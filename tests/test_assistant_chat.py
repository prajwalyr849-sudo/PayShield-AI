from unittest.mock import Mock

import pytest

from backend.assistant.ai_client import AssistantAIService, AssistantProviderError
from backend.assistant.models import AssistantChatRequest


def test_chat_requires_ollama_configuration(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "replace-with-key")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:31b")
    # Pin a remote host so an invalid placeholder key is genuinely unconfigured
    # (an empty base URL would legitimately fall back to a keyless local host).
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.com")

    service = AssistantAIService()

    with pytest.raises(AssistantProviderError, match="not configured"):
        service.generate_chat_response("Help me compare laptops", [])


def test_chat_returns_provider_text(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:31b")
    service = AssistantAIService()
    service._ollama_client = Mock()
    service._ollama_client.chat.return_value = {
        "message": {"content": "I can help compare live products."}
    }

    result = service.generate_chat_response(
        "Compare laptops",
        [{"role": "user", "content": "I need a coding laptop"}],
    )

    assert result == "I can help compare live products."
    service._ollama_client.chat.assert_called_once()


def test_chat_rejects_oversized_query(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    service = AssistantAIService()

    with pytest.raises(AssistantProviderError, match="too long"):
        service.generate_chat_response("x" * 2001, [])


def test_chat_maps_quota_errors(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:31b")
    service = AssistantAIService()

    class QuotaError(Exception):
        status_code = 429

    service._ollama_client = Mock()
    service._ollama_client.chat.side_effect = QuotaError("quota exceeded")

    with pytest.raises(AssistantProviderError, match="quota or rate limit"):
        service.generate_chat_response("Compare laptops", [])


def test_chat_rejects_oversized_history():
    with pytest.raises(ValueError, match="history is too large"):
        AssistantChatRequest(
            query="Compare laptops",
            messages=[{"role": "user", "content": "x" * 2000}] * 7,
        )
