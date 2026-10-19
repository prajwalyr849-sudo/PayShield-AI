"""Server-side extraction and validation of product prices.

PayShield never trusts a price that was merely displayed in a search snippet.
After a candidate product is discovered it retrieves the product's original
source page (server-side) and extracts a price from reliable evidence in
priority order:

1. Structured data -- ``schema.org`` ``Product``/``Offer`` JSON-LD
2. Explicit price metadata -- Open Graph / ``itemprop`` meta tags
3. Clearly labelled price fields -- microdata and labelled page text
4. Search snippet text -- low confidence, never auto-verified

An extracted amount is only marked ``verified`` when it comes from structured
or clearly labelled evidence, a single consistent amount is found, the currency
matches the expected checkout currency, the offer is not stale, and the page
identity is not contradicted by a different model/variant/seller.

Every other outcome returns an explicit ``reason`` so the caller can keep the
price unverified and explain exactly why.
"""

from __future__ import annotations

import html as _html
import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

import requests

USER_AGENT = (
    "PayShieldPriceBot/1.0 (+https://payshield.local; product price verification)"
)
DEFAULT_TIMEOUT = 8
DEFAULT_MAX_BYTES = 1_500_000

# Symbol -> ISO code. Ambiguous symbols (``$``) are deliberately not mapped
# here; they are resolved from ISO context on the page instead.
_SYMBOL_CURRENCIES = {
    "\u20ac": "EUR",
    "\u00a3": "GBP",
    "\u20b9": "INR",
    "\u00a5": "JPY",
    "C$": "CAD",
    "A$": "AUD",
}
_AMBIGUOUS_DOLLAR = {"$", "US$", "USD$", "$US"}
_KNOWN_CURRENCIES = {"USD", "EUR", "GBP", "INR", "CAD", "AUD", "JPY"}

_JSONLD_RE = re.compile(
    r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(
    r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))'
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_MICRODATA_PRICE_RE = re.compile(
    r'itemprop\s*=\s*["\'](?:price|lowprice|highprice)["\'][^>]*?content\s*=\s*["\']'
    r'([0-9][0-9.,\s]*)[^"\']*["\']',
    re.IGNORECASE,
)
_MICRODATA_CURRENCY_RE = re.compile(
    r'itemprop\s*=\s*["\']pricecurrency["\'][^>]*?content\s*=\s*["\']([A-Za-z]{3})',
    re.IGNORECASE,
)

# A number with optional thousands separators and 1-2 decimals.
_NUM = r"(?P<amount>\d{1,3}(?:[,\s]\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
_PRICE_WITH_SYMBOL_RE = re.compile(
    r"(?P<symbol>C\$|A\$|US\$|\u20ac|\u00a3|\u20b9|\u00a5|\$)\s*" + _NUM
)
_PRICE_WITH_ISO_RE = re.compile(
    _NUM + r"\s*(?P<iso>USD|EUR|GBP|INR|CAD|AUD|JPY)\b"
)
_ISO_WITH_PRICE_RE = re.compile(
    r"(?P<iso>USD|EUR|GBP|INR|CAD|AUD|JPY)\s*" + _NUM
)

_LIST_PRICE_LABELS = (
    "mrp",
    "m.r.p",
    "list price",
    "msrp",
    "regular price",
    "original price",
    "was ",
    "strike",
    "crossed",
    "crossed-out",
)
_SALE_PRICE_LABELS = (
    "sale price",
    "sale",
    "now ",
    " deal",
    "special price",
    "discounted",
    "offer price",
    "our price",
    "current price",
    "price today",
    "flash sale",
)
_NON_PRICE_LABELS = (
    "shipping",
    "delivery",
    "tax",
    "vat",
    "gst",
    "fee",
    "fees",
    "handling",
    "installment",
    "emi",
    "deposit",
    "down payment",
)

_BLOCKED_MARKERS = (
    "captcha",
    "are you a robot",
    "unusual traffic",
    "px-captcha",
    "enable javascript and cookies",
    "access denied",
    "verify you are human",
    "request blocked",
)

_PRIVATE_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".lan")


@dataclass
class FetchOutcome:
    """The result of attempting to retrieve a product page.

    ``fetch`` historically returned only HTML (or ``None``), which threw away
    *why* a page failed. This structured outcome preserves the original URL, the
    retrieval status, the HTTP status when one was received, the retrieval time,
    and a clear, safe failure reason so evidence can report it honestly.
    """

    url: str = ""
    html: Optional[str] = None
    status: str = "not_attempted"
    reason: str = ""
    http_status: Optional[int] = None
    content_type: str = ""
    retrieved_at: str = ""

    @property
    def ok(self) -> bool:
        return self.html is not None


@dataclass
class PriceEvidence:
    """A price extracted from a product page, with full provenance."""

    amount: Optional[float] = None
    currency: str = ""
    price_type: str = "unknown"
    method: str = "none"
    confidence: str = "none"
    verified: bool = False
    source_url: str = ""
    retrieved_at: str = ""
    reason: str = ""
    availability: str = ""
    raw_amount: str = ""
    identity: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "price": self.amount,
            "price_currency": self.currency,
            "price_type": self.price_type,
            "price_method": self.method,
            "price_confidence": self.confidence,
            "price_verified": self.verified,
            "price_source_url": self.source_url,
            "price_retrieved_at": self.retrieved_at,
            "price_unverified_reason": "" if self.verified else self.reason,
        }


def _utcnow(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _normalize_amount(raw: str) -> Optional[float]:
    if raw is None:
        return None
    cleaned = raw.strip().replace(" ", "")
    # ``1,234.56`` or ``1.234,56`` -- assume the final separator is decimal.
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", "")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if value <= 0:
        return None
    return round(value, 2)


def _detect_currency(text: str, symbol: str = "") -> str:
    symbol = (symbol or "").strip()
    upper = text.upper()
    if symbol in _SYMBOL_CURRENCIES:
        return _SYMBOL_CURRENCIES[symbol]
    if symbol in _AMBIGUOUS_DOLLAR:
        # Resolve a bare ``$`` from nearby ISO context; otherwise default USD.
        for code in ("CAD", "AUD", "USD"):
            if code in upper:
                return code
        return "USD"
    for code in _KNOWN_CURRENCIES:
        if re.search(rf"\b{code}\b", upper):
            return code
    return ""


def _attr_map(tag: str) -> dict:
    attrs: dict[str, str] = {}
    for match in _ATTR_RE.finditer(tag):
        key = match.group(1).lower()
        value = match.group(3) or match.group(4) or match.group(5) or ""
        attrs[key] = _html.unescape(value)
    return attrs


def _iter_jsonld(html: str) -> Iterable[dict]:
    for block in _JSONLD_RE.findall(html or ""):
        raw = _html.unescape(block.strip())
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        yield from _walk_json(data)


def _walk_json(node) -> Iterable[dict]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_json(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_json(item)


def _type_names(node: dict) -> list[str]:
    raw = node.get("@type")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str):
        return [raw]
    return []


def _extract_identity_texts(node: dict) -> list[str]:
    texts: list[str] = []

    def add(value):
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            name = value.get("name")
            if isinstance(name, str):
                texts.append(name)

    for key in ("name", "sku", "mpn", "gtin", "gtin13", "gtin8", "productID"):
        add(node.get(key))
    add(node.get("brand"))
    return texts


def _alnum(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _model_tokens(value: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", (value or "").lower())
    # Strong model tokens contain a digit (e.g. "wh1000xm5", "xm5", "iphone15").
    return {token for token in tokens if any(ch.isdigit() for ch in token)}


def _identity_conflicts(product_title: str, identity_texts: list[str]) -> bool:
    """True when the page clearly describes a *different* model than requested."""
    wanted = _alnum(product_title)
    if not wanted:
        return False
    wanted_tokens = _model_tokens(product_title)
    found_tokens: set[str] = set()
    for text in identity_texts:
        normalized = _alnum(text)
        if len(normalized) >= 5 and (normalized in wanted or wanted in normalized):
            return False  # a strong identity match on the same page
        found_tokens |= _model_tokens(text)
    if not wanted_tokens or not found_tokens:
        return False
    # Require a shared digit-bearing token; otherwise the page is a different SKU.
    return wanted_tokens.isdisjoint(found_tokens)


def _parse_valid_until(value) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _offer_from_node(offer: dict) -> dict:
    return {
        "amount": _normalize_amount(str(offer.get("price")))
        if offer.get("price") is not None
        else None,
        "low": _normalize_amount(str(offer.get("lowPrice")))
        if offer.get("lowPrice") is not None
        else None,
        "high": _normalize_amount(str(offer.get("highPrice")))
        if offer.get("highPrice") is not None
        else None,
        "currency": str(offer.get("priceCurrency") or "").upper(),
        "valid_until": _parse_valid_until(offer.get("priceValidUntil")),
        "availability": str(offer.get("availability") or ""),
        "url": str(offer.get("url") or ""),
        "seller": _extract_identity_texts({"brand": offer.get("seller")}),
    }


def _structured_offers(html: str) -> tuple[list[dict], list[str], dict]:
    """Return (offers, product_identity_texts, meta)."""
    offers: list[dict] = []
    identity: list[str] = []
    meta: dict = {}
    for node in _iter_jsonld(html):
        types = {t.lower() for t in _type_names(node)}
        raw_offers = node.get("offers")
        is_product = "product" in types or "productgroup" in types
        if not is_product and raw_offers is None:
            continue
        if is_product:
            identity.extend(_extract_identity_texts(node))
            for key in ("priceCurrency", "price"):
                if key in node:
                    meta.setdefault(key, node.get(key))
        offer_nodes = raw_offers if isinstance(raw_offers, list) else [raw_offers]
        for offer in offer_nodes:
            if isinstance(offer, dict):
                offers.append(_offer_from_node(offer))
    return offers, identity, meta


def _meta_prices(html: str) -> tuple[list[dict], str]:
    offers: list[dict] = []
    currency = ""
    for tag in _META_TAG_RE.findall(html or ""):
        attrs = _attr_map(tag)
        key = (
            attrs.get("property")
            or attrs.get("name")
            or attrs.get("itemprop")
            or ""
        ).lower()
        content = attrs.get("content", "")
        if key in {"product:price:amount", "og:price:amount", "price"}:
            amount = _normalize_amount(content)
            if amount is not None:
                offers.append(
                    {"amount": amount, "currency": "", "valid_until": None,
                     "availability": "", "low": None, "high": None}
                )
        elif key in {"product:price:currency", "og:price:currency", "pricecurrency"}:
            currency = content.upper()
    if currency:
        for offer in offers:
            offer["currency"] = offer["currency"] or currency
    return offers, currency


def _microdata_price(html: str) -> Optional[dict]:
    match = _MICRODATA_PRICE_RE.search(html or "")
    if not match:
        return None
    amount = _normalize_amount(match.group(1))
    if amount is None:
        return None
    currency_match = _MICRODATA_CURRENCY_RE.search(html)
    currency = currency_match.group(1).upper() if currency_match else ""
    return {"amount": amount, "currency": currency, "low": None, "high": None,
            "valid_until": None, "availability": ""}


def _labelled_price_type(context: str) -> str:
    lowered = context.lower()
    # A price explicitly labelled as a sale/current price wins over a nearby
    # "was"/MRP figure that also falls inside the context window.
    if any(label in lowered for label in _SALE_PRICE_LABELS):
        return "sale_price"
    if any(label in lowered for label in _LIST_PRICE_LABELS):
        return "list_price"
    return "selling_price"


def _labelled_prices(html: str) -> list[dict]:
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", html or ""))
    results: list[dict] = []
    seen: set[tuple] = set()

    def record(match: re.Match, symbol: str, iso: str):
        amount = _normalize_amount(match.group("amount"))
        if amount is None:
            return
        # Only the text immediately preceding a price can label it; a window that
        # also spans the *next* price would mislabel "MRP $199  Sale $149".
        context = text[max(0, match.start() - 40): match.start()]
        currency = _detect_currency(context, symbol) if symbol else (
            iso.upper() if iso else _detect_currency(context)
        )
        price_type = _labelled_price_type(context)
        key = (amount, currency, price_type)
        if key in seen:
            return
        seen.add(key)
        results.append(
            {"amount": amount, "currency": currency, "price_type": price_type,
             "low": None, "high": None, "valid_until": None, "availability": ""}
        )

    for match in _PRICE_WITH_SYMBOL_RE.finditer(text):
        record(match, match.group("symbol"), "")
    for match in _PRICE_WITH_ISO_RE.finditer(text):
        record(match, "", match.group("iso"))
    for match in _ISO_WITH_PRICE_RE.finditer(text):
        record(match, "", match.group("iso"))
    return results


def _snippet_price(snippet: str) -> Optional[float]:
    if not snippet:
        return None
    match = _PRICE_WITH_SYMBOL_RE.search(snippet) or _PRICE_WITH_ISO_RE.search(snippet)
    if not match:
        return None
    return _normalize_amount(match.group("amount"))


def extract_price_from_html(
    html: str,
    page_url: str,
    *,
    product_title: str = "",
    expected_currency: str = "USD",
    now: Optional[datetime] = None,
) -> PriceEvidence:
    """Extract and validate a price from already-retrieved page HTML."""
    expected_currency = (expected_currency or "USD").upper()
    retrieved_at = _utcnow(now).isoformat()
    evidence = PriceEvidence(source_url=page_url, retrieved_at=retrieved_at)

    structured, identity, _meta = _structured_offers(html)
    meta_offers, _ = _meta_prices(html)
    micro = _microdata_price(html)
    labelled = _labelled_prices(html)

    if product_title and identity and _identity_conflicts(product_title, identity):
        evidence.method = "json_ld"
        evidence.reason = "price found on a page for a different product variant"
        return evidence

    # Aggregate ranges are ambiguous and never verified on their own.
    aggregates = [o for o in structured if o.get("low") is not None or o.get("high") is not None]
    concrete = [o for o in structured if o.get("amount") is not None]
    if not concrete and aggregates:
        low, high = aggregates[0].get("low"), aggregates[0].get("high")
        evidence.method = "json_ld"
        evidence.price_type = "aggregate"
        evidence.currency = aggregates[0].get("currency", "")
        evidence.reason = "source only exposes an aggregate price range"
        if low is not None and high is not None and abs(low - high) < 0.01:
            concrete = [{"amount": low, "currency": aggregates[0].get("currency", ""),
                         "valid_until": None, "availability": "", "low": None, "high": None}]
        else:
            return evidence

    candidate_pool: list[tuple[str, str, list[dict]]] = []
    if concrete:
        candidate_pool.append(("json_ld", "high", concrete))
    if meta_offers:
        candidate_pool.append(("meta", "high", meta_offers))
    if micro:
        candidate_pool.append(("microdata", "high", [micro]))
    if labelled:
        candidate_pool.append(("labelled_text", "medium", labelled))

    if not candidate_pool:
        evidence.method = "none"
        evidence.reason = "source page did not expose a usable price"
        return evidence

    method, confidence, offers = candidate_pool[0]
    evidence.method = method
    evidence.confidence = confidence

    typed = [
        (offer.get("price_type") or "selling_price", round(offer["amount"], 2), offer)
        for offer in offers
        if offer.get("amount") is not None
    ]
    # Prefer the current selling/sale price over a list/MRP figure when a page
    # exposes both (e.g. "MRP $199.99  Sale price $149.99").
    chosen_type = "selling_price"
    for preference in ("selling_price", "sale_price", "list_price"):
        if any(price_type == preference for price_type, _amt, _offer in typed):
            chosen_type = preference
            break

    amounts = {amt for price_type, amt, _offer in typed if price_type == chosen_type}
    if len(amounts) > 1:
        evidence.reason = "source page contained conflicting prices"
        evidence.raw_amount = ", ".join(f"{a:.2f}" for a in sorted(amounts))
        return evidence

    chosen = next(
        offer
        for price_type, _amt, offer in typed
        if price_type == chosen_type
    )
    evidence.amount = round(chosen["amount"], 2)
    evidence.raw_amount = f"{evidence.amount:.2f}"
    evidence.currency = (chosen.get("currency") or _detect_currency(html)).upper()
    evidence.price_type = chosen_type
    evidence.availability = chosen.get("availability", "") or ""

    if not evidence.currency:
        evidence.reason = "could not determine the currency of the extracted price"
        return evidence
    if evidence.currency != expected_currency:
        evidence.reason = (
            f"price is listed in {evidence.currency}, not {expected_currency}"
        )
        return evidence

    valid_until = chosen.get("valid_until")
    if valid_until is not None and valid_until < _utcnow(now):
        evidence.reason = "the source price is marked as no longer valid (stale)"
        return evidence

    evidence.identity = identity[0] if identity else ""
    evidence.verified = True
    evidence.reason = ""
    if method == "labelled_text":
        evidence.notes.append("price taken from clearly labelled page text")
    return evidence


def extract_from_snippet(
    snippet: str,
    page_url: str,
    *,
    expected_currency: str = "USD",
    now: Optional[datetime] = None,
) -> PriceEvidence:
    """Low-confidence price parsed from a search snippet. Never auto-verified."""
    evidence = PriceEvidence(
        source_url=page_url,
        retrieved_at=_utcnow(now).isoformat(),
        method="snippet",
        confidence="low",
    )
    amount = _snippet_price(snippet)
    if amount is None:
        evidence.reason = "no price could be extracted from the product page"
        return evidence
    evidence.amount = amount
    evidence.raw_amount = f"{amount:.2f}"
    evidence.currency = expected_currency
    evidence.reason = "price came from a search snippet, not the source page"
    return evidence


def _is_fetchable(url: str) -> bool:
    if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
        return False
    host = url.split("://", 1)[1].split("/", 1)[0].split("@")[-1].split(":")[0]
    host = host.strip("[]").lower()
    if not host or host in {"localhost"} or host.endswith(_PRIVATE_HOST_SUFFIXES):
        return False
    try:
        literal = ipaddress.ip_address(host)
        return not (
            literal.is_private
            or literal.is_loopback
            or literal.is_link_local
            or literal.is_reserved
        )
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError):
        return True  # let the request itself fail closed
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    return True


def _looks_blocked(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _BLOCKED_MARKERS)


class ProductPageFetcher:
    """Retrieves a product page's HTML with SSRF guards and bounded size."""

    def __init__(
        self,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES,
        user_agent: str = USER_AGENT,
        session: Optional[requests.Session] = None,
    ):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        self.session = session

    def fetch_outcome(self, url: str, *, now: Optional[datetime] = None) -> FetchOutcome:
        """Retrieve a product page, preserving the outcome and failure reason."""
        started = _utcnow(now).isoformat()
        outcome = FetchOutcome(url=url, retrieved_at=started)

        if not _is_fetchable(url):
            outcome.status = "unfetchable"
            outcome.reason = "the source URL is not a publicly retrievable product page"
            return outcome

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            if self.session is not None:
                response = self.session.get(
                    url, headers=headers, timeout=self.timeout, allow_redirects=True
                )
            else:
                response = requests.get(
                    url, headers=headers, timeout=self.timeout, allow_redirects=True
                )
        except requests.Timeout:
            outcome.status = "timeout"
            outcome.reason = (
                f"the source page did not respond within {self.timeout} seconds"
            )
            return outcome
        except requests.RequestException:
            outcome.status = "network_error"
            outcome.reason = "the source page could not be reached"
            return outcome

        outcome.http_status = response.status_code
        outcome.content_type = (response.headers.get("content-type") or "").lower()

        if response.status_code != 200:
            if response.status_code in {401, 403}:
                outcome.status = "blocked"
                outcome.reason = (
                    f"the source refused access (HTTP {response.status_code})"
                )
            elif response.status_code == 404:
                outcome.status = "http_error"
                outcome.reason = "the source product page was not found (HTTP 404)"
            elif response.status_code >= 500:
                outcome.status = "http_error"
                outcome.reason = (
                    f"the source returned a server error (HTTP {response.status_code})"
                )
            else:
                outcome.status = "http_error"
                outcome.reason = f"the source returned HTTP {response.status_code}"
            return outcome

        if outcome.content_type and "html" not in outcome.content_type:
            outcome.status = "non_html"
            outcome.reason = (
                f"the source returned '{outcome.content_type}', not an HTML product page"
            )
            return outcome

        text = response.text or ""
        if _looks_blocked(text):
            outcome.status = "blocked"
            outcome.reason = "the source returned an anti-bot or access-denied page"
            return outcome

        outcome.status = "retrieved"
        outcome.html = text[: self.max_bytes]
        return outcome

    def fetch(self, url: str) -> Optional[str]:
        """Backwards-compatible helper returning only HTML (or ``None``)."""
        return self.fetch_outcome(url).html
