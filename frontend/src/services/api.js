const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");
const PAYMENT_API_URL = import.meta.env.DEV ? "" : API_BASE_URL;

export async function checkPayment({ agent_id, amount, category }) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/check-payment`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        agent_id,
        amount: Number(amount),
        category,
      }),
    });
  } catch {
    throw new Error(
      "Unable to reach PayShield. Check that the backend is running."
    );
  }

  return parseResponse(response, "Payment check");
}

export async function getAuditHistory(limit = 50) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/audit/history?limit=${limit}`, {
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error(
      "Unable to reach PayShield. Check that the backend is running."
    );
  }

  return parseResponse(response, "Audit history");
}

export async function createPayPalOrder(order) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/paypal/orders`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        ...order,
        amount: Number(order.amount),
      }),
    });
  } catch {
    throw new Error(
      "Unable to reach PayShield. Check that the backend is running."
    );
  }

  return parseResponse(response, "PayPal order creation");
}

export async function capturePayPalOrder(orderId) {
  let response;
  try {
    response = await fetch(
      `${PAYMENT_API_URL}/paypal/orders/${encodeURIComponent(orderId)}/capture`,
      {
        method: "POST",
        headers: { Accept: "application/json" },
      }
    );
  } catch {
    throw new Error(
      "Unable to reach PayShield. Check that the backend is running."
    );
  }

  return parseResponse(response, "PayPal payment");
}

async function parseResponse(response, requestName) {
  const text = await response.text();
  let data = null;

  if (text.trim()) {
    try {
      data = JSON.parse(text);
    } catch {
      if (response.ok) {
        throw new Error(`${requestName} returned malformed JSON.`);
      }
    }
  }

  if (!response.ok) {
    const detail =
      typeof data?.detail === "string"
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((item) => item.msg).join(", ")
          : typeof data?.reason === "string"
            ? data.reason
            : text.trim() || null;
    throw new Error(
      detail || `${requestName} failed with status ${response.status}.`
    );
  }

  if (data === null) {
    throw new Error(`${requestName} returned an empty response.`);
  }

  return data;
}