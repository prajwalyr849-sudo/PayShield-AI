/**
 * PayShield AI — Unified API Client
 * Connects the premium UI to the existing FastAPI backend.
 *
 * All requests go through a single fetch wrapper that:
 *  - Resolves the backend base URL from VITE_API_BASE_URL (default http://127.0.0.1:8000)
 *  - Sends credentials (cookies) for authenticated endpoints
 *  - Normalizes error responses into throwable Error objects with status/code/detail
 *  - Never logs or exposes API keys/secrets
 */

interface ImportMetaEnv {
  VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  env: ImportMetaEnv;
}

const metaEnv =
  typeof import.meta !== 'undefined' && (import.meta as ImportMeta).env
    ? (import.meta as ImportMeta).env
    : {};

const API_BASE_URL = (
  metaEnv.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
).replace(/\/+$/, '');

import { ReceiptRecord } from '../types';

export interface ApiError extends Error {
  status?: number;
  code?: string;
  detail?: unknown;
}

async function parseResponse<T>(
  response: Response,
  requestName: string
): Promise<T> {
  const text = await response.text();
  let data: unknown = null;
  if (text.trim()) {
    try {
      data = JSON.parse(text);
    } catch {
      if (response.ok) {
        const err: ApiError = new Error(
          `${requestName} returned malformed JSON.`
        );
        err.status = response.status;
        throw err;
      }
    }
  }

  if (!response.ok) {
    const dataAny = data as any;
    let message: string;
    const detail = dataAny?.detail;
    if (Array.isArray(detail)) {
      message = detail
        .map((item: any) => (typeof item.msg === 'string' ? item.msg : String(item)))
        .join(', ');
    } else if (typeof detail === 'string') {
      message = detail;
    } else if (typeof dataAny?.reason === 'string') {
      message = dataAny.reason;
    } else {
      message = text.trim() || `${requestName} failed with status ${response.status}.`;
    }
    const err: ApiError = new Error(message);
    err.status = response.status;
    if ((data as any)?.code) err.code = (data as any).code;
    if (data as any) err.detail = data;
    throw err;
  }

  if (data === null) {
    const err: ApiError = new Error(
      `${requestName} returned an empty response.`
    );
    err.status = response.status;
    throw err;
  }

  return data as T;
}

function requestHeaders(contentType = false): HeadersInit {
  const headers: HeadersInit = { Accept: 'application/json' };
  if (contentType) {
    headers['Content-Type'] = 'application/json';
  }
  return headers;
}

/* ------------------------------------------------------------------ */
/* Health                                                             */
/* ------------------------------------------------------------------ */

export interface HealthResponse {
  status: string;
  application: { name: string; version: string };
  components: {
    api: { status: string };
    database: { status: string };
    audit_log: { status: string };
  };
  providers: {
    channel3: { configured: boolean };
    live_search_fallback: {
      configured: boolean;
      enabled: boolean;
    };
    paypal_sandbox: { configured: boolean };
  };
}

export async function getHealth(): Promise<HealthResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/health`, {
      headers: requestHeaders(),
    });
  } catch {
    throw new Error('Unable to reach the PayShield health endpoint.');
  }
  return parseResponse<HealthResponse>(response, 'Health status');
}

/* ------------------------------------------------------------------ */
/* Auth                                                               */
/* ------------------------------------------------------------------ */

export interface UserPublicProfile {
  id: string;
  primary_email: string;
  full_name: string;
  avatar_url: string;
  identities: Array<{
    provider: string;
    provider_user_id: string;
    email: string;
    email_verified: boolean;
    linked_at: string;
    last_login_at: string;
  }>;
}

export async function getAuthMe(): Promise<UserPublicProfile | null> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/me`, {
      credentials: 'include',
      headers: requestHeaders(),
    });
  } catch {
    return null;
  }
  if (response.status === 401) return null;
  return parseResponse<UserPublicProfile>(response, 'User profile');
}

export async function loginDemoUser(): Promise<UserPublicProfile> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/demo/login`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify({}),
    });
  } catch {
    throw new Error('Unable to contact PayShield authentication service.');
  }
  return parseResponse<UserPublicProfile>(response, 'Demo login');
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export async function loginUser(
  credentials: LoginCredentials
): Promise<UserPublicProfile> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify({
        email: credentials.email,
        password: credentials.password,
      }),
    });
  } catch {
    throw new Error('Unable to contact PayShield authentication service.');
  }
  return parseResponse<UserPublicProfile>(response, 'Sign in');
}

export interface RegisterCredentials {
  email: string;
  name: string;
  password: string;
  confirm_password: string;
}

export async function registerUser(
  credentials: RegisterCredentials
): Promise<UserPublicProfile> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/register`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify({
        email: credentials.email,
        name: credentials.name,
        password: credentials.password,
        confirm_password: credentials.confirm_password,
      }),
    });
  } catch {
    throw new Error('Unable to contact PayShield authentication service.');
  }
  return parseResponse<UserPublicProfile>(response, 'Register');
}

/* ------------------------------------------------------------------ */
/* Password Reset                                                     */
/* ------------------------------------------------------------------ */

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetRequestResponse {
  status: string;
  message: string;
  dev_mode?: boolean;
  reset_token?: string;
  expires_in_minutes?: number;
}

export async function requestPasswordReset(
  credentials: PasswordResetRequest
): Promise<PasswordResetRequestResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/password-reset/request`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify({
        email: credentials.email,
      }),
    });
  } catch {
    throw new Error('Unable to contact PayShield authentication service.');
  }
  return parseResponse<PasswordResetRequestResponse>(
    response,
    'Password reset request'
  );
}

export interface PasswordResetConfirm {
  token: string;
  password: string;
}

export interface PasswordResetConfirmResponse {
  status: string;
}

export async function confirmPasswordReset(
  credentials: PasswordResetConfirm
): Promise<PasswordResetConfirmResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/password-reset/confirm`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify({
        token: credentials.token,
        password: credentials.password,
      }),
    });
  } catch {
    throw new Error('Unable to contact PayShield authentication service.');
  }
  return parseResponse<PasswordResetConfirmResponse>(
    response,
    'Password reset confirm'
  );
}

/* ------------------------------------------------------------------ */
/* Google OAuth                                                       */
/* ------------------------------------------------------------------ */

export interface GoogleSignInUrlResponse {
  authorization_url: string;
  state: string;
  provider: string;
}

export async function getGoogleSignInUrl(): Promise<GoogleSignInUrlResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/google/login`, {
      method: 'GET',
      credentials: 'include',
      headers: requestHeaders(),
    });
  } catch {
    throw new Error('Unable to contact PayShield authentication service.');
  }
  return parseResponse<GoogleSignInUrlResponse>(response, 'Google sign-in');
}

export async function logoutUser(): Promise<{ status: string }> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(),
    });
  } catch {
    throw new Error('Unable to contact PayShield authentication service.');
  }
  return parseResponse<{ status: string }>(response, 'Logout');
}

export async function getAuthProviderStatus(): Promise<any> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/auth/providers/status`, {
      headers: requestHeaders(),
    });
  } catch {
    throw new Error('Unable to contact PayShield authentication service.');
  }
  return parseResponse<any>(response, 'Authentication provider status');
}

/* ------------------------------------------------------------------ */
/* Budget                                                             */
/* ------------------------------------------------------------------ */

export interface AgentBudget {
  agent_id: string;
  spending_limit_cents: number;
  spent_cents: number;
  reserved_cents: number;
  available_cents: number;
  reservations: Array<{
    idempotency_key: string;
    amount_cents: number;
    status: string;
    created_at: string;
  }>;
  pending_reservation_count: number;
}

export interface BudgetStateResponse {
  agents: AgentBudget[];
}

export async function getBudgetState(): Promise<BudgetStateResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/budget/state`, {
      credentials: 'include',
      headers: requestHeaders(),
    });
  } catch {
    throw new Error('Unable to fetch budget state from PayShield.');
  }
  return parseResponse<BudgetStateResponse>(response, 'Budget state');
}

/* ------------------------------------------------------------------ */
/* Audit History                                                      */
/* ------------------------------------------------------------------ */

export interface AuditRecord {
  transaction_id?: string;
  external_order_id?: string;
  user_id?: string;
  agent_id?: string;
  merchant?: string;
  merchant_name?: string;
  amount?: number;
  currency?: string;
  risk_score?: number;
  risk_level?: string;
  policy_decision?: string;
  final_decision?: string;
  decision_reason?: string;
  timestamp?: string;
  event_type?: string;
  source?: string;
  order_fingerprint?: string;
  [key: string]: unknown;
}

export interface AuditHistoryResponse {
  records: AuditRecord[];
}

export async function getAuditHistory(
  limit = 50
): Promise<AuditHistoryResponse> {
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/audit/history?limit=${encodeURIComponent(String(limit))}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to reach PayShield. Check that the backend is running.');
  }
  return parseResponse<AuditHistoryResponse>(response, 'Audit history');
}

/* ------------------------------------------------------------------ */
/* Elasticsearch                                                      */
/* ------------------------------------------------------------------ */

export interface ElasticStatus {
  configured: boolean;
  reachable: boolean;
  index?: string;
  reason?: string;
  cluster_name?: string;
  version?: string;
}

export async function getElasticStatus(): Promise<ElasticStatus> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/audit/elastic/status`, {
      credentials: 'include',
      headers: requestHeaders(),
    });
  } catch {
    throw new Error('Unable to reach Elasticsearch status endpoint.');
  }
  return parseResponse<ElasticStatus>(response, 'Elasticsearch status');
}

export interface ElasticSearchParams {
  query?: string;
  decision?: string;
  risk_level?: string;
  size?: number;
}

export interface ElasticSearchResponse {
  results: any[];
  count: number;
}

export async function searchElasticAudit(
  params: ElasticSearchParams = {}
): Promise<ElasticSearchResponse> {
  let response: Response;
  try {
    const searchParams = new URLSearchParams();
    if (params.query) searchParams.append('query', params.query);
    if (params.decision && params.decision !== 'ALL')
      searchParams.append('decision', params.decision);
    if (params.risk_level && params.risk_level !== 'ALL')
      searchParams.append('risk_level', params.risk_level);
    if (params.size) searchParams.append('size', String(params.size));

    response = await fetch(
      `${API_BASE_URL}/audit/elastic/search?${searchParams.toString()}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
        method: 'GET',
      }
    );
  } catch {
    throw new Error('Unable to search Elasticsearch audit events.');
  }
  return parseResponse<ElasticSearchResponse>(response, 'Elasticsearch search');
}

/* ------------------------------------------------------------------ */
/* Transactions / Activity                                            */
/* ------------------------------------------------------------------ */

export interface ActivityEvent {
  event_id: string;
  event_type: string;
  paypal_order_id: string;
  paypal_capture_id: string;
  paypal_amount: string;
  paypal_currency: string;
  paypal_status: string;
  paypal_create_time: string;
  paypal_capture_time: string;
  payshield_transaction_id: string;
  payshield_decision: string;
  payshield_risk_level: string;
  payshield_risk_score: number | null;
  payshield_reason: string;
  reconciled: boolean;
  received_at: string;
}

export interface ActivityResponse {
  events: ActivityEvent[];
  count: number;
}

export async function getTransactionActivity({
  limit = 50,
}: { limit?: number } = {}): Promise<ActivityResponse> {
  let response: Response;
  try {
    const params = new URLSearchParams();
    params.append('size', String(limit));
    response = await fetch(
      `${API_BASE_URL}/transactions/activity?${params.toString()}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
        method: 'GET',
      }
    );
  } catch {
    throw new Error('Unable to fetch transaction activity.');
  }
  return parseResponse<ActivityResponse>(response, 'Transaction activity');
}

export async function getActivityByOrder(
  paypalOrderId: string
): Promise<ActivityEvent> {
  if (!paypalOrderId || !paypalOrderId.trim()) {
    throw new Error('PayPal order ID is required.');
  }
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/transactions/activity/${encodeURIComponent(
        paypalOrderId
      )}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
        method: 'GET',
      }
    );
  } catch {
    throw new Error('Unable to fetch activity for this PayPal order.');
  }
  return parseResponse<ActivityEvent>(response, 'Activity by order');
}

/* ------------------------------------------------------------------ */
/* Receipts                                                           */
/* ------------------------------------------------------------------ */

export interface ReceiptRecordFrontend {
  id: string;
  transactionId: string | null;
  orderId: string | null;
  captureId: string | null;
  externalOrderId: string | null;
  idempotencyKey: string | null;
  userId: string;
  agentName: string;
  merchantName: string;
  merchantCategory: string;
  amount: string | null;
  currency: string;
  quantity: number;
  status: string;
  decision: string;
  verificationStatus: string;
  reason: string;
  riskScore: number | null;
  riskLevel: string;
  snapshots: any;
  events: any[];
  timestamp: string;
  updatedAt: string;
}

export interface ReceiptRecordCamel {
  receiptId: string;
  transactionId: string | null;
  orderId: string | null;
  captureId: string | null;
  externalOrderId: string | null;
  idempotencyKey: string | null;
  userId: string;
  agentId: string;
  merchantName: string;
  merchantCategory: string;
  amount: string | null;
  currency: string;
  quantity: number;
  status: string;
  decision: string;
  paymentStatusRaw: string;
  reason: string;
  riskScore: number | null;
  riskLevel: string;
  snapshots: any;
  events: any[];
  createdAt: string;
  updatedAt: string;
}

export interface ReceiptsResponse {
  receipts: ReceiptRecord[];
  count: number;
}

export async function getReceipts(limit = 50): Promise<ReceiptsResponse> {
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/receipts?limit=${encodeURIComponent(String(limit))}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to fetch receipts.');
  }
  const data = await parseResponse<{ receipts: any[]; count: number }>(response, 'Receipts');
  return {
    receipts: (data.receipts || []).map((r: any) => ({
      id: r.receipt_id,
      hash: r.receipt_id,
      timestamp: r.created_at,
      orderId: r.order_id || null,
      transactionId: r.transaction_id || null,
      agentName: r.agent_name,
      agentId: r.agent_id,
      merchantName: r.merchant_name,
      merchantDomain: r.merchant_domain || '',
      mcc: r.mcc,
      paypalMid: r.paypal_mid || '',
      taxId: r.tax_id || '',
      authGate: r.auth_gate || r.decision || 'ALLOW',
      captureId: r.capture_id || null,
      settledAmount: r.settled_amount || r.amount ? Number(r.settled_amount || r.amount) : null,
      currency: r.currency,
      quantity: r.quantity,
      status: r.status,
      decision: r.decision,
      verificationStatus: r.verification_status || r.status || 'COMPLETED',
      reason: r.reason || '',
      riskScore: r.risk_score || null,
      riskLevel: r.risk_level || '',
      snapshots: r.snapshots || {},
      events: r.events || [],
      agentIntentSig: r.agent_intent_sig || '',
      policyToken: r.policy_token || '',
      merkleProofBlock: r.merkle_proof_block || null,
      lineItems: r.line_items || [],
      deliveryAddress: r.delivery_address || '',
      updatedAt: r.updated_at || '',
    })),
    count: data.count,
  };
}

export async function getReceipt(receiptId: string): Promise<ReceiptRecord> {
  if (!receiptId || !receiptId.trim()) {
    throw new Error('Receipt ID is required.');
  }
  let response: Response;
  try {
    console.log('[PayShield API] Stage: getReceipt invoked', { receiptId });
    response = await fetch(
      `${API_BASE_URL}/receipts/${encodeURIComponent(receiptId)}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
    console.log('[PayShield API] Stage: getReceipt response', {
      receiptId,
      status: response.status,
      ok: response.ok,
    });
  } catch {
    console.error('[PayShield API] Stage: getReceipt network failed', { receiptId });
    throw new Error('Unable to fetch receipt.');
  }
  const data = await parseResponse<any>(response, 'Receipt');
  return mapReceipt(data);
}

export async function getReceiptByOrderId(
  orderId: string
): Promise<ReceiptRecord> {
  if (!orderId || !orderId.trim()) {
    throw new Error('Order ID is required.');
  }
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/receipts/order/${encodeURIComponent(orderId)}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to fetch receipt.');
  }
  const data = await parseResponse<any>(response, 'Receipt');
  return mapReceipt(data);
}

/** Map backend snake_case receipt fields to the camelCase ReceiptRecord type. */
/** Map backend snake_case receipt fields to the camelCase ReceiptRecord type. */
export function mapReceipt(r: any): ReceiptRecord {
  return {
    id: r.receipt_id,
    hash: r.receipt_id,
    timestamp: r.created_at,
    orderId: r.order_id || null,
    transactionId: r.transaction_id || null,
    agentName: r.agent_name,
    agentId: r.agent_id,
    merchantName: r.merchant_name,
    merchantDomain: r.merchant_domain || '',
    mcc: r.mcc,
    paypalMid: r.paypal_mid || '',
    taxId: r.tax_id || '',
    authGate: r.auth_gate || r.decision || 'ALLOW',
    captureId: r.capture_id || null,
    settledAmount: r.settled_amount || r.amount ? Number(r.settled_amount || r.amount) : null,
    currency: r.currency,
    quantity: r.quantity,
    status: r.status,
    decision: r.decision,
    verificationStatus: r.verification_status || r.status || 'COMPLETED',
    reason: r.reason || '',
    riskScore: r.risk_score || null,
    riskLevel: r.risk_level || '',
    snapshots: r.snapshots || {},
    events: r.events || [],
    agentIntentSig: r.agent_intent_sig || '',
    policyToken: r.policy_token || '',
    merkleProofBlock: r.merkle_proof_block || null,
    lineItems: r.line_items || [],
    deliveryAddress: r.delivery_address || '',
    updatedAt: r.updated_at || '',
  };
}

/* ------------------------------------------------------------------ */
/* Assistant                                                          */
/* ------------------------------------------------------------------ */

export interface AssistantStatus {
  status: string;
  provider: string;
  model: string;
  configured: boolean;
  assistant_configured: boolean;
  rating_configured: boolean;
  ollama_client_installed: boolean;
  offline_catalog_available: boolean;
  live_search_configured: boolean;
  search_provider: string;
  base_url: string;
}

export async function getAssistantStatus(): Promise<AssistantStatus> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/assistant/status`, {
      headers: requestHeaders(),
    });
  } catch {
    throw new Error('Unable to contact PayShield assistant service.');
  }
  return parseResponse<AssistantStatus>(response, 'Assistant status');
}

export interface ProductOffer {
  id: string;
  title: string;
  category: string;
  merchantName: string;
  merchantDomain: string;
  price: number;
  currency: string;
  verification: 'VERIFIED_MERCHANT' | 'CANDIDATE_UNVERIFIED';
  dnssec: boolean;
  kycTrustmark: boolean;
  reputationScore: number;
  withinCeiling: boolean;
  specifications: string[];
  description?: string;
  brand?: string;
  rating?: number;
  reviewCount?: number;
  dataSource?: string;
  imageUrl?: string;
  merchantUrl?: string;
  specs?: any;
}

export interface AssistantRecommendationsResponse {
  query: string;
  intent: any;
  recommendations: any[];
  summary: string;
  model_provider: string;
  timestamp: string;
  search_results: ProductOffer[];
  search_diagnostics: any;
  next_page_token?: string;
  has_more?: boolean;
}

/** Map a Channel3 live-search result to the frontend ProductOffer shape,
 *  labeling its provenance honestly. Every field is null-safe so a partial or
 *  malformed provider response can never crash the renderer. The canonical
 *  offer id is the provider's product reference (c3_…). */
export function mapChannel3Result(p: any): ProductOffer {
  return {
    id: String(p?.id || p?.product_reference || ''),
    title: String(p?.title || 'Untitled product'),
    category: 'general',
    merchantName: String(p?.retailer || p?.source_domain || 'Unknown merchant'),
    merchantDomain: String(p?.source_domain || ''),
    price: Number(p?.price ?? 0) || 0,
    currency: String(p?.price_currency || p?.currency || 'USD'),
    verification: p?.price_verified ? 'VERIFIED_MERCHANT' : 'CANDIDATE_UNVERIFIED',
    dnssec: false,
    kycTrustmark: false,
    reputationScore: 0,
    withinCeiling: (Number(p?.price ?? 0) || 0) <= 5000,
    specifications: [],
    description: String(p?.snippet || ''),
    dataSource: 'live',
    imageUrl: String(p?.image_url || ''),
    merchantUrl: String(p?.source_url || ''),
    specs: {},
  };
}

export interface ShoppingQueryRequest {
  query: string;
  budget?: number | null;
  category?: string | null;
  preferred_merchant?: string | null;
  currency?: string;
  country?: string;
  max_results?: number;
  page_token?: string;
}

export async function getAssistantRecommendations(
  body: ShoppingQueryRequest
): Promise<AssistantRecommendationsResponse> {
  let response: Response;
  const params = new URLSearchParams();
  if (body.max_results) params.append('max_results', String(body.max_results));
  if (body.page_token) params.append('page_token', body.page_token);
  const suffix = params.toString() ? `?${params.toString()}` : '';
  try {
    response = await fetch(`${API_BASE_URL}/assistant/recommendations${suffix}`, {
      method: 'POST',
      headers: requestHeaders(true),
      body: JSON.stringify({
        query: body.query,
        budget: body.budget ? Number(body.budget) : null,
        category: body.category || null,
        preferred_merchant: body.preferred_merchant || null,
        currency: body.currency || 'USD',
        country: body.country || 'US',
      }),
    });
  } catch {
    throw new Error('Unable to reach PayShield Assistant service.');
  }
  return parseResponse<AssistantRecommendationsResponse>(
    response,
    'Shopping recommendations'
  );
}

export interface AssistantChatRequest {
  query: string;
  messages: any[];
  budget?: number | null;
  category?: string | null;
  currency?: string;
  country?: string;
}

export interface AssistantChatResponse {
  reply: string;
  intent: any;
  recommendations: any[];
  search_results: ProductOffer[];
  search_diagnostics: any;
  timestamp: string;
  provider: string;
  search_available: boolean;
}

export async function sendAssistantChat(
  body: AssistantChatRequest
): Promise<AssistantChatResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/assistant/chat`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify({
        query: body.query,
        messages: body.messages,
        budget: body.budget ? Number(body.budget) : null,
        category: body.category || null,
        currency: body.currency || 'USD',
        country: body.country || 'US',
      }),
    });
  } catch {
    throw new Error('Unable to reach PayShield Assistant service.');
  }
  return parseResponse<AssistantChatResponse>(response, 'Assistant chat');
}

export async function getAssistantProducts(
  category = ''
): Promise<ProductOffer[]> {
  let response: Response;
  try {
    const url = category
      ? `${API_BASE_URL}/assistant/products?category=${encodeURIComponent(category)}`
      : `${API_BASE_URL}/assistant/products`;
    response = await fetch(url, {
      headers: requestHeaders(),
    });
  } catch {
    throw new Error('Unable to fetch catalog products.');
  }
  const data = await response.json();
  return (data as any[]).map((p: any) => ({
    id: p.id,
    title: p.title,
    category: p.category,
    merchantName: p.merchant_name,
    merchantDomain: p.merchant_domain,
    price: p.price,
    currency: p.currency,
    verification: p.verification || 'CANDIDATE_UNVERIFIED',
    dnssec: p.dnssec,
    kycTrustmark: p.kyc_trustmark,
    reputationScore: p.reputation_score,
    withinCeiling: p.within_ceiling,
    specifications: p.specifications || [],
    description: p.description,
    brand: p.brand,
    rating: p.rating,
    reviewCount: p.review_count,
    dataSource: p.data_source,
    imageUrl: p.image_url,
    merchantUrl: p.merchant_url,
    specs: p.specs,
  }));
}

/* ------------------------------------------------------------------ */
/* Settings                                                           */
/* ------------------------------------------------------------------ */

export interface SecurityControls {
  [key: string]: unknown;
}

export async function getSettingsPreferences(): Promise<SecurityControls> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/settings/preferences`, {
      credentials: 'include',
      headers: requestHeaders(),
    });
  } catch {
    throw new Error('Unable to load preferences from PayShield.');
  }
  return parseResponse<SecurityControls>(response, 'Security controls');
}

export async function updateSettingsPreferences(
  preferences: SecurityControls
): Promise<SecurityControls> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/settings/preferences`, {
      method: 'PUT',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify(preferences),
    });
  } catch {
    throw new Error('Unable to save preferences to PayShield.');
  }
  return parseResponse<SecurityControls>(
    response,
    'Save settings preferences'
  );
}

/* ------------------------------------------------------------------ */
/* PayPal Orders                                                      */
/* ------------------------------------------------------------------ */

export interface CreatePayPalOrderRequest {
  amount: number;
  currency?: string;
  agent_id?: string;
  category?: string;
  merchant_name?: string;
  user_id?: string;
}

export interface CreatePayPalOrderResponse {
  order_id: string;
  status: string;
  payment_status: string;
  approval_url: string;
  links: any[];
}

export async function createPayPalOrder(
  order: CreatePayPalOrderRequest
): Promise<CreatePayPalOrderResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/paypal/orders`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify({
        ...order,
        amount: Number(order.amount),
      }),
    });
  } catch {
    throw new Error('Unable to reach PayShield. Check that the backend is running.');
  }
  return parseResponse<CreatePayPalOrderResponse>(response, 'PayPal order creation');
}

export interface CapturePayPalOrderResponse {
  success: boolean;
  decision: string;
  payment_status: string;
  reason: string;
  order_id: string;
  receipt_id: string | null;
  capture?: any;
  risk_assessment?: any;
  reconciliation_required?: boolean;
  risk_score?: number | null;
  risk_level?: string;
}

export async function capturePayPalOrder(
  orderId: string
): Promise<CapturePayPalOrderResponse> {
  if (!orderId || !orderId.trim()) {
    throw new Error('PayPal order ID is required.');
  }
  let response: Response;
  try {
    console.log('[PayShield API] Stage: capturePayPalOrder invoked', { orderId });
    response = await fetch(
      `${API_BASE_URL}/paypal/orders/${encodeURIComponent(orderId)}/capture`,
      {
        method: 'POST',
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
    console.log('[PayShield API] Stage: capturePayPalOrder response', {
      orderId,
      status: response.status,
      ok: response.ok,
    });
  } catch {
    console.error('[PayShield API] Stage: capturePayPalOrder network failed', { orderId });
    throw new Error('Unable to reach PayShield. Check that the backend is running.');
  }
  return parseResponse<CapturePayPalOrderResponse>(response, 'PayPal payment');
}

/* ------------------------------------------------------------------ */
/* Payment Check                                                      */
/* ------------------------------------------------------------------ */

export interface PaymentCheckRequest {
  agent_id: string;
  amount: number;
  category: string;
}

export interface PaymentCheckResponse {
  decision: string;
  reason: string;
}

export async function checkPayment(
  body: PaymentCheckRequest
): Promise<PaymentCheckResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/check-payment`, {
      method: 'POST',
      headers: requestHeaders(true),
      body: JSON.stringify({
        agent_id: body.agent_id,
        amount: Number(body.amount),
        category: body.category,
      }),
    });
  } catch {
    throw new Error('Unable to reach PayShield. Check that the backend is running.');
  }
  return parseResponse<PaymentCheckResponse>(response, 'Payment check');
}

/* ------------------------------------------------------------------ */
/* Guard Buy                                                          */
/* ------------------------------------------------------------------ */

export interface GuardBuyRequest {
  product_reference: string;
  quantity: number;
  idempotency_key?: string;
}

export interface GuardBuyResponse {
  decision: string;
  payment_status: string;
  product_reference: string;
  decision_reference: string;
  checkout_available: boolean;
  title: string;
  source_url: string;
  retailer: string;
  price: number | null;
  price_verified: boolean;
  price_currency: string;
  price_type: string;
  price_method: string;
  price_unverified_reason: string;
  availability: string;
  identity_match: string;
  source_domain: string;
  currency: string;
  quantity: number;
  amount: number | null;
  checkout_amount_verified: boolean;
  risk_score: number | null;
  risk_level: string;
  reason: string;
  reasons: string[];
  audit_reference: string | null;
  evaluation: any;
  provider: string;
  is_fallback: boolean;
  evidence_status: string;
  condition: string;
  seller: string;
  variant: string;
  rating: any;
  review_count: any;
  rating_status: string;
  rating_provider: string;
}

export async function guardBuy(
  body: GuardBuyRequest
): Promise<GuardBuyResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/assistant/guard-buy`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify({
        product_reference: body.product_reference,
        quantity: Number(body.quantity),
        idempotency_key: body.idempotency_key || undefined,
      }),
    });
  } catch {
    throw new Error('Unable to contact PayShield Guard Buy.');
  }
  return parseResponse<GuardBuyResponse>(response, 'Guard Buy decision');
}

export interface GuardBuyReviewRequest {
  decision_reference: string;
  approved: boolean;
}

export async function approveGuardBuyReview(
  body: GuardBuyReviewRequest
): Promise<GuardBuyResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/assistant/guard-buy/review`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify({
        decision_reference: body.decision_reference,
        approved: body.approved,
      }),
    });
  } catch {
    throw new Error('Unable to contact PayShield review approval service.');
  }
  return parseResponse<GuardBuyResponse>(response, 'Guard Buy review');
}

export interface GuardBuyCheckoutRequest {
  decision_reference: string;
  idempotency_key?: string;
  delivery_address?: string;
}

export interface GuardBuyCheckoutResponse {
  decision: string;
  payment_status: string;
  product_reference: string;
  order_id: string | null;
  approval_url: string | null;
  total_amount: number;
  currency: string;
  checkout_amount_verified: boolean;
  reason: string;
  evaluation: any;
}

export async function guardBuyCheckout(
  body: GuardBuyCheckoutRequest
): Promise<GuardBuyCheckoutResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/assistant/guard-buy/checkout`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify({
        decision_reference: body.decision_reference,
        idempotency_key: body.idempotency_key || `gb-checkout-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        delivery_address: body.delivery_address || undefined,
      }),
    });
  } catch {
    throw new Error('Unable to contact PayShield Sandbox checkout.');
  }
  return parseResponse<GuardBuyCheckoutResponse>(response, 'Sandbox checkout');
}

export interface GuardBuyHandoffRequest {
  decision_reference: string;
  idempotency_key: string;
}

export interface GuardBuyHandoffResponse {
  decision: string;
  handoff_status: string;
  product_reference: string;
  decision_reference: string;
  merchant_url: string | null;
  source_url: string;
  merchant_name: string;
  amount: number | null;
  currency: string;
  quantity: number;
  expires_at: string | null;
  reason: string;
}

export async function guardBuyHandoff(
  body: GuardBuyHandoffRequest
): Promise<GuardBuyHandoffResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/assistant/guard-buy/handoff`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify({
        decision_reference: body.decision_reference,
        idempotency_key: body.idempotency_key || `gb-handoff-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      }),
    });
  } catch {
    throw new Error('Unable to contact PayShield merchant handoff service.');
  }
  return parseResponse<GuardBuyHandoffResponse>(response, 'Merchant handoff');
}

export interface RecordHandoffOpenedResponse {
  decision: string;
  handoff_status: string;
  product_reference: string;
  decision_reference: string;
  opened: boolean;
  opened_at: string | null;
  merchant_url: string | null;
  reason: string;
}

export async function recordHandoffOpened(
  body: GuardBuyHandoffRequest
): Promise<RecordHandoffOpenedResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/assistant/guard-buy/handoff/opened`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify({
        decision_reference: body.decision_reference,
        idempotency_key: body.idempotency_key || `gb-handoff-opened-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      }),
    });
  } catch {
    throw new Error('Unable to record merchant handoff.');
  }
  return parseResponse<RecordHandoffOpenedResponse>(
    response,
    'Record merchant handoff opened'
  );
}

export interface GuardBuyCheckoutResponse2 {
  decision: string;
  payment_status: string;
  product_reference: string;
  order_id: string | null;
  approval_url: string | null;
  total_amount: number;
  currency: string;
  checkout_amount_verified: boolean;
  reason: string;
  evaluation: any;
}

export async function assistantCheckout(
  body: {
    product_id: string;
    quantity: number;
    user_id: string;
    idempotency_key?: string;
  }
): Promise<GuardBuyCheckoutResponse2> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/assistant/checkout`, {
      method: 'POST',
      headers: requestHeaders(true),
      body: JSON.stringify({
        product_id: body.product_id,
        quantity: Number(body.quantity),
        user_id: body.user_id || 'demo-user',
        idempotency_key:
          body.idempotency_key ||
          `idemp-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      }),
    });
  } catch {
    throw new Error('Unable to contact PayShield Guarded Checkout.');
  }
  return parseResponse<GuardBuyCheckoutResponse2>(response, 'Assistant checkout');
}

export async function rateAssistantProduct(
  body: { product_reference: string; query?: string }
): Promise<any> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/assistant/rate`, {
      method: 'POST',
      credentials: 'include',
      headers: requestHeaders(true),
      body: JSON.stringify({ product_reference: body.product_reference, query: body.query || '' }),
    });
  } catch {
    throw new Error('Unable to contact PayShield product rating service.');
  }
  return parseResponse<any>(response, 'AI product assessment');
}

export async function getLiveRating(
  body: { productReference: string; sourceUrl: string; sku?: string; forceRefresh?: boolean }
): Promise<any> {
  if (!body.productReference || !body.productReference.trim()) {
    throw new Error('Product reference is required.');
  }
  if (!body.sourceUrl || !body.sourceUrl.trim()) {
    throw new Error('Source URL is required.');
  }
  let response: Response;
  try {
    const params = new URLSearchParams({
      product_reference: body.productReference,
      source_url: body.sourceUrl,
    });
    if (body.sku) params.append('sku', body.sku);
    if (body.forceRefresh) params.append('force_refresh', 'true');
    response = await fetch(
      `${API_BASE_URL}/assistant/rating?${params.toString()}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to fetch live rating.');
  }
  return parseResponse<any>(response, 'Live rating');
}

/* ------------------------------------------------------------------ */
/* Risk Incidents                                                     */
/* ------------------------------------------------------------------ */

export interface RiskIncidentApi {
  id: string;
  agentId: string;
  cluster: string;
  riskScore: number;
  vector: string;
  proposedAmount: number;
  targetVendor: string;
  verdict: 'HARD_BLOCK' | 'QUARANTINE_REVIEW' | 'ALLOW';
  slaRemaining: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  paypalAuthHash: string;
  policyCode: string;
  mandateDeviationPct: number;
  rawPayload: Record<string, unknown>;
  llmRationale: string;
  deterministicReason: string;
  quarantined?: boolean;
  timestamp: string;
}

export async function getRiskIncidents(
  limit = 50,
  severity?: string,
  verdict?: string,
): Promise<{ incidents: RiskIncidentApi[]; count: number }> {
  let response: Response;
  try {
    const params = new URLSearchParams();
    params.append('limit', String(limit));
    if (severity) params.append('severity', severity);
    if (verdict) params.append('verdict', verdict);
    response = await fetch(
      `${API_BASE_URL}/risk/incidents?${params.toString()}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to fetch risk incidents from PayShield.');
  }
  return parseResponse<{ incidents: RiskIncidentApi[]; count: number }>(
    response,
    'Risk incidents'
  );
}

export async function getRiskIncident(
  incidentId: string
): Promise<RiskIncidentApi> {
  if (!incidentId || !incidentId.trim()) {
    throw new Error('Incident ID is required.');
  }
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/risk/incidents/${encodeURIComponent(incidentId)}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to fetch risk incident.');
  }
  return parseResponse<RiskIncidentApi>(response, 'Risk incident');
}

/* ------------------------------------------------------------------ */
/* Alerts                                                             */
/* ------------------------------------------------------------------ */

export interface AlertRecordApi {
  id: string;
  title: string;
  description: string;
  severity: 'critical' | 'high' | 'medium' | 'info';
  timestamp: string;
  source: string;
  policyId?: string;
  agentId?: string;
  status: 'active' | 'acknowledged' | 'resolved';
}

export async function listAlerts(
  status?: string,
  severity?: string,
  limit = 50,
): Promise<{ alerts: AlertRecordApi[]; count: number }> {
  let response: Response;
  try {
    const params = new URLSearchParams();
    params.append('limit', String(limit));
    if (status) params.append('status', status);
    if (severity) params.append('severity', severity);
    response = await fetch(
      `${API_BASE_URL}/alerts?${params.toString()}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to fetch alerts from PayShield.');
  }
  return parseResponse<{ alerts: AlertRecordApi[]; count: number }>(
    response,
    'Alerts'
  );
}

export async function acknowledgeAlert(
  alertId: string
): Promise<{ id: string; status: string }> {
  if (!alertId || !alertId.trim()) {
    throw new Error('Alert ID is required.');
  }
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/alerts/${encodeURIComponent(alertId)}/acknowledge`,
      {
        method: 'POST',
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to acknowledge alert.');
  }
  return parseResponse<{ id: string; status: string }>(
    response,
    'Acknowledge alert'
  );
}

export async function resolveAlert(
  alertId: string
): Promise<{ id: string; status: string }> {
  if (!alertId || !alertId.trim()) {
    throw new Error('Alert ID is required.');
  }
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/alerts/${encodeURIComponent(alertId)}/resolve`,
      {
        method: 'POST',
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to resolve alert.');
  }
  return parseResponse<{ id: string; status: string }>(
    response,
    'Resolve alert'
  );
}

/* ------------------------------------------------------------------ */
/* Policies                                                           */
/* ------------------------------------------------------------------ */

export interface PolicyRuleApi {
  id: string;
  name: string;
  category: 'spend' | 'merchant' | 'mandate' | 'crypto';
  action: string;
  description: string;
  dsl: string;
  enabled: boolean;
  latency: string;
}

export interface PolicyListResponse {
  policies: PolicyRuleApi[];
  count: number;
  constitution: {
    max_auto_payment: number;
    approval_limit: number;
    blocked_categories: string[];
  };
}

export async function listPolicies(
  category?: string,
  enabledOnly?: boolean
): Promise<PolicyListResponse> {
  let response: Response;
  try {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (enabledOnly !== undefined) params.append('enabledOnly', String(enabledOnly));
    response = await fetch(
      `${API_BASE_URL}/policies?${params.toString()}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to fetch policies from PayShield.');
  }
  return parseResponse<PolicyListResponse>(response, 'Policies');
}

export async function togglePolicy(
  policyId: string
): Promise<{ id: string; enabled: boolean; message: string }> {
  if (!policyId || !policyId.trim()) {
    throw new Error('Policy ID is required.');
  }
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/policies/${encodeURIComponent(policyId)}/toggle`,
      {
        method: 'PUT',
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to toggle policy.');
  }
  return parseResponse<{ id: string; enabled: boolean; message: string }>(
    response,
    'Toggle policy'
  );
}

/* ------------------------------------------------------------------ */
/* Lifecycle Sessions                                                 */
/* ------------------------------------------------------------------ */

export interface LifecycleSessionApi {
  sessionId: string;
  agentId: string;
  targetVendor: string;
  requestedAmount: number;
  currentState: string;
  stateHistory: any[];
  policyId?: string;
  assignedTo?: string;
  gatewayToken?: string;
  receiptId?: string;
  createdAt: string;
  updatedAt: string;
}

export interface LifecycleSessionResponse {
  sessions: LifecycleSessionApi[];
  count: number;
}

export async function listLifecycleSessions(
  state?: string,
  limit = 50
): Promise<LifecycleSessionResponse> {
  let response: Response;
  try {
    const params = new URLSearchParams();
    params.append('limit', String(limit));
    if (state) params.append('state', state);
    response = await fetch(
      `${API_BASE_URL}/lifecycle/sessions?${params.toString()}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to fetch lifecycle sessions from PayShield.');
  }
  return parseResponse<LifecycleSessionResponse>(response, 'Lifecycle sessions');
}

export async function getLifecycleSession(
  sessionId: string
): Promise<LifecycleSessionApi> {
  if (!sessionId || !sessionId.trim()) {
    throw new Error('Session ID is required.');
  }
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/lifecycle/sessions/${encodeURIComponent(sessionId)}`,
      {
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to fetch lifecycle session.');
  }
  return parseResponse<LifecycleSessionApi>(response, 'Lifecycle session');
}

/* ------------------------------------------------------------------ */
/* Refunds                                                            */
/* ------------------------------------------------------------------ */

export interface RefundResponse {
  refundId: string;
  captureId: string;
  amount: number;
  currency: string;
  status: string;
  note: string;
  requiresConfirmation: boolean;
}

export async function createRefund(
  captureId: string,
  amount?: number
): Promise<RefundResponse> {
  if (!captureId || !captureId.trim()) {
    throw new Error('Capture ID is required.');
  }
  let response: Response;
  try {
    const params = new URLSearchParams();
    if (amount !== undefined) params.append('amount', String(amount));
    response = await fetch(
      `${API_BASE_URL}/refunds?${params.toString()}`,
      {
        method: 'POST',
        credentials: 'include',
        headers: requestHeaders(),
      }
    );
  } catch {
    throw new Error('Unable to create refund.');
  }
  return parseResponse<RefundResponse>(response, 'Create refund');
}

/* ------------------------------------------------------------------ */
/* Integrations                                                       */
/* ------------------------------------------------------------------ */

export interface IntegrationStatusApi {
  name: string;
  category: string;
  configured: boolean;
  status: string;
  note: string;
  [key: string]: any;
}

export interface IntegrationStatusResponse {
  integrations: IntegrationStatusApi[];
  count: number;
  configuredCount: number;
}

export async function getIntegrationStatus(): Promise<IntegrationStatusResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/integrations/status`, {
      credentials: 'include',
      headers: requestHeaders(),
    });
  } catch {
    throw new Error('Unable to fetch integration status from PayShield.');
  }
  return parseResponse<IntegrationStatusResponse>(response, 'Integration status');
}

export { API_BASE_URL };
