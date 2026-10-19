"""Tests for the persistent transaction receipt store."""

import pytest

from backend.payment.receipts import (
    ReceiptStatus,
    ReceiptStore,
    build_snapshots,
    count_receipts,
)


def test_receipt_persists_across_restart(tmp_path):
    db_path = tmp_path / "receipts.db"
    first = ReceiptStore(db_path)
    receipt_id = first.create_receipt(
        status=ReceiptStatus.COMPLETED,
        transaction_id="TXN-1",
        order_id="ORDER-1",
        user_id="user-1",
        agent_id="agent-001",
        merchant_name="Shop",
        merchant_category="electronics",
        amount="42.00",
        currency="USD",
        decision="ALLOW",
        payment_status_raw="COMPLETED",
        reason="PayPal capture confirmed.",
        risk_score=5,
        risk_level="LOW",
        snapshots=build_snapshots(product={"title": "Widget"}),
    )

    second = ReceiptStore(db_path)
    record = second.get_receipt(receipt_id)

    assert record is not None
    assert record["status"] == ReceiptStatus.COMPLETED
    assert record["amount"] == "42.00"
    assert record["currency"] == "USD"
    assert record["snapshots"]["product"]["title"] == "Widget"
    assert record["events"][0]["status"] == ReceiptStatus.COMPLETED


def test_receipt_lookup_by_order_and_user(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.db")
    store.create_receipt(
        status=ReceiptStatus.PENDING,
        order_id="ORDER-2",
        user_id="user-a",
    )
    store.create_receipt(
        status=ReceiptStatus.BLOCKED,
        user_id="user-b",
    )

    assert store.get_receipt_by_order_id("ORDER-2")["user_id"] == "user-a"
    assert store.get_receipt_by_order_id("MISSING") is None
    assert len(store.list_receipts(user_id="user-a")) == 1
    assert len(store.list_receipts()) == 2


def test_receipt_snapshots_are_immutable_across_status_updates(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.db")
    receipt_id = store.create_receipt(
        status=ReceiptStatus.PENDING,
        order_id="ORDER-3",
        user_id="user-1",
        snapshots=build_snapshots(product={"title": "Original", "price": 10.0}),
    )

    store.update_receipt(
        receipt_id,
        status=ReceiptStatus.COMPLETED,
        capture_id="CAP-1",
        reason="PayPal capture confirmed.",
        event={"source": "capture"},
    )

    record = store.get_receipt(receipt_id)
    assert record["status"] == ReceiptStatus.COMPLETED
    assert record["capture_id"] == "CAP-1"
    # The historical product snapshot must not change.
    assert record["snapshots"]["product"]["title"] == "Original"
    assert [event["status"] for event in record["events"] if event.get("status")] == [
        ReceiptStatus.PENDING,
        ReceiptStatus.COMPLETED,
    ]


def test_create_receipt_is_idempotent_by_order_id(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.db")
    first = store.create_receipt(
        status=ReceiptStatus.PENDING, order_id="ORDER-4"
    )
    second = store.create_receipt(
        status=ReceiptStatus.COMPLETED, order_id="ORDER-4"
    )

    assert first == second
    assert count_receipts(str(tmp_path / "receipts.db")) == 1


def test_create_receipt_is_idempotent_by_idempotency_key(tmp_path):
    """Integration outcomes without an order_id rely on the idempotency key."""
    store = ReceiptStore(tmp_path / "receipts.db")
    first = store.create_receipt(
        status=ReceiptStatus.BLOCKED,
        transaction_id="TXN-INTEG-DUP",
        idempotency_key="purchase:TXN-INTEG-DUP",
    )
    second = store.create_receipt(
        status=ReceiptStatus.BLOCKED,
        transaction_id="TXN-INTEG-DUP",
        idempotency_key="purchase:TXN-INTEG-DUP",
    )

    assert first == second
    assert count_receipts(str(tmp_path / "receipts.db")) == 1


def test_unknown_status_is_rejected(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.db")
    with pytest.raises(ValueError):
        store.create_receipt(status="NOT_A_STATUS")


def test_status_vocabulary_covers_all_required_outcomes():
    required = {
        "COMPLETED",
        "PENDING",
        "FAILED",
        "CANCELLED",
        "BLOCKED",
        "REVIEW_REQUIRED",
        "EXPIRED",
        "REFUNDED",
        "PARTIALLY_REFUNDED",
        "AWAITING_BUYER_APPROVAL",
        "AUTHORIZED",
        "CAPTURE_PENDING",
    }
    assert required == set(ReceiptStatus.ALL)
