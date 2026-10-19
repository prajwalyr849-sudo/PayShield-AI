"""Route-level tests for the /receipts API used by the frontend."""

from fastapi.testclient import TestClient

from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.main import app
from backend.payment.receipt_router import get_receipt_store
from backend.payment.receipts import ReceiptStatus, ReceiptStore


def make_client(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.db")
    user = User(id="user-1", primary_email="user-1@example.com", full_name="User One")

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_receipt_store] = lambda: store
    return TestClient(app), store


def teardown_function():
    app.dependency_overrides.clear()


def test_receipts_list_route_is_registered_and_returns_json(tmp_path):
    client, store = make_client(tmp_path)
    store.create_receipt(status=ReceiptStatus.COMPLETED, user_id="user-1", order_id="ORDER-1")
    store.create_receipt(status=ReceiptStatus.BLOCKED, user_id="user-2", order_id="ORDER-2")

    response = client.get("/receipts?limit=50")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"receipts", "count"}
    assert payload["count"] == 1
    assert payload["receipts"][0]["user_id"] == "user-1"


def test_receipts_list_returns_empty_state_with_200(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.get("/receipts?limit=50")

    assert response.status_code == 200
    assert response.json() == {"receipts": [], "count": 0}


def test_receipts_list_requires_authentication(tmp_path):
    client, _ = make_client(tmp_path)
    app.dependency_overrides.pop(get_current_user, None)

    response = client.get("/receipts?limit=50")

    assert response.status_code == 401
