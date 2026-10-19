"""Unit tests for Assistant intent parsing and heuristic NLP engine."""

import pytest
from backend.assistant.ai_client import AssistantAIService


@pytest.fixture
def ai_service():
    return AssistantAIService()


def test_intent_parsing_budget_and_category(ai_service):
    query = "Find noise-cancelling headphones under $250 for travel"
    intent = ai_service.parse_intent(query)

    assert intent.category == "electronics"
    assert intent.target_budget == 250.0
    assert any("noise" in req for req in intent.key_requirements) or "wireless" in intent.extracted_keywords
    assert intent.confidence >= 0.8


def test_intent_parsing_office_chair(ai_service):
    query = "Ergonomic mesh chair with lumbar support below $350"
    intent = ai_service.parse_intent(query)

    assert intent.category == "office"
    assert intent.target_budget == 350.0
    assert "ergonomic" in intent.key_requirements
    assert "mesh" in intent.key_requirements
    assert "lumbar" in intent.key_requirements


def test_intent_parsing_software_category(ai_service):
    query = "Cloud hosting subscription for web app"
    intent = ai_service.parse_intent(query)

    assert intent.category == "software"
    assert intent.target_budget is None


def test_intent_tradeoff_budget(ai_service):
    query = "Cheapest mechanical keyboard under $60"
    intent = ai_service.parse_intent(query)

    assert intent.primary_tradeoff == "budget"
    assert intent.target_budget == 60.0


def test_intent_tradeoff_performance(ai_service):
    query = "Best performance 4K OLED monitor for pro gaming"
    intent = ai_service.parse_intent(query)

    assert intent.primary_tradeoff == "performance"
    assert "4k" in intent.key_requirements
    assert "oled" in intent.key_requirements


def test_intent_tradeoff_durability(ai_service):
    query = "Durable aluminum laptop stand with lifetime warranty"
    intent = ai_service.parse_intent(query)

    assert intent.primary_tradeoff == "durability"


def test_explicit_category_hint_overrides(ai_service):
    query = "Smart device"
    intent = ai_service.parse_intent(query, category_hint="office")
    assert intent.category == "office"


def test_summary_generation(ai_service):
    query = "Wireless mouse"
    intent = ai_service.parse_intent(query)
    mock_products = [
        {
            "title": "Logitech MX Master 3S",
            "price": 99.99,
            "value_score": {"overall_score": 94},
        }
    ]
    summary = ai_service.generate_summary(query, intent, mock_products)
    assert "Logitech MX Master 3S" in summary
    assert "94/100" in summary
