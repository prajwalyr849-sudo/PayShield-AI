import pytest

from backend.payshield.order_integrity import (
    approve_order,
    verify_order,
)


def test_approved_order_verifies():
    approved = approve_order(
        "TXN-001", "500.00", "INR", "ALLOW"
    )

    assert verify_order(
        approved, "TXN-001", "500.00", "INR"
    )


def test_modified_amount_is_rejected():
    approved = approve_order(
        "TXN-001", "500.00", "INR", "ALLOW"
    )

    assert not verify_order(
        approved, "TXN-001", "900.00", "INR"
    )


def test_modified_currency_is_rejected():
    approved = approve_order(
        "TXN-001", "500.00", "INR", "ALLOW"
    )

    assert not verify_order(
        approved, "TXN-001", "500.00", "USD"
    )


def test_review_order_cannot_be_verified():
    approved = approve_order(
        "TXN-001", "500.00", "INR", "REVIEW"
    )

    assert not verify_order(
        approved, "TXN-001", "500.00", "INR"
    )


def test_zero_amount_is_rejected():
    with pytest.raises(ValueError):
        approve_order(
            "TXN-001", "0", "INR", "ALLOW"
        )