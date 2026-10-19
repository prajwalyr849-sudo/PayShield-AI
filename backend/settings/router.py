"""User preference API.

Only non-security preferences are user-configurable. Mandatory risk, policy and
payment-guard enforcement is served read-only through ``security_controls`` and
can never be changed from here, so a stored preference can never override a
deterministic BLOCK or the payment guards.
"""

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.db import AuthDatabase
from backend.auth.dependencies import get_auth_db, get_current_user
from backend.auth.models import User

router = APIRouter(prefix="/settings", tags=["Settings"])

# field -> validator returning normalized value or raising ValueError
DEFAULTS = {
    "notify_daily_digest": True,
    "notify_realtime_alerts": True,
    "notify_browser": False,
    "risk_alert_threshold": 70,
    "display_currency": "USD",
}

SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "INR"}

# Read-only: enforced by the deterministic engines, never user-editable.
SECURITY_CONTROLS = [
    {
        "key": "policy_enforcement",
        "label": "Policy enforcement",
        "value": "Always on",
        "description": "The deterministic policy engine is authoritative and cannot be disabled.",
    },
    {
        "key": "max_auto_payment",
        "label": "Automatic payment limit",
        "value": "10000 USD",
        "description": "Payments above this amount are not auto-approved by policy.",
    },
    {
        "key": "approval_limit",
        "label": "Approval ceiling",
        "value": "60000 USD",
        "description": "Payments above this amount are blocked and require out-of-band approval.",
    },
    {
        "key": "blocked_categories",
        "label": "Blocked categories",
        "value": "gift_cards",
        "description": "These categories are always blocked regardless of any preference.",
    },
    {
        "key": "ai_advisory",
        "label": "AI authorization",
        "value": "Advisory only",
        "description": "AI output never authorizes, approves or captures a payment.",
    },
]


def _validate(field: str, value):
    if field in ("notify_daily_digest", "notify_realtime_alerts", "notify_browser"):
        if not isinstance(value, bool):
            raise ValueError(f"{field} must be a boolean.")
        return value
    if field == "risk_alert_threshold":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("risk_alert_threshold must be an integer between 0 and 100.")
        if not 0 <= value <= 100:
            raise ValueError("risk_alert_threshold must be between 0 and 100.")
        return value
    if field == "display_currency":
        if not isinstance(value, str):
            raise ValueError("display_currency must be a 3-letter currency code.")
        normalized = value.strip().upper()
        if normalized not in SUPPORTED_CURRENCIES:
            raise ValueError(
                f"display_currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}."
            )
        return normalized
    raise ValueError(f"Unsupported preference: {field}")


def _merged(stored: dict) -> dict:
    merged = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in stored:
            try:
                merged[key] = _validate(key, stored[key])
            except ValueError:
                pass
    return merged


@router.get("/preferences")
def get_preferences(
    current_user: User = Depends(get_current_user),
    auth_db: AuthDatabase = Depends(get_auth_db),
):
    stored = auth_db.get_preferences(current_user.id)
    return {
        "preferences": _merged(stored),
        "stored": stored,
        "defaults": DEFAULTS,
        "editable_fields": sorted(DEFAULTS.keys()),
        "security_controls": SECURITY_CONTROLS,
    }


@router.put("/preferences")
def update_preferences(
    payload: dict,
    current_user: User = Depends(get_current_user),
    auth_db: AuthDatabase = Depends(get_auth_db),
):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Preferences must be a JSON object.")
    updates = {}
    for field, value in payload.items():
        if field not in DEFAULTS:
            raise HTTPException(status_code=422, detail=f"Unsupported preference: {field}")
        try:
            updates[field] = _validate(field, value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    merged = _merged({**auth_db.get_preferences(current_user.id), **updates})
    auth_db.save_preferences(current_user.id, merged)
    return {
        "preferences": merged,
        "stored": merged,
        "editable_fields": sorted(DEFAULTS.keys()),
        "security_controls": SECURITY_CONTROLS,
    }
