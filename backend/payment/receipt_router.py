"""Read-only API for persistent transaction receipts."""

import os

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.payment.receipts import ReceiptStore

router = APIRouter(prefix="/receipts", tags=["Receipts"])


def get_receipt_store() -> ReceiptStore:
    return ReceiptStore(
        os.getenv("PAYSHIELD_RECEIPT_DB_PATH")
        or os.getenv("PAYSHIELD_DB_PATH")
        or "payshield_payments.sqlite3"
    )


def _authorize_receipt(receipt: dict, current_user: User) -> dict:
    """Return the receipt only if it belongs to the authenticated user.

    Unknown or unowned receipts raise the same 404 as a missing receipt so the
    API never reveals whether another user's transaction exists.
    """
    owner = receipt.get("user_id") or ""
    if not owner or owner != current_user.id:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    return receipt


@router.get("")
def list_receipts(
    limit: int = Query(default=50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    store: ReceiptStore = Depends(get_receipt_store),
):
    """Return the authenticated user's persistent transaction receipts."""
    records = store.list_receipts(user_id=current_user.id, limit=limit)
    return {"receipts": records, "count": len(records)}


@router.get("/order/{order_id}")
def get_receipt_by_order_id(
    order_id: str,
    current_user: User = Depends(get_current_user),
    store: ReceiptStore = Depends(get_receipt_store),
):
    """Return the receipt bound to a PayPal order the user is allowed to see."""
    receipt = store.get_receipt_by_order_id(order_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    return _authorize_receipt(receipt, current_user)


@router.get("/decision/{decision_reference}")
def get_receipt_by_decision(
    decision_reference: str,
    current_user: User = Depends(get_current_user),
    store: ReceiptStore = Depends(get_receipt_store),
):
    """Return the receipt bound to a Guard Buy decision the user may see."""
    receipt = store.get_receipt_by_decision_reference(decision_reference)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    return _authorize_receipt(receipt, current_user)


@router.get("/{receipt_id}")
def get_receipt(
    receipt_id: str,
    current_user: User = Depends(get_current_user),
    store: ReceiptStore = Depends(get_receipt_store),
):
    """Return a single receipt the user is allowed to see."""
    receipt = store.get_receipt(receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    return _authorize_receipt(receipt, current_user)
