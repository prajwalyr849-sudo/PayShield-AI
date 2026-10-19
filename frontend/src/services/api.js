const metaEnv = (typeof import.meta !== 'undefined' && import.meta.env) ? import.meta.env : {}
const API_BASE_URL = (
  metaEnv.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
).replace(/\/+$/, '')
const PAYMENT_API_URL = metaEnv.DEV ? '' : API_BASE_URL

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
      credentials: "include",
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
      credentials: "include",
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
        credentials: "include",
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

export async function getAuthMe() {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/auth/me`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
  } catch {
    return null;
  }

  if (response.status === 401) {
    return null;
  }
  return parseResponse(response, "User profile");
}

export async function loginDemoUser() {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/auth/demo/login`, {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error("Unable to contact PayShield authentication service.");
  }

  return parseResponse(response, "Demo login");
}

export async function loginWithEmail(email, password) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email, password }),
    });
  } catch {
    throw new Error("Unable to contact PayShield authentication service.");
  }
  return parseResponse(response, "Email sign-in");
}

export async function registerWithEmail(name, email, password, confirm_password) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/auth/register`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ name, email, password, confirm_password }),
    });
  } catch {
    throw new Error("Unable to contact PayShield authentication service.");
  }
  return parseResponse(response, "Account registration");
}

export async function requestPasswordReset(email) {
  const response = await fetch(`${PAYMENT_API_URL}/auth/password-reset/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ email }),
  });
  return parseResponse(response, "Password reset request");
}

export async function initiateOAuthLogin(provider, link = false) {
  let response;
  try {
    response = await fetch(
      `${PAYMENT_API_URL}/auth/${encodeURIComponent(provider)}/login?link=${link}`,
      {
        credentials: "include",
        headers: { Accept: "application/json" },
      }
    );
  } catch {
    throw new Error(
      "Unable to contact PayShield authentication service. Check that the backend is running."
    );
  }
  return parseResponse(response, "OAuth login initiation");
}

export async function getAuthProviderStatus() {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/auth/providers/status`, {
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error("Unable to contact PayShield authentication service.");
  }
  return parseResponse(response, "Authentication provider status");
}

export async function logoutUser() {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error("Unable to contact PayShield authentication service.");
  }
  return parseResponse(response, "Logout");
}

export async function unlinkProviderIdentity(provider) {
  let response;
  try {
    response = await fetch(
      `${PAYMENT_API_URL}/auth/identities/${encodeURIComponent(provider)}/unlink`,
      {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json" },
      }
    );
  } catch {
    throw new Error("Unable to contact PayShield authentication service.");
  }
  return parseResponse(response, "Unlink identity");
}

export async function getAssistantStatus() {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/assistant/status`, {
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error("Unable to contact PayShield assistant service.");
  }
  return parseResponse(response, "Assistant status");
}

export async function getAssistantRecommendations({ query, budget, category, preferred_merchant, currency, country }) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/assistant/recommendations`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        query,
        budget: budget ? Number(budget) : null,
        category: category || null,
        preferred_merchant: preferred_merchant || null,
        currency: currency || 'USD',
        country: country || 'US',
      }),
    });
  } catch {
    throw new Error("Unable to reach PayShield Assistant service.");
  }
  return parseResponse(response, "Shopping recommendations");
}

export async function sendAssistantChat({ query, messages = [], budget, category, currency, country }) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/assistant/chat`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        query,
        messages,
        budget: budget ? Number(budget) : null,
        category: category || null,
        currency: currency || 'USD',
        country: country || 'US',
      }),
    });
  } catch {
    throw new Error("Unable to reach PayShield Assistant service.");
  }
  return parseResponse(response, "Assistant chat");
}

export async function getAssistantProducts(category = "") {
  let response;
  try {
    const url = category ? `${PAYMENT_API_URL}/assistant/products?category=${encodeURIComponent(category)}` : `${PAYMENT_API_URL}/assistant/products`;
    response = await fetch(url, {
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error("Unable to fetch catalog products.");
  }
  return parseResponse(response, "Catalog products");
}

export async function getAssistantProductDetails(productId) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/assistant/products/${encodeURIComponent(productId)}`, {
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error("Unable to fetch product details.");
  }
  return parseResponse(response, "Product details");
}

export async function checkoutAssistantProduct({ product_id, quantity = 1, user_id, idempotency_key }) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/assistant/checkout`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        product_id,
        quantity: Number(quantity),
        user_id: user_id || "demo-user",
        idempotency_key: idempotency_key || `idemp-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      }),
    });
  } catch {
    throw new Error("Unable to contact PayShield Guarded Checkout.");
  }
  return parseResponse(response, "Assistant checkout");
}

export async function rateAssistantProduct({ product_reference, query = "" }) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/assistant/rate`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ product_reference, query }),
    });
  } catch {
    throw new Error("Unable to contact PayShield product rating service.");
  }
  return parseResponse(response, "AI product assessment");
}

export async function guardBuy({ product_reference, quantity = 1, idempotency_key }) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/assistant/guard-buy`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        product_reference,
        quantity: Number(quantity),
        idempotency_key: idempotency_key || undefined,
      }),
    });
  } catch {
    throw new Error("Unable to contact PayShield Guard Buy.");
  }
  return parseResponse(response, "Guard Buy decision");
}

export async function approveGuardBuyReview({ decision_reference, approved = true }) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/assistant/guard-buy/review`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ decision_reference, approved }),
    });
  } catch {
    throw new Error("Unable to contact PayShield review approval service.");
  }
  return parseResponse(response, "Guard Buy review");
}

export async function guardBuyCheckout({ decision_reference, idempotency_key }) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/assistant/guard-buy/checkout`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        decision_reference,
        idempotency_key: idempotency_key || `gb-checkout-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      }),
    });
  } catch {
    throw new Error("Unable to contact PayShield Sandbox checkout.");
  }
  return parseResponse(response, "Sandbox checkout");
}

export async function getReceipts(limit = 50) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/receipts?limit=${encodeURIComponent(limit)}`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error("Unable to fetch receipts.");
  }
  return parseResponse(response, "Receipts");
}

export async function getReceipt(receiptId) {
  if (!receiptId || !receiptId.trim()) {
    throw new Error("Receipt ID is required.");
  }
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/receipts/${encodeURIComponent(receiptId)}`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error("Unable to fetch receipt.");
  }
  return parseResponse(response, "Receipt");
}

export async function getReceiptByOrderId(orderId) {
  if (!orderId || !orderId.trim()) {
    throw new Error("Order ID is required.");
  }
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/receipts/order/${encodeURIComponent(orderId)}`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error("Unable to fetch receipt.");
  }
  return parseResponse(response, "Receipt");
}

export async function getLiveRating({ productReference, sourceUrl, sku, forceRefresh }) {
  if (!productReference || !productReference.trim()) {
    throw new Error("Product reference is required.");
  }
  if (!sourceUrl || !sourceUrl.trim()) {
    throw new Error("Source URL is required.");
  }
  let response;
  try {
    const params = new URLSearchParams({
      product_reference: productReference,
      source_url: sourceUrl,
    });
    if (sku) params.append("sku", sku);
    if (forceRefresh) params.append("force_refresh", "true");
    response = await fetch(
      `${PAYMENT_API_URL}/assistant/rating?${params.toString()}`,
      {
        credentials: "include",
        headers: { Accept: "application/json" },
      }
    );
  } catch {
    throw new Error("Unable to fetch live rating.");
  }
  return parseResponse(response, "Live rating");
}

export async function getSecurityControls() {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/settings/preferences`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error("Unable to load security controls from PayShield.");
  }
  return parseResponse(response, "Security controls");
}

export async function getSettingsPreferences() {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/settings/preferences`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error("Unable to load preferences from PayShield.");
  }
  return parseResponse(response, "Settings preferences");
}

export async function updateSettingsPreferences(preferences) {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/settings/preferences`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(preferences),
    });
  } catch {
    throw new Error("Unable to save preferences to PayShield.");
  }
  return parseResponse(response, "Save settings preferences");
}

export async function getHealth() {
  let response;
  try {
    response = await fetch(`${PAYMENT_API_URL}/health`, {
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error("Unable to reach the PayShield health endpoint.");
  }
  return parseResponse(response, "Health status");
}

export async function parseResponse(response, requestName) {
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
    const structured =
      data?.detail && typeof data.detail === "object" && !Array.isArray(data.detail)
        ? data.detail
        : null;
    const detail =
      structured?.message ??
      (typeof data?.detail === "string"
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((item) => item.msg).join(", ")
          : typeof data?.reason === "string"
            ? data.reason
            : text.trim() || null);
    const error = new Error(
      detail || `${requestName} failed with status ${response.status}.`
    );
    error.status = response.status;
    if (structured?.code) {
      error.code = structured.code;
    }
    if (structured) {
      error.detail = structured;
    }
    throw error;
  }
  if (data === null) {
    throw new Error(`${requestName} returned an empty response.`);
  }
  return data;
}
