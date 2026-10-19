"""Endpoint handler tests for PayShield AI Shopping Assistant router."""

import pytest
from backend.assistant.ai_client import AssistantAIService
from backend.assistant.models import AssistantChatRequest, ShoppingQueryRequest
from backend.auth.models import User
from backend.assistant.router import (
    assistant_chat,
    get_assistant_status,
    get_provider_health,
    parse_shopping_intent,
)


@pytest.fixture
def ai_service():
    return AssistantAIService()


def test_assistant_status_endpoint(ai_service):
    data = get_assistant_status(ai_service=ai_service)
    assert data["status"] in {"configured", "unavailable"}
    assert "provider" in data
    assert data["configured"] is ai_service.ollama_configured
    assert data["offline_catalog_available"] is True
    assert "ollama_client_installed" in data


def test_provider_health_endpoint_reports_status(ai_service, monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "verify_provider",
        lambda timeout=None: {
            "reachable": True,
            "model": ai_service.ai_model,
            "model_available": True,
            "reason": "",
        },
    )
    data = get_provider_health(ai_service=ai_service)
    assert data["reachable"] is True
    assert data["model_available"] is True


def test_parse_shopping_intent_endpoint(ai_service):
    req = ShoppingQueryRequest(
        query="Ergonomic standing desk under $450",
        category="office",
        budget=450.0,
    )
    data = parse_shopping_intent(request=req, ai_service=ai_service)
    assert data.category == "office"
    assert data.target_budget == 450.0
    assert "ergonomic" in data.key_requirements or "standing desk" in data.key_requirements


from backend.assistant.search_provider import EndlessSearchProvider, SearchOutcome
from backend.assistant.search_provider import ProductSearchError
from backend.assistant.models import SearchDiagnostics
from backend.assistant.evidence_store import ProductEvidenceStore


def test_assistant_chat_endpoint(ai_service, monkeypatch, tmp_path):
    req = AssistantChatRequest(
        query="Find me high-end wireless headphones with active noise cancellation",
        messages=[],
    )
    search_provider = EndlessSearchProvider(api_key="configured")
    monkeypatch.setattr(
        search_provider,
        "search_with_diagnostics",
        lambda *args, **kwargs: SearchOutcome(
            results=[],
            diagnostics=SearchDiagnostics(
                provider="endless-search", configured=True, query=req.query
            ),
        ),
    )
    monkeypatch.setattr(
        ai_service,
        "generate_chat_response",
        lambda query, messages, catalog_context: "The electronics catalog has matching options.",
    )
    data = assistant_chat(
        request=req,
        ai_service=ai_service,
        current_user=User(id="user-1", primary_email="user@example.com", full_name="User"),
        search_provider=search_provider,
        evidence_store=ProductEvidenceStore(db_path=tmp_path / "evidence.db"),
    )
    assert "reply" in data
    assert "intent" in data
    assert data["intent"].category == "electronics"
    assert "electronics" in data["reply"].lower()
    assert "timestamp" in data


def test_assistant_chat_continues_when_live_search_unavailable(
    ai_service, monkeypatch, tmp_path
):
    """Chat must not 503 merely because live product search is unavailable.

    A 503 from /assistant/chat must mean the AI assistant itself is unavailable,
    never that an optional product search failed.
    """
    req = AssistantChatRequest(query="Find me noise cancelling headphones", messages=[])
    search_provider = EndlessSearchProvider(api_key="")

    def boom(*args, **kwargs):
        raise ProductSearchError(
            "Live product search is not configured. Set ENDLESS_SEARCH_KEY on the backend."
        )

    monkeypatch.setattr(search_provider, "search_with_diagnostics", boom)
    monkeypatch.setattr(
        ai_service,
        "generate_chat_response",
        lambda query, messages, catalog_context: "Here are catalog options to compare.",
    )
    data = assistant_chat(
        request=req,
        ai_service=ai_service,
        current_user=User(id="user-1", primary_email="user@example.com", full_name="User"),
        search_provider=search_provider,
        evidence_store=ProductEvidenceStore(db_path=tmp_path / "evidence.db"),
    )
    assert data["reply"] == "Here are catalog options to compare."
    assert data["search_results"] == []
    assert data["search_available"] is False
    assert data["search_diagnostics"].configured is False
    assert any(
        "unavailable" in note.lower() for note in data["search_diagnostics"].notes
    )

