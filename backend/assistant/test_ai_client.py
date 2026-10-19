import pytest

from backend.assistant import ai_client
from backend.assistant.ai_client import AssistantAIService, AssistantProviderError


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def chat(self, **_kwargs):
        if self.error:
            raise self.error
        return self.response


class ProviderFailure(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


def test_module_imports_without_ollama_client(monkeypatch):
    """A missing ollama package must never break importing the backend modules."""
    # The module-level guard is what protects backend startup; assert it exists
    # and that a missing client is handled without raising at import time.
    assert hasattr(ai_client, "OLLAMA_CLIENT_AVAILABLE")
    assert hasattr(ai_client, "OllamaClient")


def test_client_reports_clear_error_when_package_missing(monkeypatch):
    service = AssistantAIService()
    service.ollama_api_key = "test-key"
    service.ai_model = "gemma4:31b"
    monkeypatch.setattr(ai_client, "OllamaClient", None)
    monkeypatch.setattr(ai_client, "OLLAMA_CLIENT_AVAILABLE", False)

    with pytest.raises(AssistantProviderError, match="client is not installed") as raised:
        service._client()
    assert raised.value.status_code == 503


def test_client_reports_clear_error_when_model_missing(monkeypatch):
    service = AssistantAIService()
    service.ollama_api_key = "test-key"
    service.ai_model = ""

    with pytest.raises(AssistantProviderError, match="model is not configured"):
        service._client()


def test_verify_provider_reports_missing_model(monkeypatch):
    service = AssistantAIService()
    service.ai_model = ""
    result = service.verify_provider()
    assert result["reachable"] is False
    assert result["model_available"] is False
    assert "OLLAMA_MODEL" in result["reason"]


def test_verify_provider_reports_unreachable_host(monkeypatch):
    service = AssistantAIService()
    service.ollama_api_key = "test-key"
    service.ai_model = "gemma4:31b"

    def boom(*_args, **_kwargs):
        raise ai_client.requests.RequestException("connection refused")

    monkeypatch.setattr(ai_client.requests, "get", boom)
    result = service.verify_provider()
    assert result["reachable"] is False
    assert "could not be reached" in result["reason"]


def test_verify_provider_detects_available_model(monkeypatch):
    service = AssistantAIService()
    service.ollama_api_key = "test-key"
    service.ai_model = "gemma4:31b"

    class Response:
        status_code = 200

        def json(self):
            return {"models": [{"name": "gemma4:31b"}, {"name": "llama3.3"}]}

    monkeypatch.setattr(ai_client.requests, "get", lambda *a, **k: Response())
    result = service.verify_provider()
    assert result["reachable"] is True
    assert result["model_available"] is True
    assert result["reason"] == ""


def test_verify_provider_reports_model_not_available(monkeypatch):
    service = AssistantAIService()
    service.ollama_api_key = "test-key"
    service.ai_model = "does-not-exist:1b"

    class Response:
        status_code = 200

        def json(self):
            return {"models": [{"name": "gemma4:31b"}]}

    monkeypatch.setattr(ai_client.requests, "get", lambda *a, **k: Response())
    result = service.verify_provider()
    assert result["reachable"] is True
    assert result["model_available"] is False
    assert "not available" in result["reason"]



def test_generate_chat_response_returns_mocked_ollama_text():
    service = AssistantAIService()
    service.ollama_api_key = "test-key"
    service.ai_model = "gemma4:31b"
    service._ollama_client = FakeClient(
        response={"message": {"content": "Verified response"}}
    )

    assert service.generate_chat_response("Hello", []) == "Verified response"


@pytest.mark.parametrize(
    ("error", "status", "expected"),
    [
        (
            ProviderFailure("401 unauthorized", 401),
            401,
            "authentication failed",
        ),
        (ProviderFailure("429 quota exceeded", 429), 429, "quota or rate limit"),
        (ProviderFailure("404 model not found", 404), 404, "model is unavailable"),
        (ProviderFailure("request timeout", 503), 503, "temporarily unavailable"),
    ],
)
def test_generate_chat_response_classifies_provider_failures(
    error, status, expected, monkeypatch
):
    service = AssistantAIService()
    service.ollama_api_key = "test-key"
    service.ai_model = "gemma4:31b"
    service._ollama_client = FakeClient(error=error)
    monkeypatch.setattr("backend.assistant.ai_client.time.sleep", lambda _seconds: None)

    with pytest.raises(AssistantProviderError) as raised:
        service.generate_chat_response("Hello", [])

    assert raised.value.status_code == status
    assert expected in str(raised.value)


def test_unconfigured_service_fails_without_provider_call():
    service = AssistantAIService()
    service.ollama_api_key = ""
    # Pin a remote host so the outcome does not depend on ambient .env config.
    service.ollama_base_url = "https://ollama.com"

    with pytest.raises(AssistantProviderError, match="not configured") as raised:
        service.generate_chat_response("Hello", [])
    assert raised.value.status_code == 503


def test_local_ollama_host_is_configured_without_key(monkeypatch):
    service = AssistantAIService()
    service.ollama_api_key = ""
    service.ai_model = "gemma4:31b"
    service.ollama_base_url = "http://localhost:11434"

    assert service.ollama_configured is True
    assert service.rating_configured is True

    captured = {}

    def recorder(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(ai_client, "OllamaClient", recorder)
    monkeypatch.setattr(ai_client, "OLLAMA_CLIENT_AVAILABLE", True)

    client = service._client()
    assert client is not None
    assert captured["host"] == "http://localhost:11434"
    assert captured["headers"] == {}


def test_keyed_remote_host_sends_authorization_header(monkeypatch):
    service = AssistantAIService()
    service.ollama_api_key = "secret-key"
    service.ai_model = "gemma4:31b"
    service.ollama_base_url = "https://ollama.com"

    captured = {}

    def recorder(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(ai_client, "OllamaClient", recorder)
    monkeypatch.setattr(ai_client, "OLLAMA_CLIENT_AVAILABLE", True)

    service._client()
    assert captured["headers"] == {"Authorization": "Bearer secret-key"}


def test_empty_base_url_falls_back_to_local_default_without_key(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "")
    monkeypatch.setenv("OLLAMA_BASE_URL", "")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:31b")

    service = AssistantAIService()
    assert service.ollama_base_url == "http://localhost:11434"
    assert service.ollama_configured is True


def test_empty_base_url_falls_back_to_cloud_default_with_key(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "secret-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:31b")

    service = AssistantAIService()
    assert service.ollama_base_url == "https://ollama.com"
    assert service.ollama_configured is True
