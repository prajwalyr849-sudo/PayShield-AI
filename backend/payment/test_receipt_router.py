"""Tests for the receipt router authorization boundaries."""

import tempfile

import pytest
from fastapi import HTTPException

from backend.auth.models import User
from backend.payment.receipt_router import (
    get_receipt,
    get_receipt_by_decision,
    get_receipt_by_order_id,
    list_receipts,
)
from backend.payment.receipts import ReceiptStatus, ReceiptStore


def make_user(user_id: str) -> User:
    return User(
        id=user_id,
        primary_email=f"{user_id}@example.com",
        full_name="Test User",
    )


def make_store(tmp_path):
    db_path = tmp_path / "receipts.db"
    return ReceiptStore(db_path)


def test_list_receipts_returns_only_authenticated_user(tmp_path):
    store = make_store(tmp_path)
    store.create_receipt(status=ReceiptStatus.COMPLETED, user_id="user-a")
    store.create_receipt(status=ReceiptStatus.BLOCKED, user_id="user-b")

    result = list_receipts(limit=50, current_user=make_user("user-a"), store=store)
    assert result["count"] == 1
    assert result["receipts"][0]["user_id"] == "user-a"


def test_get_receipt_returns_404_for_other_user(tmp_path):
    store = make_store(tmp_path)
    receipt_id = store.create_receipt(status=ReceiptStatus.COMPLETED, user_id="owner-1")

    with pytest.raises(HTTPException) as exc:
        get_receipt(receipt_id=receipt_id, current_user=make_user("owner-2"), store=store)
    assert exc.value.status_code == 404


def test_get_receipt_returns_404_when_owner_missing(tmp_path):
    store = make_store(tmp_path)
    receipt_id = store.create_receipt(status=ReceiptStatus.COMPLETED, user_id="")

    with pytest.raises(HTTPException) as exc:
        get_receipt(receipt_id=receipt_id, current_user=make_user("owner-x"), store=store)
    assert exc.value.status_code == 404


def test_get_receipt_by_order_id_allows_owner(tmp_path):
    store = make_store(tmp_path)
    store.create_receipt(status=ReceiptStatus.COMPLETED, user_id="owner-1", order_id="ORDER-1")

    result = get_receipt_by_order_id(
        order_id="ORDER-1",
        current_user=make_user("owner-1"),
        store=store,
    )
    assert result["order_id"] == "ORDER-1"
    assert result["user_id"] == "owner-1"


def test_get_receipt_by_decision_rejects_other_user(tmp_path):
    store = make_store(tmp_path)
    store.create_receipt(
        status=ReceiptStatus.REVIEW_REQUIRED,
        user_id="owner-1",
        decision_reference="DEC-1",
    )

    with pytest.raises(HTTPException) as exc:
        get_receipt_by_decision(
            decision_reference="DEC-1",
            current_user=make_user("owner-2"),
            store=store,
        )
    assert exc.value.status_code == 404
