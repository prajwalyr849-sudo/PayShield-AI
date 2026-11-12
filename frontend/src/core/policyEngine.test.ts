import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluateTransactionPolicy } from './policyEngine.ts';
import type { TransactionIntent } from './policyEngine.ts';

test('ALLOW: clean transaction under threshold with verified vendor passes all guards', () => {
  const cleanIntent: TransactionIntent = {
    txId: 'TX-TEST-01',
    agentId: 'ProcureBot-AWS-Prod',
    agentCluster: 'us-east-prod',
    merchantName: 'Amazon Web Services',
    merchantDomain: 'aws.amazon.com',
    merchantCountry: 'US',
    mcc: '7379',
    amountUsd: 1420.5,
    currency: 'USD',
    paypalVerified: true,
    dnssecValid: true,
    rolling10mVolume: 3500.0,
  };

  const result = evaluateTransactionPolicy(cleanIntent);
  assert.equal(result.decision, 'ALLOW');
  assert.equal(result.canReleaseToPayPal, true);
  assert.equal(result.rulesPassed, 5);
  assert.equal(result.reasons.length, 0);
});

test('BLOCK: transaction exceeding $5,000 ceiling triggers POL-EXP-01 Hard Stop', () => {
  const overspendIntent: TransactionIntent = {
    txId: 'TX-TEST-02',
    agentId: 'ProcureBot-AWS-Prod',
    agentCluster: 'us-east-prod',
    merchantName: 'Cloudflare Inc',
    merchantDomain: 'cloudflare.com',
    merchantCountry: 'US',
    mcc: '7372',
    amountUsd: 14500.0,
    currency: 'USD',
    paypalVerified: true,
    dnssecValid: true,
    rolling10mVolume: 4000.0,
  };

  const result = evaluateTransactionPolicy(overspendIntent);
  assert.equal(result.decision, 'BLOCK');
  assert.equal(result.canReleaseToPayPal, false);
  assert.equal(result.primaryRuleTriggered, 'POL-EXP-01');
  assert.match(result.reasons[0], /5,000/);
});

test('REVIEW: unverified merchant domain triggers POL-VENDOR-02 Escrow Hold', () => {
  const unverifiedIntent: TransactionIntent = {
    txId: 'TX-TEST-03',
    agentId: 'MarketingSaaS-Agent',
    agentCluster: 'us-east-prod',
    merchantName: 'Unverified Ad Network',
    merchantDomain: 'ad-track-fast.net',
    merchantCountry: 'US',
    mcc: '7311',
    amountUsd: 2100.0,
    currency: 'USD',
    paypalVerified: false,
    dnssecValid: true,
    rolling10mVolume: 2100.0,
  };

  const result = evaluateTransactionPolicy(unverifiedIntent);
  assert.equal(result.decision, 'REVIEW');
  assert.equal(result.canReleaseToPayPal, false);
  assert.equal(result.primaryRuleTriggered, 'POL-VENDOR-02');
});

test('BLOCK: prompt injection attempt triggers POL-LLM-DRIFT-08 Hard Stop', () => {
  const injectionIntent: TransactionIntent = {
    txId: 'TX-TEST-04',
    agentId: 'AGT-DEV-OPUS-09',
    agentCluster: 'us-east-compute',
    merchantName: 'cloud-scale-relay.io',
    merchantDomain: 'cloud-scale-relay.io',
    merchantCountry: 'US',
    mcc: '7372',
    amountUsd: 4800.0,
    currency: 'USD',
    paypalVerified: true,
    dnssecValid: true,
    rolling10mVolume: 4800.0,
    promptInjectionDetected: true,
    promptIntentDeviation: 82.4,
  };

  const result = evaluateTransactionPolicy(injectionIntent);
  assert.equal(result.decision, 'BLOCK');
  assert.equal(result.canReleaseToPayPal, false);
  assert.equal(result.primaryRuleTriggered, 'POL-LLM-DRIFT-08');
});
