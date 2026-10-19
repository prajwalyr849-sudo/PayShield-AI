"""Server-side purchase-context binding for PayShield checkout attempts.

The browser supplies references and approval; it never supplies the authoritative
commercial facts.  A purchase context is a canonical, immutable snapshot of the
approved transaction.  Its fingerprint lets PayShield detect tampering with any
protected field before PayPal capture.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

# Fields that are protected: any change requires a new approved decision.
PROTECTED_FIELDS = (
    "product_reference",
    "variant",
    "merchant",
    "offer_reference",
    "quantity",
    "unit_price",
    "total_amount",
    "currency",
    "shipping_amount",
    "user_id",
    "constraints",
    "evidence_references",
    "evidence_version",
    "paypal_order_id",
    "payment_attempt",
)


def canonical_money(value: Any) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Invalid monetary value.")
    if not amount.is_finite() or amount < 0:
        raise ValueError("Monetary value must be finite and non-negative.")
    return f"{amount:.2f}"


def canonical_context(payload: Mapping[str, Any]) -> str:
    """Return a sorted, stable JSON encoding of a purchase context."""
    normalized = {
        "product_reference": str(payload.get("product_reference", "")).strip(),
        "variant": str(payload.get("variant", "")).strip(),
        "merchant": str(payload.get("merchant", "")).strip(),
        "offer_reference": str(payload.get("offer_reference", "")).strip(),
        "quantity": int(payload.get("quantity", 1)),
        "unit_price": canonical_money(payload.get("unit_price", "0")),
        "total_amount": canonical_money(payload.get("total_amount", "0")),
        "currency": str(payload.get("currency", "USD")).strip().upper(),
        "shipping_amount": canonical_money(payload.get("shipping_amount", "0")),
        "user_id": str(payload.get("user_id", "")).strip(),
        "constraints": payload.get("constraints") or {},
        "evidence_references": sorted(str(x) for x in (payload.get("evidence_references") or [])),
        "evidence_version": str(payload.get("evidence_version", "")).strip(),
        "paypal_order_id": str(payload.get("paypal_order_id", "")).strip(),
        "payment_attempt": str(payload.get("payment_attempt", "")).strip(),
    }
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint_context(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_context(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PurchaseContext:
    product_reference: str
    variant: str = ""
    merchant: str = ""
    offer_reference: str = ""
    quantity: int = 1
    unit_price: str = "0.00"
    total_amount: str = "0.00"
    currency: str = "USD"
    shipping_amount: str = "0.00"
    user_id: str = ""
    approved_intent: bool = False
    constraints: dict = field(default_factory=dict)
    evidence_references: tuple = field(default_factory=tuple)
    evidence_version: str = ""
    paypal_order_id: str = ""
    payment_attempt: str = ""
    context_version: int = 1

    def __post_init__(self):
        object.__setattr__(self, "unit_price", canonical_money(self.unit_price))
        object.__setattr__(self, "total_amount", canonical_money(self.total_amount))
        object.__setattr__(self, "shipping_amount", canonical_money(self.shipping_amount))
        object.__setattr__(self, "currency", self.currency.upper())
        object.__setattr__(self, "evidence_references", tuple(sorted(self.evidence_references)))

    @property
    def fingerprint(self) -> str:
        return fingerprint_context(asdict(self))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["evidence_references"] = list(self.evidence_references)
        return data

    def matches(self, other: "PurchaseContext") -> tuple[bool, list[str]]:
        """Compare protected fields; return (ok, changed_fields)."""
        changed: list[str] = []
        for name in PROTECTED_FIELDS:
            left = getattr(self, name, None)
            right = getattr(other, name, None)
            if name in ("unit_price", "total_amount", "shipping_amount"):
                left = canonical_money(left)
                right = canonical_money(right)
            if name == "currency":
                left = str(left).upper()
                right = str(right).upper()
            if name == "evidence_references":
                left = tuple(sorted(left or ()))
                right = tuple(sorted(right or ()))
            if left != right:
                changed.append(name)
        # Fingerprint must also match for exact equality.
        if self.fingerprint != other.fingerprint:
            if "fingerprint" not in changed:
                changed.append("fingerprint")
        return (not changed, changed)


def verify_context(stored: PurchaseContext, current: PurchaseContext) -> tuple[bool, list[str]]:
    return stored.matches(current)