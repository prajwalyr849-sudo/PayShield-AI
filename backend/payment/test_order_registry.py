import pytest

from backend.payment.order_registry import OrderRegistry


def test_new_order_can_be_processed():
    registry = OrderRegistry()

    assert registry.mark_processed("ORDER-001") is True

def test_duplicate_order_is_rejected(tmp_path):
    registry = OrderRegistry(tmp_path / "test.db")

    assert registry.mark_processed("ORDER-001") is True
    assert registry.mark_processed("ORDER-001") is False


def test_processed_order_can_be_checked():
    registry = OrderRegistry()

    registry.mark_processed("ORDER-001")

    assert registry.is_processed("ORDER-001") is True
    assert registry.is_processed("ORDER-002") is False


def test_empty_order_id_is_rejected():
    registry = OrderRegistry()

    with pytest.raises(ValueError):
        registry.mark_processed("")

def test_new_order_can_be_processed(tmp_path):
    registry = OrderRegistry(tmp_path / "test.db")

    assert registry.mark_processed("ORDER-001") is True

def test_processed_order_survives_restart(tmp_path):
    db_path = tmp_path / "persistent.db"

    first_registry = OrderRegistry(db_path)
    assert first_registry.mark_processed("ORDER-001") is True

    second_registry = OrderRegistry(db_path)
    assert second_registry.is_processed("ORDER-001") is True
    assert second_registry.mark_processed("ORDER-001") is False


def test_order_cannot_be_reserved_twice(tmp_path):
    from backend.payment.order_registry import OrderRegistry

    registry = OrderRegistry(db_path=str(tmp_path / "orders.db"))
    order_id = "ORDER-ATOMIC-1"

    first_reservation = registry.reserve_order(order_id)
    second_reservation = registry.reserve_order(order_id)

    assert first_reservation is True
    assert second_reservation is False


def test_completed_order_cannot_be_reserved_again(tmp_path):
    from backend.payment.order_registry import OrderRegistry

    registry = OrderRegistry(db_path=str(tmp_path / "orders.db"))
    order_id = "ORDER-RECOVERY-4"

    assert registry.reserve_order(order_id) is True
    assert registry.complete_reservation(order_id) is True

    assert registry.is_processed(order_id) is True
    assert registry.reserve_order(order_id) is False


def test_checkout_intent_survives_restart(tmp_path):
    db_path = tmp_path / "checkout.db"
    first_registry = OrderRegistry(db_path)
    assert first_registry.register_checkout_order(
        "ORDER-INTENT-1",
        "25.00",
        "USD",
        "agent-001",
        "services",
        "Sandbox merchant",
        "sandbox-user",
    ) is True

    second_registry = OrderRegistry(db_path)
    assert second_registry.get_checkout_order("ORDER-INTENT-1") == {
        "order_id": "ORDER-INTENT-1",
        "amount": "25.00",
        "currency": "USD",
        "agent_id": "agent-001",
        "category": "services",
        "merchant_name": "Sandbox merchant",
        "user_id": "sandbox-user",
    }