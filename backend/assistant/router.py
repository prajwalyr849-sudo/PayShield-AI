"""FastAPI router for PayShield AI Shopping Assistant, evidence scoring, and Guard Buy."""

from datetime import datetime, timezone
import json
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.assistant.ai_client import AssistantAIService
from backend.assistant.ai_client import AssistantProviderError
from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.assistant.catalog import CATALOG_PRODUCTS, get_catalog_products
from backend.assistant.checkout_service import AssistantCheckoutService
from backend.assistant.evidence_store import ProductEvidenceStore
from backend.assistant.guard_buy_service import GuardBuyError, GuardBuyService
from backend.assistant.models import (
    AssistantChatRequest,
    AssistantCheckoutRequest,
    AssistantCheckoutResponse,
    GuardBuyCheckoutRequest,
    GuardBuyCheckoutResponse,
    GuardBuyRequest,
    GuardBuyResponse,
    GuardBuyReviewRequest,
    ProductItem,
    ProductLiveRating,
    ProductRating,
    ProductRatingDimensionScores,
    ProductRatingRequest,
    ProductRecommendation,
    SearchDiagnostics,
    ShoppingAssistantResponse,
    ShoppingIntent,
    ShoppingQueryRequest,
)
from backend.assistant.recommendation_engine import RecommendationEngine
from backend.assistant.price_enrichment import PriceEnrichmentService
from backend.assistant.identity_matcher import match_identity
from backend.assistant.rating_provider import (
    ProductRatingError,
    default_rating_provider,
)
from backend.assistant.rating_service import RatingService
from backend.assistant.search_provider import EndlessSearchProvider, ProductSearchError
from backend.assistant.channel3_provider import Channel3SearchProvider
from backend.assistant.product_provider import (
    ProductProviderService,
    fallback_enabled_from_env,
    finalize_evidence_status,
)
from backend.assistant.scoring import ScoringEngine
from backend.payment.receipts import ReceiptStore

router = APIRouter(prefix="/assistant", tags=["AI Shopping Assistant"])

# Singleton instances
_ai_service = AssistantAIService()
_scoring_engine = ScoringEngine()
_recommendation_engine = RecommendationEngine(_scoring_engine)
_checkout_service = AssistantCheckoutService()
# Channel3 is the primary structured product provider; the general web-search
# provider is an explicitly-enabled, clearly-labelled fallback.
_product_search_service = ProductProviderService(
    Channel3SearchProvider(),
    fallback=EndlessSearchProvider(),
    fallback_enabled=fallback_enabled_from_env(),
)
_price_enrichment = PriceEnrichmentService()
_evidence_store = ProductEvidenceStore()
_receipt_store = ReceiptStore()
_rating_service = RatingService()
_guard_buy_service = GuardBuyService(
    _evidence_store,
    checkout_service=_checkout_service,
    rating_service=_rating_service,
    receipt_store=_receipt_store,
)


def get_ai_service() -> AssistantAIService:
    return _ai_service


def get_recommendation_engine() -> RecommendationEngine:
    return _recommendation_engine


def get_scoring_engine() -> ScoringEngine:
    return _scoring_engine


def get_checkout_service() -> AssistantCheckoutService:
    return _checkout_service


def get_search_provider() -> ProductProviderService:
    return _product_search_service


def get_price_enrichment() -> PriceEnrichmentService:
    return _price_enrichment


def get_evidence_store() -> ProductEvidenceStore:
    return _evidence_store


def get_rating_service() -> RatingService:
    return _rating_service


def get_guard_buy_service() -> GuardBuyService:
    return _guard_buy_service


def _run_live_search(
    search_provider,
    *,
    query: str,
    budget,
    currency: str,
    category,
    country: str,
):
    """Run a live search through any provider, returning (results, diagnostics).

    Providers that expose ``search_with_diagnostics`` (the supported interface)
    return structured diagnostics; older providers fall back to plain lists.
    """
    if hasattr(search_provider, "search_with_diagnostics"):
        outcome = search_provider.search_with_diagnostics(
            query,
            budget=budget,
            currency=currency,
            category=category,
            country=country,
        )
        return outcome.results, outcome.diagnostics
    return (
        search_provider.search(
            query,
            budget=budget,
            currency=currency,
            category=category,
            country=country,
        ),
        None,
    )


def _build_search_summary(query: str, count: int, diagnostics) -> str:
    if count:
        return f"Found {count} live product page{'' if count == 1 else 's'} for '{query}'."
    if diagnostics is not None and diagnostics.provider_result_count:
        return (
            f"No individual retailer product pages matched '{query}'. The provider returned "
            f"{diagnostics.provider_result_count} results, none of which were verifiable product "
            "pages. Try a specific model or product name, then search again."
        )
    return f"No live products matched '{query}'. Try a broader query or different budget."


def _enrich_prices(enrichment, results, *, currency: str):
    """Attach source-verified prices when an enrichment service is available."""
    if enrichment is not None and hasattr(enrichment, "enrich"):
        return enrichment.enrich(results, expected_currency=currency)
    return results


def _summarize_prices(diagnostics, results) -> None:
    if diagnostics is None:
        return
    verified = 0
    products = 0
    methods: dict = {}
    for result in results:
        if getattr(result, "result_type", "") != "product":
            continue
        products += 1
        if getattr(result, "price_verified", False):
            verified += 1
            method = getattr(result, "price_method", "") or "unknown"
            methods[method] = methods.get(method, 0) + 1
    diagnostics.prices_verified = verified
    diagnostics.prices_unverified = max(products - verified, 0)
    diagnostics.price_methods = methods


def _apply_identity_matching(results, query: str) -> None:
    """Attach a deterministic identity match to each product result.

    The comparison is between the shopper's request and the candidate's title.
    It never fabricates attributes; unknown dimensions stay unknown.
    """
    if not query or not query.strip():
        return
    for result in results:
        if getattr(result, "result_type", "") != "product":
            continue
        outcome = match_identity(query, getattr(result, "title", ""))
        result.identity_match = outcome.outcome
        result.identity_reasons = list(outcome.reasons)
        result.identity_conflicts = list(outcome.conflicts)


@router.get("/status")
def get_assistant_status(
    ai_service: AssistantAIService = Depends(get_ai_service),
    search_provider: Any = Depends(get_search_provider),
):
    """Return configured AI assistant provider and runtime status."""
    resolved_search = search_provider if hasattr(search_provider, "configured") else get_search_provider()
    return {
        "status": "configured" if ai_service.ollama_configured else "unavailable",
        "provider": ai_service.provider_name,
        "model": ai_service.ai_model,
        "configured": ai_service.ollama_configured,
        "assistant_configured": getattr(ai_service, "ollama_configured", False),
        "rating_configured": ai_service.rating_configured,
        "ollama_client_installed": bool(getattr(ai_service, "client_installed", False)),
        "offline_catalog_available": True,
        "live_search_configured": bool(getattr(resolved_search, "configured", False)),
        "search_provider": getattr(resolved_search, "provider_name", "unknown"),
        "base_url": getattr(ai_service, "ollama_base_url", ""),
    }


@router.get("/provider-health")
def get_provider_health(
    ai_service: AssistantAIService = Depends(get_ai_service),
):
    """Advisory, non-secret check that the configured Ollama host and model are usable."""
    return ai_service.verify_provider()


@router.post("/intent", response_model=ShoppingIntent)
def parse_shopping_intent(
    request: ShoppingQueryRequest,
    ai_service: AssistantAIService = Depends(get_ai_service),
):
    """Analyze query text and extract category, budget constraints, and requirements."""
    try:
        return ai_service.parse_intent(
            query=request.query,
            budget=request.budget,
            category_hint=request.category,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process shopping intent: {str(exc)}",
        ) from exc


@router.post("/recommendations", response_model=ShoppingAssistantResponse)
def get_recommendations(
    request: ShoppingQueryRequest,
    ai_service: AssistantAIService = Depends(get_ai_service),
    rec_engine: Optional[RecommendationEngine] = Depends(get_recommendation_engine),
    search_provider: Any = Depends(get_search_provider),
    enrichment: Optional[PriceEnrichmentService] = Depends(get_price_enrichment),
    evidence_store: ProductEvidenceStore = Depends(get_evidence_store),
):
    """Search live product evidence; never substitute the offline catalog."""
    try:
        search_results, search_diagnostics = _run_live_search(
            search_provider,
            query=request.query,
            budget=request.budget,
            currency=request.currency,
            category=request.category,
            country=request.country,
        )
    except ProductSearchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    search_results = _enrich_prices(
        enrichment, search_results, currency=request.currency
    )
    finalize_evidence_status(search_results)
    _summarize_prices(search_diagnostics, search_results)
    _apply_identity_matching(search_results, request.query)
    intent = ai_service.parse_intent(
        query=request.query,
        budget=request.budget,
        category_hint=request.category,
    )
    evidence_store.save_search_results(
        search_results, category=intent.category or request.category or ""
    )

    recommendations: List[ProductRecommendation] = []
    summary = _build_search_summary(request.query, len(search_results), search_diagnostics)

    return ShoppingAssistantResponse(
        query=request.query,
        intent=intent,
        recommendations=recommendations,
        summary=summary,
        model_provider=ai_service.provider_name,
        timestamp=datetime.now(timezone.utc).isoformat(),
        search_results=search_results,
        search_diagnostics=search_diagnostics,
    )


@router.post("/chat")
def assistant_chat(
    request: AssistantChatRequest,
    ai_service: AssistantAIService = Depends(get_ai_service),
    rec_engine: RecommendationEngine = Depends(get_recommendation_engine),
    current_user: User = Depends(get_current_user),
    search_provider: Any = Depends(get_search_provider),
    enrichment: Optional[PriceEnrichmentService] = Depends(get_price_enrichment),
    evidence_store: ProductEvidenceStore = Depends(get_evidence_store),
):
    """Authenticated live-search chat with bounded per-request history."""
    del current_user
    intent = ai_service.parse_intent(
        query=request.query,
        budget=request.budget,
        category_hint=request.category,
    )

    try:
        search_results, search_diagnostics = _run_live_search(
            search_provider,
            query=request.query,
            budget=request.budget,
            currency=request.currency,
            category=request.category,
            country=request.country,
        )
    except ProductSearchError as exc:
        # Do not fail the AI chat if live product search is unavailable.
        search_results = []
        search_diagnostics = SearchDiagnostics(
            provider=getattr(search_provider, "provider_name", "endless-search"),
            configured=False,
            query=request.query,
            notes=[f"Live product search was unavailable for this request: {exc}"],
        )
    search_results = _enrich_prices(
        enrichment, search_results, currency=request.currency
    )
    finalize_evidence_status(search_results)
    _summarize_prices(search_diagnostics, search_results)
    _apply_identity_matching(search_results, request.query)

    evidence_store.save_search_results(
        search_results, category=intent.category or request.category or ""
    )

    try:
        reply = ai_service.generate_chat_response(
            query=request.query,
            messages=[message.model_dump() for message in request.messages],
            catalog_context=json.dumps(
                [result.model_dump() for result in search_results], ensure_ascii=True
            ),
        )
    except AssistantProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return {
        "reply": reply,
        "intent": intent,
        "recommendations": [],
        "search_results": search_results,
        "search_diagnostics": search_diagnostics,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": ai_service.provider_name,
        "search_available": search_diagnostics.configured if search_diagnostics else True,
    }


@router.post("/rate", response_model=ProductRating)
def rate_product(
    request: ProductRatingRequest,
    ai_service: AssistantAIService = Depends(get_ai_service),
    evidence_store: ProductEvidenceStore = Depends(get_evidence_store),
    current_user: User = Depends(get_current_user),
):
    """Return an advisory AI assessment for stored product evidence via Ollama."""
    del current_user
    product = evidence_store.get_product(request.product_reference)
    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown or expired product reference. Run a live search again.",
        )

    try:
        assessment = ai_service.rate_product(request.query, product)
    except AssistantProviderError as exc:
        return ProductRating(
            product_reference=request.product_reference,
            available=False,
            explanation=f"AI assessment unavailable: {exc}",
            evidence_urls=[product.get("source_url", "")] if product.get("source_url") else [],
            model=ai_service.ai_model,
        )

    return ProductRating(
        product_reference=request.product_reference,
        available=True,
        ai_score=assessment.get("ai_score"),
        explanation=assessment.get("explanation", ""),
        strengths=assessment.get("strengths", []),
        concerns=assessment.get("concerns", []),
        missing_information=assessment.get("missing_information", []),
        evidence_urls=assessment.get("evidence_urls", []),
        dimension_scores=ProductRatingDimensionScores(
            **assessment.get("dimension_scores", {})
        ),
        model=assessment.get("model", ai_service.ai_model),
    )


@router.get("/rating", response_model=ProductLiveRating)
def get_live_rating(
    product_reference: str,
    source_url: str,
    sku: Optional[str] = None,
    force_refresh: bool = False,
    rating_service: RatingService = Depends(get_rating_service),
    current_user: User = Depends(get_current_user),
):
    """Return live product rating evidence for a product reference.

    The browser supplies the product reference and source URL; the server
    re-derives the rating from the configured provider (or reports
    unavailability). Ollama explains the evidence but never invents a rating.
    """
    del current_user
    try:
        evidence = rating_service.fetch_rating(
            product_reference=product_reference,
            source_url=source_url,
            sku=sku,
            force_refresh=force_refresh,
        )
    except ProductRatingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ProductLiveRating(
        product_reference=evidence.product_reference,
        provider=evidence.provider,
        available=evidence.status == "available" and evidence.rating is not None,
        rating=evidence.rating,
        review_count=evidence.review_count,
        source_url=evidence.source_url,
        status=evidence.status,
        reason=evidence.reason,
        retrieved_at=evidence.retrieved_at,
        ttl_seconds=evidence.ttl_seconds,
        cache_hit=evidence.cache_hit,
        ollama_explanation=evidence.ollama_explanation,
        ollama_available=evidence.ollama_available,
    )


def _guard_buy_http_error(exc: GuardBuyError) -> HTTPException:
    """Translate a GuardBuyError into a structured HTTP conflict.

    Frontends need an actionable, stable code (not just prose) so expected
    conflicts can be shown inline and retried correctly.
    """
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": getattr(exc, "code", "guard_buy_error"), "message": str(exc)},
    )


@router.post("/guard-buy", response_model=GuardBuyResponse)
def guard_buy(
    request: GuardBuyRequest,
    guard_buy_service: GuardBuyService = Depends(get_guard_buy_service),
    current_user: User = Depends(get_current_user),
):
    """Authoritative PayShield decision for a stored product reference.

    The browser supplies only the reference and quantity; amount and identity
    are re-derived server-side. Ollama never influences this decision.
    """
    try:
        return guard_buy_service.decide(request, user_id=current_user.id)
    except GuardBuyError as exc:
        raise _guard_buy_http_error(exc) from exc


@router.post("/guard-buy/review", response_model=GuardBuyResponse)
def guard_buy_review(
    request: GuardBuyReviewRequest,
    guard_buy_service: GuardBuyService = Depends(get_guard_buy_service),
    current_user: User = Depends(get_current_user),
):
    """Explicit review approval; re-evaluates through the backend before proceeding."""
    try:
        return guard_buy_service.approve_review(
            request.decision_reference,
            approved=request.approved,
            reviewer_user_id=current_user.id,
        )
    except GuardBuyError as exc:
        raise _guard_buy_http_error(exc) from exc


@router.post("/guard-buy/checkout", response_model=GuardBuyCheckoutResponse)
def guard_buy_checkout(
    request: GuardBuyCheckoutRequest,
    guard_buy_service: GuardBuyService = Depends(get_guard_buy_service),
    current_user: User = Depends(get_current_user),
):
    """Create a PayPal Sandbox order, only for an authoritative ALLOW decision."""
    try:
        return guard_buy_service.checkout(
            request.decision_reference,
            user_id=current_user.id,
            idempotency_key=request.idempotency_key,
        )
    except GuardBuyError as exc:
        raise _guard_buy_http_error(exc) from exc


@router.get("/products", response_model=List[ProductItem])
def list_catalog_products(category: str = ""):
    """List available verified products in the catalog with explicit data source labeling."""
    return get_catalog_products(category)


@router.get("/products/{product_id}")
def get_product_details(
    product_id: str,
    scoring: ScoringEngine = Depends(get_scoring_engine),
    ai_service: AssistantAIService = Depends(get_ai_service),
):
    """Retrieve detailed product specifications and computed PVS/WTS scores."""
    product = next((p for p in CATALOG_PRODUCTS if p.id == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found in catalog.")

    default_intent = ai_service.parse_intent(query=product.title, category_hint=product.category)
    pvs = scoring.calculate_product_value_score(product, default_intent)
    wts = scoring.calculate_website_trust_score(product)

    return {
        "product": product,
        "value_score": pvs,
        "trust_score": wts,
    }


@router.post("/checkout", response_model=AssistantCheckoutResponse)
def assistant_checkout(
    request: AssistantCheckoutRequest,
    checkout_svc: AssistantCheckoutService = Depends(get_checkout_service),
):
    """Execute guarded PayPal checkout with PayShield Risk & Policy governance."""
    try:
        return checkout_svc.process_checkout(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Checkout failed: {str(exc)}") from exc
