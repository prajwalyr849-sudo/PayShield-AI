/**
 * PayShield AI Deterministic Policy Engine
 * Evaluates agent purchase intents against mathematical and cryptographic invariants.
 *
 * Core Principle: Deterministic policies supersede LLM suggestions.
 * Strict Decoupling Protocol: PayShield Decision Rail acts prior to PayPal Payment Orchestration.
 */

export interface TransactionIntent {
  txId: string;
  agentId: string;
  agentCluster: string;
  merchantName: string;
  merchantDomain: string;
  merchantCountry: string;
  mcc: string;
  amountUsd: number;
  currency: string;
  paypalVerified: boolean;
  dnssecValid: boolean;
  rolling10mVolume: number;
  promptIntentDeviation?: number;
  promptInjectionDetected?: boolean;
}

export type PayShieldDecision = 'ALLOW' | 'REVIEW' | 'BLOCK';

export type PayPalPaymentStatus =
  | 'UNEXECUTED'
  | 'PENDING_AUTH'
  | 'CAPTURED'
  | 'HALTED'
  | 'VOIDED'
  | 'REFUNDED';

export interface PolicyRule {
  id: string;
  name: string;
  type: 'HARD_STOP' | 'ESCROW_HOLD' | 'QUARANTINE';
  description: string;
  evaluate: (intent: TransactionIntent) => { passed: boolean; reason?: string };
}

export interface EvaluationResult {
  decision: PayShieldDecision;
  primaryRuleTriggered?: string;
  reasons: string[];
  rulesPassed: number;
  rulesEvaluated: number;
  canReleaseToPayPal: boolean;
  riskScore: number;
  suggestedAction: string;
}

export const DETERMINISTIC_POLICIES: PolicyRule[] = [
  {
    id: 'POL-EXP-01',
    name: 'Single-Transaction Threshold Hard-Stop',
    type: 'HARD_STOP',
    description: 'Transaction amount exceeds maximum allowable unassisted ceiling ($5,000.00)',
    evaluate: (intent) => {
      if (intent.amountUsd > 5000.0) {
        return {
          passed: false,
          reason: `Single-TX threshold cap breached ($${intent.amountUsd.toFixed(2)} > $5,000.00 max allowable spend).`,
        };
      }
      return { passed: true };
    },
  },
  {
    id: 'POL-GEO-04',
    name: 'Jurisdiction & Sanctions Geo-Fencing',
    type: 'HARD_STOP',
    description: 'Merchant country must be in approved economic zones [US, CA, UK, EU, JP]',
    evaluate: (intent) => {
      const allowedCountries = ['US', 'CA', 'UK', 'EU', 'JP', 'DE', 'FR', 'GB'];
      if (!allowedCountries.includes(intent.merchantCountry.toUpperCase())) {
        return {
          passed: false,
          reason: `Merchant origin jurisdiction (${intent.merchantCountry}) violates sanctioned zone policy.`,
        };
      }
      return { passed: true };
    },
  },
  {
    id: 'POL-VENDOR-02',
    name: 'Verified PayPal Merchant & DNSSEC Check',
    type: 'ESCROW_HOLD',
    description: 'Unverified PayPal KYC or missing DNSSEC triggers 15m human escrow hold',
    evaluate: (intent) => {
      if (!intent.paypalVerified || !intent.dnssecValid) {
        return {
          passed: false,
          reason: `Vendor trustmark validation failed: PayPal KYC=${intent.paypalVerified ? 'OK' : 'MISSING'}, DNSSEC=${intent.dnssecValid ? 'OK' : 'INVALID'}.`,
        };
      }
      return { passed: true };
    },
  },
  {
    id: 'POL-VELOCITY-03',
    name: 'Agent Burst Rate Limit Enclave',
    type: 'QUARANTINE',
    description: 'Rolling 10-minute spend volume cannot exceed $15,000.00',
    evaluate: (intent) => {
      if (intent.rolling10mVolume > 15000.0) {
        return {
          passed: false,
          reason: `Rolling 10m spend volume ($${intent.rolling10mVolume.toFixed(2)}) departed 3-sigma baseline. Rate limit breached.`,
        };
      }
      return { passed: true };
    },
  },
  {
    id: 'POL-LLM-DRIFT-08',
    name: 'Prompt Injection & Semantic Mandate Override',
    type: 'HARD_STOP',
    description: 'Adversarial prompt injection attempt or semantic deviation > 75%',
    evaluate: (intent) => {
      if (intent.promptInjectionDetected || (intent.promptIntentDeviation && intent.promptIntentDeviation > 75)) {
        return {
          passed: false,
          reason: 'Indirect prompt injection or severe semantic mandate bypass detected in intent payload.',
        };
      }
      return { passed: true };
    },
  },
];

export function evaluateTransactionPolicy(intent: TransactionIntent): EvaluationResult {
  const reasons: string[] = [];
  let hasHardStop = false;
  let hasEscrow = false;
  let primaryRule: string | undefined;
  let rulesPassed = 0;

  for (const rule of DETERMINISTIC_POLICIES) {
    const outcome = rule.evaluate(intent);
    if (!outcome.passed) {
      if (!primaryRule) primaryRule = rule.id;
      reasons.push(outcome.reason || rule.description);
      if (rule.type === 'HARD_STOP' || rule.type === 'QUARANTINE') {
        hasHardStop = true;
      } else if (rule.type === 'ESCROW_HOLD') {
        hasEscrow = true;
      }
    } else {
      rulesPassed++;
    }
  }

  let decision: PayShieldDecision = 'ALLOW';
  let suggestedAction = 'Proceed with PayPal Capture';
  let riskScore = 4;

  if (hasHardStop) {
    decision = 'BLOCK';
    suggestedAction = 'Pre-flight Abort: Zero PayPal API Tokens Dispatched';
    riskScore = 88;
  } else if (hasEscrow) {
    decision = 'REVIEW';
    suggestedAction = 'Escrow Hold: Mandatory Human Multi-Sig Verification Required';
    riskScore = 68;
  }

  return {
    decision,
    primaryRuleTriggered: primaryRule,
    reasons,
    rulesPassed,
    rulesEvaluated: DETERMINISTIC_POLICIES.length,
    canReleaseToPayPal: decision === 'ALLOW',
    riskScore,
    suggestedAction,
  };
}
