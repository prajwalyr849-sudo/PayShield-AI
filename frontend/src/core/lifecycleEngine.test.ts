import test from 'node:test';
import assert from 'node:assert/strict';
import { canTransition, transitionSession } from './lifecycleEngine.ts';
import type { LifecycleSession } from './lifecycleEngine.ts';

test('valid lifecycle transitions: intent -> evaluation -> approved -> token -> captured -> reconciled', () => {
  let session: LifecycleSession = {
    sessionId: 'LC-TEST-1',
    agentId: 'ProcureBot-AWS-Prod',
    targetVendor: 'Cloudflare Inc.',
    requestedAmount: 1840.0,
    currentState: 'INTENT_DECLARED',
    stateHistory: [{ state: 'INTENT_DECLARED', timestamp: new Date().toISOString() }],
  };

  assert.equal(canTransition('INTENT_DECLARED', 'EVALUATION_ACTIVE'), true);
  let step = transitionSession(session, 'EVALUATION_ACTIVE');
  assert.equal(step.success, true);
  session = step.session;

  assert.equal(canTransition('EVALUATION_ACTIVE', 'AUTO_APPROVED'), true);
  step = transitionSession(session, 'AUTO_APPROVED');
  assert.equal(step.success, true);
  session = step.session;

  assert.equal(canTransition('AUTO_APPROVED', 'GATEWAY_TOKEN_MINTED'), true);
  step = transitionSession(session, 'GATEWAY_TOKEN_MINTED');
  assert.equal(step.success, true);
  session = step.session;
  assert.ok(session.gatewayToken);

  assert.equal(canTransition('GATEWAY_TOKEN_MINTED', 'PAYPAL_CAPTURED'), true);
  step = transitionSession(session, 'PAYPAL_CAPTURED');
  assert.equal(step.success, true);
  session = step.session;

  assert.equal(canTransition('PAYPAL_CAPTURED', 'RECONCILED'), true);
  step = transitionSession(session, 'RECONCILED');
  assert.equal(step.success, true);
  session = step.session;
  assert.ok(session.receiptId);
});

test('prohibited state transition: INTENT_DECLARED cannot jump directly to PAYPAL_CAPTURED', () => {
  const session: LifecycleSession = {
    sessionId: 'LC-TEST-2',
    agentId: 'RogueAgent',
    targetVendor: 'Untrusted',
    requestedAmount: 1000.0,
    currentState: 'INTENT_DECLARED',
    stateHistory: [{ state: 'INTENT_DECLARED', timestamp: new Date().toISOString() }],
  };

  assert.equal(canTransition('INTENT_DECLARED', 'PAYPAL_CAPTURED'), false);
  const step = transitionSession(session, 'PAYPAL_CAPTURED');
  assert.equal(step.success, false);
  assert.match(step.error || '', /Illegal state transition/);
});
