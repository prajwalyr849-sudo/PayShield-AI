import test from 'node:test';
import assert from 'node:assert/strict';
import { generateReceiptPdf, generateLedgerAuditPdf } from '../services/pdfReportGenerator.ts';
import type { ReceiptRecord } from '../types/index.ts';

const mockReceiptAllowed: ReceiptRecord = {
  id: 'RCP-2025-99418',
  hash: 'sha256:0b84e8912d7a9b8f',
  timestamp: '2025-05-18 14:12:08 UTC',
  orderId: 'ORD-2025-99418',
  transactionId: 'txn_99418',
  agentName: 'ProcureBot-AWS-Prod',
  agentId: 'agent:procure-08',
  merchantName: 'Cloudflare Enterprise Inc.',
  merchantDomain: 'cloudflare.com',
  mcc: '7372 (Compute/Data)',
  paypalMid: 'CLOUD-FL-99214-PP',
  taxId: 'XX-XXX4910',
  authGate: 'ALLOW',
  captureId: 'cap_9a87d12f99014b2',
  settledAmount: 14500.0,
  currency: 'USD',
  quantity: 1,
  status: 'COMPLETED',
  decision: 'ALLOW',
  reason: '',
  verificationStatus: 'ATTESTED',
  riskScore: 0,
  riskLevel: 'LOW',
  snapshots: {},
  events: [],
  updatedAt: '2025-05-18 14:12:08 UTC',
  lineItems: [
    {
      description: 'Enterprise Bandwidth Tier 3 Add-on',
      detail: '100TB Pool • Edge Transit Cluster US-East',
      amount: 12000.0,
    },
    {
      description: 'Edge Worker Compute Dedicated Pack',
      detail: '20M Invocations / mo reserved capacity',
      amount: 2500.0,
    },
  ],
  agentIntentSig: '0x9a7b21e84fcc9910ac77b312ec4188',
  policyToken: 'POL-INFRA-CAP-BREACH (Overridden by SecOps #819)',
  merkleProofBlock: '891092',
};

const mockReceiptWarning: ReceiptRecord = {
  id: 'RCP-2025-99415',
  hash: 'sha256:bb31cc49120fa712',
  timestamp: '2025-05-18 10:04:19 UTC',
  orderId: 'ORD-2025-99415',
  transactionId: 'txn_99415',
  agentName: 'MarketingSaaS-Agent',
  agentId: 'agent:mktg-autoscale',
  merchantName: 'AdRoll Retargeting',
  merchantDomain: 'adroll.com',
  mcc: '7311',
  paypalMid: 'ADROLL-PAYPAL-99',
  taxId: 'XX-XXX3190',
  authGate: 'REVIEW',
  captureId: 'cap_55ef9012',
  settledAmount: 8500.0,
  currency: 'USD',
  quantity: 1,
  status: 'PENDING',
  decision: 'REVIEW',
  reason: 'Anomaly detected',
  verificationStatus: 'EVIDENCE_WARNING',
  riskScore: 75,
  riskLevel: 'HIGH',
  snapshots: {},
  events: [],
  updatedAt: '2025-05-18 10:04:19 UTC',
  lineItems: [
    {
      description: 'Targeted Retargeting Ad Credits Tier 3',
      detail: 'Unitemized Ad Campaign Top-up',
      amount: 8500.0,
    },
  ],
  agentIntentSig: '0xbb3109ff124a9102',
  policyToken: 'POL-EXCESS-ANOMALY (Manual Overwrite)',
  merkleProofBlock: '891060',
};

test('generateReceiptPdf: generates valid PDF capturing verified payment status and PayShield authorization decision', () => {
  const result = generateReceiptPdf(mockReceiptAllowed);

  // Assert valid return structure
  assert.ok(result.doc, 'jsPDF instance must exist');
  assert.equal(result.fileName, 'PayShield_Receipt_RCP-2025-99418.pdf');
  assert.ok(result.dataUrl.startsWith('data:application/pdf;'), 'Data URL must be valid application/pdf');

  // Verify binary output
  const pdfString = result.doc.output();
  assert.ok(pdfString.startsWith('%PDF-'), 'Output must start with PDF header marker');

  // Verify capturing PayShield Authorization Decision details
  assert.ok(pdfString.includes('PAYSHIELD'), 'Must include PayShield header');
  assert.ok(pdfString.includes('ALLOW'), 'Must include ALLOW gate decision');
  assert.ok(pdfString.includes('891092'), 'Must include Merkle block number');

  // Verify capturing Verified Payment Status details
  assert.ok(pdfString.includes('cap_9a87d12f99014b2'), 'Must include PayPal capture ID');
  assert.ok(pdfString.includes('CLOUD-FL-99214-PP'), 'Must include PayPal MID');
  assert.ok(pdfString.includes('Cloudflare Enterprise Inc.'), 'Must include merchant name');
});

test('generateReceiptPdf: correctly handles EVIDENCE_WARNING receipt and reflects warning state', () => {
  const result = generateReceiptPdf(mockReceiptWarning);

  assert.ok(result.doc);
  assert.equal(result.fileName, 'PayShield_Receipt_RCP-2025-99415.pdf');

  const pdfString = result.doc.output();
  assert.ok(pdfString.includes('REVIEW'), 'Must capture REVIEW authorization decision');
  assert.ok(pdfString.includes('cap_55ef9012'), 'Must include PayPal capture ID');
  assert.ok(pdfString.includes('EVIDENCE WARNING'), 'Must reflect evidence warning status');
});

test('generateLedgerAuditPdf: compiles multi-record ledger audit PDF report', () => {
  const receipts = [mockReceiptAllowed, mockReceiptWarning];
  const result = generateLedgerAuditPdf(receipts);

  assert.ok(result.doc);
  assert.ok(result.fileName.startsWith('PayShield_Ledger_Audit_Report_'));
  assert.ok(result.dataUrl.startsWith('data:application/pdf;'));

  const pdfString = result.doc.output();
  assert.ok(pdfString.startsWith('%PDF-'));
  assert.ok(pdfString.includes('RCP-2025-99418'));
  assert.ok(pdfString.includes('RCP-2025-99415'));
  assert.ok(pdfString.includes('ALLOW'));
  assert.ok(pdfString.includes('cap_9a87d12f99014b2'));
});
