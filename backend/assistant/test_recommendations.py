"""Tests for 3-Product Recommendations, Product Value Scores (PVS),
and Website Trust Scores (WTS).
"""

import pytest
from backend.assistant.ai_client import AssistantAIService
from backend.assistant.catalog import CATALOG_PRODUCTS, get_catalog_products
from backend.assistant.models import ShoppingIntent, ShoppingQueryRequest
from backend.assistant.recommendation_engine import RecommendationEngine
from backend.assistant.router import (
    get_product_details,
    get_recommendations,
    list_catalog_products,
)
from backend.assistant.scoring import ScoringEngine
from backend.assistant.evidence_store import ProductEvidenceStore


@pytest.fixture
def scoring_engine():
    return ScoringEngine()


@pytest.fixture
def rec_engine(scoring_engine):
    return RecommendationEngine(scoring_engine)


@pytest.fixture
def ai_service():
    return AssistantAIService()


def test_catalog_products_have_data_source_and_specs():
    for p in CATALOG_PRODUCTS:
        assert p.data_source in {"live", "sourced", "demo"}
        assert p.price > 0
        assert p.rating >= 0.0 and p.rating <= 5.0
        assert p.review_count >= 0
        assert p.merchant_name
        assert p.merchant_domain
        assert len(p.specs) > 0


def test_three_recommendations_curation(rec_engine):
    intent = ShoppingIntent(
        category="electronics",
        target_budget=400.0,
        extracted_keywords=["headphones", "noise", "cancelling"],
        key_requirements=["noise cancellation"],
        primary_tradeoff="value",
    )
    recs = rec_engine.get_three_recommendations(intent)

    # Exactly 3 recommendations
    assert len(recs) == 3

    # Ranks 1, 2, 3
    ranks = [r.rank for r in recs]
    assert ranks == [1, 2, 3]

    # Badges
    badges = [r.badge for r in recs]
    assert "Top Value Pick" in badges
    assert "Best Performance" in badges
    assert "Budget Champion" in badges

    # All items distinct
    product_ids = [r.product.id for r in recs]
    assert len(set(product_ids)) == 3


def test_product_value_score_breakdown(scoring_engine):
    product = CATALOG_PRODUCTS[0]
    intent = ShoppingIntent(
        category="electronics",
        target_budget=400.0,
        key_requirements=["noise cancellation"],
        primary_tradeoff="value",
    )
    pvs = scoring_engine.calculate_product_value_score(product, intent)

    assert 10 <= pvs.overall_score <= 100
    assert 0 <= pvs.price_efficiency_score <= 100
    assert 0 <= pvs.specification_match_score <= 100
    assert 0 <= pvs.sentiment_reliability_score <= 100
    assert 0 <= pvs.longevity_score <= 100
    assert len(pvs.rationale) >= 2
    assert len(pvs.evidence_points) >= 3


def test_website_trust_score_breakdown(scoring_engine):
    product = CATALOG_PRODUCTS[0]  # B&H Photo
    wts = scoring_engine.calculate_website_trust_score(product)

    assert 10 <= wts.overall_trust <= 100
    assert 0 <= wts.domain_age_score <= 100
    assert 0 <= wts.ssl_security_score <= 100
    assert 0 <= wts.merchant_reputation_score <= 100
    assert 0 <= wts.refund_dispute_score <= 100
    assert wts.risk_level in {"LOW", "MEDIUM", "HIGH"}
    assert len(wts.verification_badges) >= 2


def test_recommendations_endpoint(ai_service, rec_engine, tmp_path):
    req = ShoppingQueryRequest(
        query="Ergonomic office chair under $500",
        category="office",
        budget=500.0,
    )
    class EmptySearchProvider:
        def search(self, *args, **kwargs):
            return []

    res = get_recommendations(
        request=req,
        ai_service=ai_service,
        rec_engine=rec_engine,
        search_provider=EmptySearchProvider(),
        evidence_store=ProductEvidenceStore(db_path=tmp_path / "rec.db"),
    )

    assert res.query == "Ergonomic office chair under $500"
    assert res.intent.category == "office"
    assert res.recommendations == []
    assert res.search_results == []
    assert len(res.summary) > 20
    assert res.model_provider


def test_product_details_endpoint(scoring_engine, ai_service):
    prod_id = "prod-sony-wh1000xm5"
    details = get_product_details(product_id=prod_id, scoring=scoring_engine, ai_service=ai_service)

    assert details["product"].id == prod_id
    assert details["value_score"].overall_score > 0
    assert details["trust_score"].overall_trust > 0
