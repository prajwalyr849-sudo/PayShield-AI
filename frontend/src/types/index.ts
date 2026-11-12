/**
 * PayShield AI - Core Type Definitions
 * Trust Operating System for Agentic Commerce
 */

export type PageId =
  | 'overview'
  | 'assistant-chat'
  | 'product-search'
  | 'transactions'
  | 'lifecycle'
  | 'receipts'
  | 'receipt-detail'
  | 'risk-intelligence'
  | 'budget-intelligence'
  | 'activity'
  | 'checkout'
  | 'audit-investigation'
  | 'alerts'
  | 'policies'
  | 'audit-logs'
  | 'settings'
  | 'integrations'
  | 'forgot-password'
  | 'reset-password';

export type PayShieldGate = 'ALLOW' | 'REVIEW' | 'BLOCK';

export interface IdentityPublic {
  provider: string;
  provider_user_id: string;
  email: string;
  email_verified: boolean;
  linked_at: string;
  last_login_at: string;
}

export interface UserPublicProfile {
  id: string;
  primary_email: string;
  full_name: string;
  avatar_url: string;
  identities: IdentityPublic[];
}

export type PayPalRailState =
  | 'CAPTURED'
  | 'PENDING_AUTH'
  | 'HOLD_ESCROW'
  | 'HALTED_NO_CALL'
  | 'REVERSED'
  | 'VOIDED'
  | 'UNEXECUTED';

export type VerificationState = 'VERIFIED' | 'ATTESTED' | 'EVIDENCE_WARNING' | 'UNVERIFIED';

export interface TransactionRecord {
  id: string; // e.g. TX-920412
  hash: string; // e.g. 0x8a91..fc01
  timestamp: string;
  agentId: string;
  agentName: string;
  targetVendor: string;
  vendorDomain: string;
  mcc: string;
  itemDescription: string;
  amount: number;
  currency: string;
  payshieldGate: PayShieldGate;
  riskScore: number;
  policyTriggered: string;
  paypalRailState: PayPalRailState;
  paypalOrderId?: string;
  paypalCaptureId?: string;
  settleLatencyMs?: number;
  inferenceModel?: string;
  agentSignature?: string;
  evidenceValidated?: boolean;
}

export interface ReceiptRecord {
  id: string;
  hash: string;
  timestamp: string;
  orderId: string | null;
  transactionId: string | null;
  agentName: string;
  agentId: string;
  merchantName: string;
  merchantDomain: string;
  mcc: string;
  paypalMid: string;
  taxId: string;
  authGate: string;
  captureId: string | null;
  settledAmount: number | null;
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
  updatedAt: string;
  agentIntentSig: string;
  policyToken: string;
  merkleProofBlock: string | null;
  lineItems: any[];
  deliveryAddress?: string;
}

export interface RiskIncident {
  id: string; // INC-2024-8841
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
}

export interface AgentHealth {
  id: string;
  name: string;
  cluster: string;
  tier: 'AUTONOMOUS' | 'SEMI-SUPERVISED' | 'HARD-GATED' | 'QUARANTINE';
  budget24h: number;
  budgetUsed24h: number;
  riskScore: number;
  blockRate: number;
  latencyMs: number;
  status: 'active' | 'quarantined' | 'throttled';
}

export interface ChatThread {
  id: string;
  title: string;
  preview: string;
  agentName: string;
  timestamp: string;
  status: 'REVIEW' | 'BLOCKED' | 'RESOLVED' | 'CLOSED';
  txRef?: string;
  amount?: number;
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
  reputationScore: number; // 0 - 100
  withinCeiling: boolean;
  specifications: string[];
  condition?: string;   // offer condition reported by the provider (new, used, ...)
  variant?: string;     // selected variant summary (storage, color, ...)
  availability?: string; // provider-reported availability
  description?: string;
  brand?: string;
  rating?: number;
  reviewCount?: number;
  dataSource?: string;
  imageUrl?: string;
  merchantUrl?: string;
  specs?: any;
}

export interface AlertRecord {
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

export interface ActivityEvent {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  target: string;
  details: string;
  status: 'success' | 'warning' | 'error' | 'intercepted';
  merkleHash: string;
}

export interface AuditLogBlock {
  blockNumber: number;
  merkleRoot: string;
  previousBlockHash: string;
  timestamp: string;
  transactionsCount: number;
  signedBy: string;
  hsmEnclaveStatus: string;
  signatureAlgorithm: string;
}

export type ClusterEnvironment =
  | 'cluster-01-live'
  | 'sandbox'
  | 'active_cluster_01'
  | 'disconnected_cluster_02'
  | 'error_state'
  | 'loading_state';

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

export interface ReceiptsResponse {
  receipts: ReceiptRecord[];
  count: number;
}

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

export interface AssistantRecommendationsResponse {
  query: string;
  intent: any;
  recommendations: any[];
  summary: string;
  model_provider: string;
  timestamp: string;
  search_results: ProductOffer[];
  search_diagnostics: any;
}

export interface ShoppingQueryRequest {
  query: string;
  budget?: number | null;
  category?: string | null;
  preferred_merchant?: string | null;
  currency?: string;
  country?: string;
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

/**
 * Payload carried when a Product Search intent is dispatched to Assistant Chat.
 * Keeps the search, its selected product, and its results together so the
 * conversation can retain them in the history section without resending them.
 */
export interface PendingIntentPayload {
  intent: string;
  query?: string;
  product?: ProductOffer;
  results?: ProductOffer[];
  /** Optional receipt ID to display when navigating to the receipt detail page. */
  receiptId?: string;
}

export interface SearchHistoryEntry {
  id: string;
  query: string;
  intent: string;
  product: ProductOffer;
  results: ProductOffer[];
  timestamp: string;
}

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

export interface PaymentCheckRequest {
  agent_id: string;
  amount: number;
  category: string;
}

export interface PaymentCheckResponse {
  decision: string;
  reason: string;
}

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

export interface GuardBuyReviewRequest {
  decision_reference: string;
  approved: boolean;
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

export interface RefundResponse {
  refundId: string;
  captureId: string;
  amount: number;
  currency: string;
  status: string;
  note: string;
  requiresConfirmation: boolean;
}

export interface IncidentListResponse {
  incidents: RiskIncidentApi[];
  count: number;
}


