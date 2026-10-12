from dataclasses import dataclass
from decimal import Decimal,InvalidOperation
import hashlib
import json

@dataclass(frozen=True)
class ApprovedOrder:
    transaction_id:str
    amount:str
    currency:str
    decision:str
    fingerprint:str

def create_fingerprint(
        transaction_id:str,
        amount:str,
        currency:str,
) -> str:
    '''create a stable fingerprint for the approved order'''
    payload = {
        "transaction_id":transaction_id,
        "amount":amount,
        "currency":currency.upper(),
    }
    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",",":"),
    )
    return hashlib.sha256(
        canonical_payload.encode("utf-8")

    ).hexdigest()

def approve_order(
        transaction_id:str,
        amount:str,
        currency:str,
        decision:str,
        
) -> ApprovedOrder:
    '''Bind an order to payshield decision'''
    if not transaction_id.strip():
        raise ValueError("Transaction ID is required")

    if not currency.strip():
        raise ValueError("currency is required")

    try:
        value = Decimal(amount)
    except(InvalidOperation,TypeError,ValueError):
        raise ValueError("Invalid order amount ") from None

    if not value.is_finite() or value <= 0:
        raise ValueError("Order amount must be positive and finite")

    normalized_amount = format(value,"f")
    normalized_currency = currency.upper()

    if decision not in {"ALLOW","REVIEW","BLOCK"}:
        raise ValueError("Invalid PayShield decision")
    fingerprint = create_fingerprint(
        transaction_id,
        normalized_amount,
        normalized_currency,
    )

    return ApprovedOrder(
        transaction_id=transaction_id,
        amount=normalized_amount,
        currency=normalized_currency,
        decision=decision,
        fingerprint=fingerprint,
    )

def verify_order(
        approved:ApprovedOrder,
        transaction_id:str,
        amount:str,
        currency:str,
) -> bool:
    """ Verify order integrity and the original approval"""
    try:
        value = Decimal(amount)

    except(InvalidOperation,TypeError,ValueError):
        return False

    if not value.is_finite() or value <= 0:
        return False
    if approved.decision != "ALLOW":
        return False

    supplied_fingerprint = create_fingerprint(
        transaction_id,
        format(value,"f"),
        currency,
    )

    return(
        supplied_fingerprint == approved.fingerprint
        and transaction_id == approved.transaction_id
        and format(value,"f") == approved.amount
        and currency.upper() == approved.currency
    )