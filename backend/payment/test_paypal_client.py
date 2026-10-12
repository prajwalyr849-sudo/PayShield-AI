from unittest.mock import Mock, patch

import pytest
import requests

from backend.payment.paypal_client import PayPalAPIError, PayPalClient


@pytest.fixture
def client():
    return PayPalClient(
        base_url="https://api-m.sandbox.paypal.com",
        timeout=5,
    )


def make_order(
    order_id="ORDER-123",
    status="APPROVED",
    amount="50.00",
    currency="USD",
):
    return {
        "id": order_id,
        "status": status,
        "purchase_units": [
            {
                "amount": {
                    "value": amount,
                    "currency_code": currency,
                }
            }
        ],
    }


def verify_mocked_order(client, order):
    with patch.object(client, "get_order", return_value=order):
        return client.verify_order(
            order_id="ORDER-123",
            expected_amount=50,
            expected_currency="USD",
        )


def test_approved_order_is_verified(client):
    result = verify_mocked_order(client, make_order())

    assert result["verified"] is True
    assert result["status"] == "APPROVED"
    assert result["amount"] == "50.00"
    assert result["currency"] == "USD"
    assert result["order_id"] == "ORDER-123"


def test_get_access_token_uses_sandbox_oauth_request(client):
    response = Mock()
    response.json.return_value = {"access_token": "sandbox-token"}
    client.client_id = "sandbox-client-id"
    client.client_secret = "sandbox-client-secret"

    with patch(
        "backend.payment.paypal_client.requests.post",
        return_value=response,
    ) as post:
        assert client.get_access_token() == "sandbox-token"

    post.assert_called_once_with(
        "https://api-m.sandbox.paypal.com/v1/oauth2/token",
        auth=("sandbox-client-id", "sandbox-client-secret"),
        headers={"Accept": "application/json"},
        data={"grant_type": "client_credentials"},
        timeout=5,
    )
    response.raise_for_status.assert_called_once_with()


def test_get_order_uses_bearer_token_and_sandbox_endpoint(client):
    response = Mock()
    response.json.return_value = make_order()

    with patch.object(
        client,
        "get_access_token",
        return_value="sandbox-token",
    ), patch(
        "backend.payment.paypal_client.requests.get",
        return_value=response,
    ) as get:
        result = client.get_order("ORDER-123")

    assert result == make_order()
    get.assert_called_once_with(
        "https://api-m.sandbox.paypal.com/v2/checkout/orders/ORDER-123",
        headers={
            "Authorization": "Bearer sandbox-token",
            "Content-Type": "application/json",
        },
        timeout=5,
    )
    response.raise_for_status.assert_called_once_with()


def test_create_order_uses_bearer_token_and_return_urls(client):
    response = Mock()
    response.json.return_value = {
        "id": "ORDER-123",
        "status": "CREATED",
        "links": [{"rel": "payer-action", "href": "https://sandbox.test"}],
    }

    with patch.object(
        client,
        "get_access_token",
        return_value="sandbox-token",
    ), patch(
        "backend.payment.paypal_client.requests.post",
        return_value=response,
    ) as post:
        result = client.create_order(
            "50.00",
            "USD",
            return_url="http://localhost:5173/checkout/return",
            cancel_url="http://localhost:5173/checkout?cancelled=1",
        )

    assert result["id"] == "ORDER-123"
    request = post.call_args.kwargs
    assert request["headers"]["Authorization"] == "Bearer sandbox-token"
    assert request["json"]["purchase_units"][0]["amount"] == {
        "currency_code": "USD",
        "value": "50.00",
    }
    assert request["json"]["application_context"] == {
        "return_url": "http://localhost:5173/checkout/return",
        "cancel_url": "http://localhost:5173/checkout?cancelled=1",
    }


def test_inr_order_is_rejected_before_any_paypal_request(client):
    with patch.object(client, "get_access_token") as get_token:
        with pytest.raises(ValueError, match="does not support INR"):
            client.create_order("100.00", "INR")

    get_token.assert_not_called()


def test_paypal_error_preserves_safe_diagnostic_fields(client):
    response = Mock()
    response.status_code = 422
    response.json.return_value = {
        "name": "UNPROCESSABLE_ENTITY",
        "message": "The requested action could not be performed.",
        "debug_id": "sandbox-debug-123",
        "details": [
            {
                "issue": "CURRENCY_NOT_SUPPORTED",
                "description": "Currency code is not currently supported.",
            }
        ],
    }
    response.raise_for_status.side_effect = requests.HTTPError("422")

    with patch.object(client, "get_access_token", return_value="sandbox-token"), patch(
        "backend.payment.paypal_client.requests.post",
        return_value=response,
    ):
        with pytest.raises(PayPalAPIError) as error:
            client.create_order("100.00", "USD")

    assert error.value.name == "UNPROCESSABLE_ENTITY"
    assert error.value.debug_id == "sandbox-debug-123"
    assert "does not support INR" in error.value.safe_detail
    assert "sandbox-token" not in error.value.safe_detail


def test_completed_order_is_rejected(client):
    result = verify_mocked_order(
        client,
        make_order(status="COMPLETED"),
    )

    assert result["verified"] is False


def test_modified_amount_is_rejected(client):
    result = verify_mocked_order(
        client,
        make_order(amount="75.00"),
    )

    assert result["verified"] is False
    assert result["reason"] == "Amount mismatch."


def test_approved_but_uncaptured_order_is_verified(client):
    result = verify_mocked_order(
        client,
        make_order(status="APPROVED"),
    )

    assert result["verified"] is True


def test_wrong_order_id_is_rejected(client):
    result = verify_mocked_order(
        client,
        make_order(order_id="ORDER-DIFFERENT"),
    )

    assert result["verified"] is False
    assert result["reason"] == "PayPal order ID mismatch."


def test_wrong_currency_is_rejected(client):
    result = verify_mocked_order(
        client,
        make_order(currency="EUR"),
    )

    assert result["verified"] is False
    assert result["reason"] == "Currency mismatch."


@pytest.mark.parametrize(
    "amount",
    [0, -1, "invalid", float("inf"), float("nan")],
)
def test_invalid_expected_amount_is_rejected(client, amount):
    with pytest.raises(ValueError):
        client.verify_order(
            order_id="ORDER-123",
            expected_amount=amount,
            expected_currency="USD",
        )


@pytest.mark.parametrize(
    "currency",
    ["", "US", "USDD", "1US", None],
)
def test_invalid_expected_currency_is_rejected(client, currency):
    with pytest.raises(ValueError):
        client.verify_order(
            order_id="ORDER-123",
            expected_amount=50,
            expected_currency=currency,
        )


def test_missing_purchase_units_is_rejected(client):
    order = {
        "id": "ORDER-123",
        "status": "APPROVED",
        "purchase_units": [],
    }

    result = verify_mocked_order(client, order)

    assert result["verified"] is False


def test_multiple_purchase_units_are_rejected(client):
    order = make_order()
    order["purchase_units"].append(order["purchase_units"][0])

    result = verify_mocked_order(client, order)

    assert result["verified"] is False


def test_invalid_order_response_is_rejected(client):
    with patch.object(client, "get_order", return_value=None):
        result = client.verify_order(
            order_id="ORDER-123",
            expected_amount=50,
            expected_currency="USD",
        )

    assert result["verified"] is False


def test_missing_amount_is_rejected(client):
    order = make_order()
    order["purchase_units"][0]["amount"] = {}

    result = verify_mocked_order(client, order)

    assert result["verified"] is False


def test_capture_order_uses_bearer_token_and_request_id(client):
    response = Mock()
    response.json.return_value = {
        "id": "CAPTURE-123",
        "status": "COMPLETED",
    }

    with patch.object(
        client,
        "get_access_token",
        return_value="sandbox-token",
    ), patch(
        "backend.payment.paypal_client.requests.post",
        return_value=response,
    ) as post:
        result = client.capture_order(
            order_id="ORDER-123",
            request_id="payshield-ORDER-123",
        )

    assert result == {
        "id": "CAPTURE-123",
        "status": "COMPLETED",
    }
    post.assert_called_once_with(
        "https://api-m.sandbox.paypal.com/v2/checkout/orders/"
        "ORDER-123/capture",
        headers={
            "Authorization": "Bearer sandbox-token",
            "Content-Type": "application/json",
            "PayPal-Request-Id": "payshield-ORDER-123",
        },
        json={},
        timeout=5,
    )
    response.raise_for_status.assert_called_once_with()