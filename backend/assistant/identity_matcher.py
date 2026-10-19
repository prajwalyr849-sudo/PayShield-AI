"""Deterministic product identity matching for live product evidence.

A shopper's request ("iPhone 17") must never be silently satisfied by a
different product ("restored iPhone 14 Pro Max"). This module compares the
attributes that are *explicitly stated* on both sides and produces one of four
outcomes:

* ``MATCH``          - every comparable attribute agrees.
* ``PARTIAL_MATCH``  - the same product family/model, but a soft attribute
                       differs (storage, variant, region) or the candidate's
                       condition differs from a silent request.
* ``MISMATCH``       - a hard attribute (brand, family, generation/model, or
                       condition) provably conflicts.
* ``UNKNOWN``        - too little explicit information to decide.

Matching never invents attributes. A dimension that is not stated on both sides
is treated as unknown rather than assumed to agree. The outcomes are advisory
inputs to the UI and to PayShield policy; they never fabricate a fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

MATCH = "MATCH"
PARTIAL_MATCH = "PARTIAL_MATCH"
MISMATCH = "MISMATCH"
UNKNOWN = "UNKNOWN"

OUTCOMES = (MATCH, PARTIAL_MATCH, MISMATCH, UNKNOWN)

# Recognised brands (kept small and explicit; absence simply means "unknown").
# Product families such as "iphone"/"galaxy"/"pixel" are NOT brands.
_BRANDS = (
    "apple", "samsung", "google", "sony", "bose", "microsoft", "dell",
    "hp", "lenovo", "asus", "acer", "nike", "adidas", "xiaomi", "oneplus", "oppo",
    "huawei", "motorola", "nvidia", "amd", "intel", "logitech", "razer", "corsair",
    "anker", "jbl", "sennheiser", "beats", "canon", "nikon", "garmin", "fitbit",
    "dyson", "lg", "toshiba", "msi", "meta", "valve", "sandisk", "seagate",
    "western digital", "crucial", "kingston", "brother", "epson", "nintendo",
)

# Product families. A shared family with a conflicting model is a hard mismatch.
_FAMILIES = (
    "iphone", "ipad", "macbook", "imac", "mac mini", "airpods", "apple watch",
    "galaxy", "pixel", "pixelbook", "wh-1000xm", "wf-1000xm", "surface", "thinkpad",
    "ideapad", "pavilion", "xps", "inspiron", "macbook air", "macbook pro",
    "playstation", "xbox", "switch", "kindle", "fire tv", "echo", "pixel buds",
)

# Multi-word variants first so "pro max" is not reduced to "max".
_VARIANTS = (
    "pro max", "pro", "max", "plus", "ultra", "mini", "se", "air", "lite", "fe",
    "fold", "flip", "note", "prime", "titanium", "slim",
)

_REFURBISHED = (
    "refurbished", "refurb", "renewed", "restored", "certified pre-owned",
    "pre-owned", "preowned", "open-box", "open box", "reconditioned",
)
_USED = ("used", "second hand", "second-hand", "secondhand", "pre loved", "pre-loved")
_NEW = ("brand new", "sealed", "new", "unopened", "in box")

_REGION_TOKENS = (
    "global", "international", "us version", "usa", "eu version", "uk version",
    "dual sim", "esim", "physical sim", "japan", "china", "india",
)

_STORAGE_RE = re.compile(r"\b(\d{1,4})\s?(gb|tb)\b", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_HYPHEN_RE = re.compile(r"[-_/]+")
_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("’", "'")
    return _WS_RE.sub(" ", text).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None


@dataclass
class ProductIdentity:
    """Explicit, comparable attributes parsed from a product string."""

    brand: str = ""
    family: str = ""
    model_tokens: set[str] = field(default_factory=set)
    variant: str = ""
    storage: str = ""
    condition: str = ""
    region: str = ""

    def is_empty(self) -> bool:
        return not any(
            (self.brand, self.family, self.model_tokens, self.variant,
             self.storage, self.condition, self.region)
        )


def parse_identity(text: str) -> ProductIdentity:
    """Parse explicit identity attributes from a product title or query."""
    normalized = _normalize(text)
    identity = ProductIdentity()
    if not normalized:
        return identity

    # Condition (refurbished/used/new).
    for phrase in _REFURBISHED:
        if _contains_phrase(normalized, phrase):
            identity.condition = "refurbished"
            break
    if not identity.condition:
        for phrase in _USED:
            if _contains_phrase(normalized, phrase):
                identity.condition = "used"
                break
    if not identity.condition:
        for phrase in _NEW:
            if _contains_phrase(normalized, phrase):
                identity.condition = "new"
                break

    # Storage capacity.
    storage = _STORAGE_RE.search(normalized)
    if storage:
        identity.storage = f"{storage.group(1)}{storage.group(2).lower()}"

    # Family (longest phrase wins so "macbook air" beats "macbook").
    for family in sorted(_FAMILIES, key=len, reverse=True):
        if _contains_phrase(normalized, family):
            identity.family = family
            break

    # Brand.
    for brand in _BRANDS:
        if _contains_phrase(normalized, brand):
            identity.brand = brand
            break

    # Variant.
    for variant in _VARIANTS:
        if _contains_phrase(normalized, variant):
            identity.variant = variant
            break

    # Region.
    for region in _REGION_TOKENS:
        if _contains_phrase(normalized, region):
            identity.region = region
            break

    identity.model_tokens = _model_tokens(normalized, identity.family)
    return identity


def _storage_tokens(normalized: str) -> set[str]:
    compact = _HYPHEN_RE.sub("", normalized)
    return {f"{m.group(1)}{m.group(2).lower()}" for m in _STORAGE_RE.finditer(compact)}


def _model_tokens(normalized: str, family: str) -> set[str]:
    """Strong model designators: letter+digit tokens, plus family generation."""
    compact = _HYPHEN_RE.sub("", normalized)
    storage = _storage_tokens(compact)
    tokens = _TOKEN_RE.findall(compact)
    strong = {
        token
        for token in tokens
        if token not in storage
        and any(char.isdigit() for char in token)
        and any(char.isalpha() for char in token)
    }
    # A bare generation number is only a model token when it directly follows a
    # known family ("iphone 17" -> 17), which avoids treating budgets as models.
    if family:
        family_compact = _HYPHEN_RE.sub("", family)
        for match in re.finditer(
            re.escape(family_compact) + r"\s*(\d{1,3})(?![0-9])", compact
        ):
            strong.add(match.group(1))
    return strong


@dataclass
class IdentityMatch:
    """The result of comparing a requested identity against a candidate."""

    outcome: str = UNKNOWN
    reasons: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "identity_match": self.outcome,
            "identity_reasons": list(self.reasons),
            "identity_matched": list(self.matched),
            "identity_conflicts": list(self.conflicts),
        }


def match_identity(
    requested_text: str, candidate_text: str
) -> IdentityMatch:
    """Compare a requested product string with a candidate product string."""
    requested = parse_identity(requested_text)
    candidate = parse_identity(candidate_text)

    matched: list[str] = []
    conflicts: list[str] = []
    reasons: list[str] = []
    hard_conflict = False
    soft_conflict = False
    compared = 0

    def note(reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)

    # --- Condition (hard) -------------------------------------------------
    if requested.condition and candidate.condition:
        compared += 1
        if requested.condition == candidate.condition:
            matched.append(f"condition={candidate.condition}")
        else:
            hard_conflict = True
            conflicts.append(
                f"condition differs: requested {requested.condition}, "
                f"candidate {candidate.condition}"
            )
    elif candidate.condition in {"refurbished", "used"}:
        soft_conflict = True
        note(
            f"candidate condition is '{candidate.condition}' but the request "
            "did not specify a condition"
        )

    # --- Brand (hard) -----------------------------------------------------
    if requested.brand and candidate.brand:
        compared += 1
        if requested.brand == candidate.brand:
            matched.append(f"brand={candidate.brand}")
        else:
            hard_conflict = True
            conflicts.append(
                f"brand differs: requested {requested.brand}, "
                f"candidate {candidate.brand}"
            )

    # --- Family (hard) ----------------------------------------------------
    if requested.family and candidate.family:
        compared += 1
        if requested.family == candidate.family:
            matched.append(f"family={candidate.family}")
        else:
            hard_conflict = True
            conflicts.append(
                f"family differs: requested {requested.family}, "
                f"candidate {candidate.family}"
            )

    # --- Model / generation (hard) ---------------------------------------
    if requested.model_tokens and candidate.model_tokens:
        compared += 1
        if requested.model_tokens & candidate.model_tokens:
            matched.append(
                "model=" + ",".join(sorted(requested.model_tokens & candidate.model_tokens))
            )
        else:
            hard_conflict = True
            conflicts.append(
                "model/generation differs: requested "
                f"{','.join(sorted(requested.model_tokens))}, candidate "
                f"{','.join(sorted(candidate.model_tokens))}"
            )

    # --- Variant (soft) ---------------------------------------------------
    if requested.variant and candidate.variant:
        compared += 1
        if requested.variant == candidate.variant:
            matched.append(f"variant={candidate.variant}")
        else:
            soft_conflict = True
            conflicts.append(
                f"variant differs: requested {requested.variant}, "
                f"candidate {candidate.variant}"
            )
    elif requested.variant and not candidate.variant:
        soft_conflict = True
        note(f"requested variant '{requested.variant}' is not stated by the candidate")

    # --- Storage (soft) ---------------------------------------------------
    if requested.storage and candidate.storage:
        compared += 1
        if requested.storage == candidate.storage:
            matched.append(f"storage={candidate.storage}")
        else:
            soft_conflict = True
            conflicts.append(
                f"storage differs: requested {requested.storage}, "
                f"candidate {candidate.storage}"
            )

    # --- Region (soft) ----------------------------------------------------
    if requested.region and candidate.region:
        compared += 1
        if requested.region == candidate.region:
            matched.append(f"region={candidate.region}")
        else:
            soft_conflict = True
            conflicts.append(
                f"region differs: requested {requested.region}, "
                f"candidate {candidate.region}"
            )

    if hard_conflict:
        return IdentityMatch(MISMATCH, conflicts or reasons, matched, conflicts)
    if soft_conflict:
        return IdentityMatch(PARTIAL_MATCH, conflicts or reasons, matched, conflicts)
    if compared > 0 and matched:
        return IdentityMatch(MATCH, reasons, matched, conflicts)
    return IdentityMatch(UNKNOWN, reasons, matched, conflicts)


def summarize_match(identity_match: IdentityMatch) -> str:
    """A short, safe human summary of an identity match result."""
    if identity_match.outcome == MATCH:
        return "Product identity matches the request."
    if identity_match.outcome == PARTIAL_MATCH:
        detail = identity_match.conflicts[0] if identity_match.conflicts else "minor attribute differences"
        return f"Partial product match: {detail}."
    if identity_match.outcome == MISMATCH:
        detail = identity_match.conflicts[0] if identity_match.conflicts else "conflicting attributes"
        return f"Product mismatch: {detail}."
    return "Product identity could not be verified from the available evidence."


def iter_conflicts(identity_match: IdentityMatch) -> Iterable[str]:
    return tuple(identity_match.conflicts)
