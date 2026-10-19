"""Pydantic schemas for PayShield AI Shopping Assistant, Recommendations, and Scoring."""

from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


class ShoppingQueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500, description="User search query or purchase objective")
    budget: Optional[float] = Field(default=None, ge=1.0, le=100000.0, description="Optional maximum budget constraint")
    category: Optional[str] = Field(default=None, max_length=100, description="Optional shopping category hint")
    currency: str = Field(default="USD", pattern=r"^[A-Za-z]{3}$")
    country: str = Field(default="US", min_length=2, max_length=2)
    preferred_merchant: Optional[str] = Field(default=None, max_length=100)
    agent_id: str = Field(default="agent-001", max_length=100)
    user_id: Optional[str] = Field(default="demo-user", max_length=100)


class ShoppingIntent(BaseModel):
    category: str = Field(description="Normalized commerce category, e.g. electronics, office, software")
    target_budget: Optional[float] = None
    extracted_keywords: List[str] = Field(default_factory=list)
    key_requirements: List[str] = Field(default_factory=list)
    primary_tradeoff: Literal["value", "performance", "budget", "durability", "balanced"] = "balanced"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class ProductItem(BaseModel):
    id: str
    title: str
    brand: str
    price: float
    currency: str = "USD"
    merchant_name: str
    merchant_domain: str
    category: str
    description: str
    specs: Dict[str, Any] = Field(default_factory=dict)
    rating: float = Field(ge=0.0, le=5.0)
    review_count: int = Field(ge=0)
    data_source: Literal["live", "sourced", "demo"] = "sourced"
    image_url: str = ""
    merchant_url: str = ""


class ProductSearchResult(BaseModel):
    id: str
    product_reference: str = ""
    title: str
    source_url: str
    source_domain: str
    snippet: str = ""
    retailer: str = ""
    image_url: str = ""
    price: Optional[float] = Field(default=None, ge=0)
    price_verified: bool = False
    price_currency: str = ""
    price_type: str = Field(default="", description="selling_price, list_price, sale_price, aggregate, or unknown")
    price_method: str = Field(default="", description="json_ld, meta, microdata, labelled_text, snippet, or none")
    price_confidence: str = Field(default="", description="high, medium, low, or none")
    price_source_url: str = ""
    price_retrieved_at: str = ""
    price_unverified_reason: str = ""
    availability: str = "Unknown"
    result_type: Literal["product", "article"] = "article"
    currency: str = "USD"
    search_timestamp: str
    retrieval_status: str = Field(
        default="", description="retrieved, http_error, timeout, blocked, non_html, ..."
    )
    retrieval_reason: str = Field(
        default="", description="Safe explanation of a failed source-page retrieval"
    )
    retrieval_http_status: Optional[int] = Field(default=None, ge=100, le=599)
    identity_match: Literal["MATCH", "PARTIAL_MATCH", "MISMATCH", "UNKNOWN"] = Field(
        default="UNKNOWN",
        description="Deterministic comparison of the request against the candidate title",
    )
    identity_reasons: List[str] = Field(default_factory=list)
    identity_conflicts: List[str] = Field(default_factory=list)
    provider: str = Field(
        default="",
        description="Evidence provider that produced this result: channel3 or endless-search",
    )
    is_fallback: bool = Field(
        default=False,
        description="True when this evidence came from the configured fallback provider",
    )
    evidence_status: str = Field(
        default="",
        description="Evidence state: VERIFIED, CANDIDATE, CONFLICT, or UNAVAILABLE",
    )
    condition: str = Field(
        default="", description="Offer condition reported by the provider: new, used, or unknown"
    )
    variant: str = Field(
        default="", description="Selected variant summary when the provider reports one"
    )
    seller: str = Field(
        default="", description="Seller/merchant name when distinct from the source domain"
    )
    offer_count: int = Field(
        default=0, ge=0, description="Number of merchant offers the provider returned for this product"
    )
    evidence_reasons: List[str] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    # Live product rating evidence (stars/review count from a configured provider).
    rating: Optional[float] = Field(
        default=None, ge=0.0, le=5.0, description="Live reviewer rating (0-5), if a provider returned one"
    )
    review_count: Optional[int] = Field(
        default=None, ge=0, description="Number of live reviews, if a provider returned one"
    )
    rating_status: str = Field(
        default="", description="Live rating retrieval status: available, unavailable, ..."
    )
    rating_reason: str = Field(
        default="", description="Safe explanation of the live rating retrieval outcome"
    )
    rating_retrieved_at: str = Field(
        default="", description="When the live rating was last retrieved"
    )
    rating_provider: str = Field(
        default="", description="Provider that produced the live rating"
    )


class ProductRatingDimensionScores(BaseModel):
    relevance: int = Field(ge=0, le=100, default=0)
    value_for_money: int = Field(ge=0, le=100, default=0)
    specification_match: int = Field(ge=0, le=100, default=0)
    evidence_quality: int = Field(ge=0, le=100, default=0)
    source_confidence: int = Field(ge=0, le=100, default=0)


class ProductRatingRequest(BaseModel):
    product_reference: str = Field(min_length=1, max_length=200)
    query: str = Field(default="", max_length=500)


class ProductRating(BaseModel):
    product_reference: str
    available: bool = False
    label: str = "AI assessment"
    ai_score: Optional[int] = Field(default=None, ge=0, le=100)
    explanation: str = ""
    strengths: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    evidence_urls: List[str] = Field(default_factory=list)
    dimension_scores: ProductRatingDimensionScores = Field(
        default_factory=ProductRatingDimensionScores
    )
    model: str = ""
    disclaimer: str = (
        "AI assessment is advisory only. It is not a verified fact or guarantee and "
        "it never sets PayShield ALLOW, REVIEW, or BLOCK decisions."
    )


class ProductLiveRating(BaseModel):
    """Live product rating evidence with full provenance.

    Distinct from the advisory Ollama ai_score: this is a real reviewer rating
    (stars) plus review count from a configured provider, or an explicit
    unavailable/not-verified state.
    """

    product_reference: str
    provider: str
    available: bool = False
    rating: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    review_count: Optional[int] = Field(default=None, ge=0)
    source_url: str = ""
    status: str = "unavailable"
    reason: str = ""
    retrieved_at: str = ""
    ttl_seconds: int = 0
    cache_hit: bool = False
    ollama_explanation: Optional[str] = None
    ollama_available: bool = False
    disclaimer: str = (
        "Live rating is advisory consumer-sentiment evidence. It never sets "
        "PayShield ALLOW, REVIEW, or BLOCK decisions by itself."
    )


class GuardBuyRequest(BaseModel):
    product_reference: str = Field(min_length=1, max_length=200)
    quantity: int = Field(default=1, gt=0, le=100)
    agent_id: str = Field(default="agent-001", max_length=100)
    idempotency_key: Optional[str] = Field(default=None, max_length=200)


class GuardBuyResponse(BaseModel):
    decision: Literal["ALLOW", "REVIEW", "BLOCK"]
    payment_status: str
    product_reference: str
    decision_reference: Optional[str] = None
    checkout_available: bool = False
    title: str = ""
    source_url: str = ""
    retailer: str = ""
    source_domain: str = ""
    price: Optional[float] = None
    price_verified: bool = False
    price_currency: str = ""
    price_type: str = ""
    price_method: str = ""
    price_unverified_reason: str = ""
    availability: str = "Unknown"
    identity_match: Literal["MATCH", "PARTIAL_MATCH", "MISMATCH", "UNKNOWN"] = "UNKNOWN"
    currency: str = "USD"
    quantity: int = 1
    amount: Optional[float] = None
    checkout_amount_verified: bool = False
    risk_score: Optional[int] = None
    risk_level: str = ""
    reason: str
    reasons: List[str] = Field(default_factory=list)
    audit_reference: Optional[str] = None
    evaluation: Optional[Dict[str, Any]] = None
    provider: str = ""
    is_fallback: bool = False
    evidence_status: str = ""
    condition: str = ""
    seller: str = ""
    variant: str = ""
    # Live rating evidence attached to the decision.
    rating: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    review_count: Optional[int] = Field(default=None, ge=0)
    rating_status: str = ""
    rating_provider: str = ""


class GuardBuyCheckoutRequest(BaseModel):
    decision_reference: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class GuardBuyReviewRequest(BaseModel):
    decision_reference: str = Field(min_length=1, max_length=200)
    approved: bool = True


class GuardBuyCheckoutResponse(BaseModel):
    decision: Literal["ALLOW", "REVIEW", "BLOCK"]
    payment_status: str
    product_reference: str
    order_id: Optional[str] = None
    approval_url: Optional[str] = None
    total_amount: Optional[float] = None
    checkout_amount_verified: bool = False
    currency: str = "USD"
    reason: str
    evaluation: Optional[Dict[str, Any]] = None


class ProductValueScoreBreakdown(BaseModel):
    overall_score: int = Field(ge=0, le=100, description="Aggregate evidence-based Product Value Score (0-100)")
    price_efficiency_score: int = Field(ge=0, le=100)
    specification_match_score: int = Field(ge=0, le=100)
    sentiment_reliability_score: int = Field(ge=0, le=100)
    longevity_score: int = Field(ge=0, le=100)
    rationale: List[str] = Field(default_factory=list)
    evidence_points: List[str] = Field(default_factory=list)


class WebsiteTrustScoreBreakdown(BaseModel):
    overall_trust: int = Field(ge=0, le=100, description="Website Trust Score (0-100)")
    domain_age_score: int = Field(ge=0, le=100)
    ssl_security_score: int = Field(ge=0, le=100)
    merchant_reputation_score: int = Field(ge=0, le=100)
    refund_dispute_score: int = Field(ge=0, le=100)
    risk_level: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    warnings: List[str] = Field(default_factory=list)
    verification_badges: List[str] = Field(default_factory=list)


class ProductRecommendation(BaseModel):
    rank: int = Field(ge=1, le=3)
    badge: str = Field(description="e.g. Best Value, Top Performance, Budget Choice")
    product: ProductItem
    value_score: ProductValueScoreBreakdown
    trust_score: WebsiteTrustScoreBreakdown
    why_recommended: str


class SearchDiagnostics(BaseModel):
    """Structured, non-fabricated reporting of a live product search run."""

    provider: str = ""
    configured: bool = False
    query: str = ""
    strategies: List[str] = Field(default_factory=list, description="Executed provider calls, e.g. 'web:<query>'")
    attempts: int = 0
    provider_result_count: int = Field(default=0, description="Raw candidate items examined across provider calls")
    accepted_count: int = 0
    rejected_count: int = 0
    prices_verified: int = Field(default=0, description="Accepted products with a source-verified retail price")
    prices_unverified: int = Field(default=0, description="Accepted products whose price could not be verified from source")
    price_methods: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts of verified prices by extraction method (json_ld, meta, microdata, labelled_text)",
    )
    rejection_reasons: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts of rejected candidates by reason (editorial, listing, media, etc.)",
    )
    notes: List[str] = Field(default_factory=list)
    primary_provider: str = Field(
        default="", description="Name of the configured primary product provider"
    )
    providers_attempted: List[str] = Field(default_factory=list)
    fallback_used: bool = Field(
        default=False, description="True when results came from the fallback provider"
    )
    fallback_reason: str = Field(
        default="", description="Safe explanation of why the fallback provider was used"
    )


class ShoppingAssistantResponse(BaseModel):
    query: str
    intent: ShoppingIntent
    recommendations: List[ProductRecommendation] = Field(default_factory=list, max_length=3)
    summary: str
    model_provider: str
    timestamp: str
    search_results: List[ProductSearchResult] = Field(default_factory=list)
    search_diagnostics: Optional[SearchDiagnostics] = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=2000)


class AssistantChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(default_factory=list, max_length=12)
    query: str = Field(min_length=1, max_length=2000)
    budget: Optional[float] = None
    category: Optional[str] = None
    currency: str = Field(default="USD", pattern=r"^[A-Za-z]{3}$")
    country: str = Field(default="US", min_length=2, max_length=2)
    agent_id: str = "agent-001"

    @model_validator(mode="after")
    def validate_history_size(self):
        if sum(len(message.content) for message in self.messages) > 12000:
            raise ValueError("Conversation history is too large.")
        return self


class AssistantCheckoutRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=100)
    agent_id: str = Field(default="agent-001", max_length=100)
    quantity: int = Field(default=1, gt=0, le=100)
    user_id: Optional[str] = Field(default="demo-user", max_length=100)
    idempotency_key: Optional[str] = Field(default=None, max_length=200)


class AssistantCheckoutResponse(BaseModel):
    transaction_id: str
    product_id: str
    order_id: Optional[str] = None
    decision: Literal["ALLOW", "REVIEW", "BLOCK"]
    payment_status: str
    total_amount: float
    currency: str = "USD"
    approval_url: Optional[str] = None
    reason: str
    evaluation: Optional[Dict[str, Any]] = None
