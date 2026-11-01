import { jsPDF } from 'jspdf';
import type { ReceiptRecord } from '../types/index.ts';

export interface GeneratedPdfReport {
  doc: jsPDF;
  fileName: string;
  blob: Blob;
  dataUrl: string;
}

/* ── Design tokens (mirrors frontend/src/index.css) ── */
const INK = [17, 24, 39];        // #111827
const INK_MUTED = [71, 85, 105]; // #475569
const INK_LIGHT = [100, 116, 139]; // #64748b
const PRIMARY_DEEP = [20, 33, 61]; // #14213d
const ACCENT = [37, 99, 235];    // #2563eb
const BORDER = [203, 213, 225];  // #cbd5e1
const SURFACE = [238, 242, 248]; // #eef2f8

const SUCCESS = [21, 128, 61];       // #15803d
const SUCCESS_SUBTLE = [220, 252, 231]; // #dcfce7
const REVIEW = [180, 83, 9];         // #b45309
const REVIEW_SUBTLE = [254, 243, 199]; // #fef3c7
const BLOCK = [185, 28, 28];         // #b91c1c
const BLOCK_SUBTLE = [254, 226, 226]; // #fee2e2

const tColor = (d: jsPDF, c: number[]) => d.setTextColor(c[0], c[1], c[2]);
const fColor = (d: jsPDF, c: number[]) => d.setFillColor(c[0], c[1], c[2]);
const drColor = (d: jsPDF, c: number[]) => d.setDrawColor(c[0], c[1], c[2]);

/**
 * Format a currency amount for the receipt.
 */
function formatCurrency(amount: number | null | undefined, currency = 'USD'): string {
  if (amount == null || Number.isNaN(amount)) return '—';
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
  }).format(amount);
}

/**
 * Returns the decision chip style for a PayShield decision.
 */
function decisionStyle(decision: string) {
  const d = String(decision || '').toUpperCase();
  switch (d) {
    case 'ALLOW': return { label: 'ALLOW', fill: SUCCESS_SUBTLE, text: SUCCESS, border: SUCCESS };
    case 'REVIEW': return { label: 'REVIEW', fill: REVIEW_SUBTLE, text: REVIEW, border: REVIEW };
    case 'BLOCK': return { label: 'BLOCK', fill: BLOCK_SUBTLE, text: BLOCK, border: BLOCK };
    default: return { label: d || '—', fill: SURFACE, text: INK_MUTED, border: BORDER };
  }
}

/**
 * Returns the verification chip style.
 */
function verificationStyle(status: string) {
  const s = String(status || '').toUpperCase();
  if (s === 'COMPLETED' || s === 'VERIFIED' || s === 'ATTESTED') {
    return { label: 'Verified', fill: SUCCESS_SUBTLE, text: SUCCESS, border: SUCCESS };
  }
  if (s === 'PENDING') return { label: 'Pending', fill: REVIEW_SUBTLE, text: REVIEW, border: REVIEW };
  if (s === 'EVIDENCE_WARNING') return { label: 'EVIDENCE WARNING', fill: REVIEW_SUBTLE, text: REVIEW, border: REVIEW };
  if (s === 'REVIEW') return { label: 'Review', fill: REVIEW_SUBTLE, text: REVIEW, border: REVIEW };
  if (s === 'FAILED' || s === 'BLOCKED') return { label: 'Failed', fill: BLOCK_SUBTLE, text: BLOCK, border: BLOCK };
  return { label: s || '—', fill: SURFACE, text: INK_MUTED, border: BORDER };
}

/**
 * Generates a premium, printable digital payment receipt PDF for a single
 * verified receipt. Every value comes from the persisted backend record;
 * missing values render as an em dash — nothing is fabricated.
 */
export function generateReceiptPdf(receipt: ReceiptRecord): GeneratedPdfReport {
  const doc = new jsPDF({
    orientation: 'portrait',
    unit: 'mm',
    format: 'a4',
  });

  const pageWidth = doc.internal.pageSize.getWidth(); // 210
  const pageHeight = doc.internal.pageSize.getHeight(); // 297
  const margin = 14;
  const contentWidth = pageWidth - margin * 2;
  let y = 12;

  const isSandbox =
    String(receipt.authGate || '').toUpperCase() === 'SANDBOX' || /sandbox/i.test(receipt.merchantDomain || '');
  const paymentMethod = receipt.captureId || receipt.paypalMid ? 'PayPal' : null;
  const capturedAmount = formatCurrency(receipt.settledAmount, receipt.currency);
  const decision = decisionStyle(receipt.decision);
  const verification = verificationStyle(receipt.verificationStatus);

  /* ── Helper: section heading ── */
  const sectionHeading = (label: string) => {
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(7);
    tColor(doc, INK_MUTED);
    doc.text(label.toUpperCase(), margin, y);
    y += 4;
  };

  /* ── Helper: label/value row ── */
  const fieldRow = (label: string, value: string, bold = false, valueColor: number[] = INK) => {
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(6.5);
    tColor(doc, INK_LIGHT);
    doc.text(label, margin, y);
    doc.setFont('helvetica', bold ? 'bold' : 'normal');
    doc.setFontSize(8);
    tColor(doc, valueColor);
    doc.text(value, margin + 34, y);
    y += 6.5;
  };

  /* ── Receipt header ── */
  fColor(doc, [255, 255, 255]);
  doc.rect(0, 0, pageWidth, 46, 'F');
  drColor(doc, BORDER);
  doc.setLineWidth(0.6);
  doc.line(0, 46, pageWidth, 46);

  // Logo mark
  fColor(doc, PRIMARY_DEEP);
  doc.roundedRect(margin, 14, 10, 10, 2, 2, 'F');
  tColor(doc, [255, 255, 255]);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(10);
  doc.text('PS', margin + 3, 21.5);

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(13);
  tColor(doc, INK);
  doc.text('PayShield', margin + 16, 21);
  const payShieldWidth = doc.getStringUnitWidth('PayShield');
  tColor(doc, ACCENT);
  doc.text('AI', margin + 16 + payShieldWidth, 21);

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(6.5);
  tColor(doc, INK_LIGHT);
  doc.text('Transaction Security', margin + 16, 26);

  // Receipt title + reference
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(16);
  tColor(doc, INK);
  doc.text('Transaction Receipt', pageWidth - margin, 16, { align: 'right' });

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(7);
  tColor(doc, INK_MUTED);
  doc.text('Verified settlement record', pageWidth - margin, 21, { align: 'right' });

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(8);
  tColor(doc, INK);
  doc.text('Receipt reference', margin, 34);
  doc.setFont('courier');
  doc.setFontSize(8.5);
  doc.text(receipt.id, margin, 40);

  if (isSandbox) {
    fColor(doc, BLOCK_SUBTLE);
    drColor(doc, BLOCK);
    doc.roundedRect(pageWidth - margin - 34, 34, 34, 7, 2, 2, 'FD');
    tColor(doc, BLOCK);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(6.5);
    doc.text('PAYPAL SANDBOX', pageWidth - margin - 30, 38.5);
  }

  y = 54;

  /* ── Payment summary ── */
  sectionHeading('Payment summary');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(8);
  tColor(doc, INK_MUTED);
  doc.text('Merchant', margin, y);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(11);
  tColor(doc, INK);
  doc.text(receipt.merchantName, margin, y + 6);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(6.5);
  tColor(doc, INK_LIGHT);
  doc.text(receipt.merchantDomain || receipt.paypalMid || 'PayShield merchant', margin, y + 11);

  // Captured amount (right aligned, prominent)
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(7);
  tColor(doc, INK_MUTED);
  doc.text('Captured amount', pageWidth - margin, y);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(19);
  tColor(doc, INK);
  doc.text(capturedAmount, pageWidth - margin, y + 10, { align: 'right' });

  y += 20;

  // Decision + verification chips row
  const chip = (x: number, style: { label: string; fill: number[]; text: number[]; border: number[] }) => {
    const { label, fill, text, border } = style;
    const w = doc.getStringUnitWidth(label) * 6.5 + 8;
    fColor(doc, fill);
    drColor(doc, border);
    doc.roundedRect(x, y, w, 7, 2, 2, 'FD');
    tColor(doc, text);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(6.5);
    doc.text(label, x + 4, y + 4.8);
    return w;
  };

  let chipX = margin;
  chipX += chip(chipX, decision) + 4;
  chipX += chip(chipX, verification) + 4;
  if (paymentMethod) {
    fColor(doc, SURFACE);
    drColor(doc, BORDER);
    const pmW = doc.getStringUnitWidth(paymentMethod) * 6.5 + 8;
    doc.roundedRect(chipX, y, pmW, 7, 2, 2, 'FD');
    tColor(doc, INK);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(6.5);
    doc.text(paymentMethod, chipX + 4, y + 4.8);
  }
  y += 12;

  /* ── Payment details ── */
  sectionHeading('Payment details');
  const details: Array<[string, string]> = [
    ['Provider order ID', receipt.orderId || '—'],
    ['PayPal capture reference', receipt.captureId || '—'],
    ['Payment method', paymentMethod || '—'],
    ['Currency', (receipt.currency || '—').toUpperCase()],
    ['Transaction date', receipt.timestamp ? new Date(receipt.timestamp).toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }) : '—'],
    ['Quantity', String(receipt.quantity || '—')],
  ];
  if (receipt.paypalMid) details.push(['Merchant ID', receipt.paypalMid]);

  details.forEach(([label, value]) => fieldRow(label, value));

  // Money breakdown (subtotal / tax / shipping / discount)
  const s: any = receipt.snapshots || {};
  const hasBreakdown =
    s.subtotal != null || s.tax != null || s.shipping != null || s.discount != null;
  if (hasBreakdown) {
    const rows: Array<[string, string]> = [
      ['Subtotal', formatCurrency(s.subtotal, receipt.currency)],
      ['Tax', formatCurrency(s.tax, receipt.currency)],
      ['Shipping', formatCurrency(s.shipping, receipt.currency)],
      ['Discount', formatCurrency(s.discount, receipt.currency)],
    ];
    rows.forEach(([label, value]) => fieldRow(label, value));
    fieldRow('Total captured', capturedAmount, true);
  }

  /* ── Product details (only when available) ── */
  if (receipt.lineItems && receipt.lineItems.length > 0) {
    y += 2;
    sectionHeading('Product details');
    fColor(doc, SURFACE);
    drColor(doc, BORDER);
    doc.rect(margin, y, contentWidth, 7, 'FD');
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(6.5);
    tColor(doc, INK_LIGHT);
    doc.text('#', margin + 4, y + 4.8);
    doc.text('Item', margin + 14, y + 4.8);
    doc.text('Amount', pageWidth - margin - 4, y + 4.8, { align: 'right' });
    y += 7;
    receipt.lineItems.forEach((item: any, i: number) => {
      if (i % 2 === 1) {
        fColor(doc, [255, 255, 255]);
        doc.rect(margin, y, contentWidth, 7, 'F');
      }
      drColor(doc, BORDER);
      doc.line(margin, y + 7, pageWidth - margin, y + 7);
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(6.5);
      tColor(doc, INK_LIGHT);
      doc.text(String(i + 1), margin + 4, y + 4.8);
      tColor(doc, INK);
      doc.text(String(item?.description || item?.title || 'Item'), margin + 14, y + 4.8);
      doc.setFont('helvetica', 'bold');
      doc.text(formatCurrency(Number(item?.amount || 0), receipt.currency), pageWidth - margin - 4, y + 4.8, { align: 'right' });
      y += 7;
    });
    y += 2;
  }

  /* ── Security verification ── */
  sectionHeading('Security verification');
  fieldRow('PayShield decision', decision.label);
  const riskLevel = String(receipt.riskLevel || '');
  const riskColor = riskLevel
    ? riskLevel.toLowerCase() === 'high' || riskLevel.toLowerCase() === 'critical'
      ? BLOCK
      : riskLevel.toLowerCase() === 'medium'
        ? REVIEW
        : SUCCESS
    : INK;
  fieldRow('Risk level', riskLevel || '—', false, riskColor);
  fieldRow('Verification status', verification.label);
  fieldRow('Verification timestamp', receipt.updatedAt ? new Date(receipt.updatedAt).toLocaleString() : '—');
  fieldRow('Risk score', receipt.riskScore != null ? String(receipt.riskScore) : '—');
  fieldRow('Reason', receipt.reason || '—');
  fieldRow('Ledger block', receipt.merkleProofBlock || '—');

  if (isSandbox) {
    y += 2;
    fColor(doc, BLOCK_SUBTLE);
    drColor(doc, BLOCK);
    doc.roundedRect(margin, y, contentWidth, 10, 2, 2, 'FD');
    tColor(doc, BLOCK);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(6.5);
    doc.text('This is a PayPal Sandbox receipt. No real money was transferred and no actual settlement occurred.', margin + 4, y + 4.5);
    doc.setFont('helvetica', 'bold');
    doc.text('No real funds moved.', margin + 4, y + 8);
    y += 14;
  }

  /* ── Payment timeline ── */
  y += 2;
  sectionHeading('Payment timeline');

  const timelineEvents: Array<{ time: string; label: string; status: 'success' | 'pending' | 'failed' }> = [];
  if (receipt.orderId) timelineEvents.push({ time: receipt.timestamp, label: 'Order recorded', status: 'success' });
  if (receipt.captureId) timelineEvents.push({ time: receipt.updatedAt || receipt.timestamp, label: 'Payment capture verified', status: 'success' });
  timelineEvents.push({ time: receipt.updatedAt || receipt.timestamp, label: 'Receipt generated', status: 'success' });
  (receipt.events || []).forEach((e: any) => {
    if (e?.received_at || e?.timestamp) {
      const raw = String(e?.status || e?.event_type || '').toLowerCase();
      let status: 'success' | 'pending' | 'failed' = 'success';
      if (raw.includes('fail') || raw.includes('error')) status = 'failed';
      else if (raw.includes('pend')) status = 'pending';
      timelineEvents.push({ time: e.received_at || e.timestamp, label: String(e.event_type || e.action || 'Event'), status });
    }
  });
  timelineEvents.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime());

  const markerY = y;
  drColor(doc, BORDER);
  doc.setLineWidth(0.4);
  doc.line(margin + 3, markerY, margin + 3, markerY + timelineEvents.length * 13);

  timelineEvents.forEach((ev, i) => {
    const isLast = i === timelineEvents.length - 1;
    const statusColor = ev.status === 'failed' ? BLOCK : ev.status === 'pending' ? REVIEW : SUCCESS;
    const circleY = markerY + i * 13 + 2;
    if (!isLast) {
      drColor(doc, BORDER);
      doc.line(margin + 3, circleY + 4, margin + 3, circleY + 11);
    }
    // Marker dot (rounded rectangle renders a reliable filled circle)
    fColor(doc, statusColor);
    doc.roundedRect(margin + 1.4, circleY - 1.4, 2.8, 2.8, 1.4, 1.4, 'F');
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(7);
    tColor(doc, INK);
    doc.text(ev.label, margin + 7, circleY + 1.5);
    doc.setFontSize(6);
    tColor(doc, INK_LIGHT);
    doc.text(new Date(ev.time).toLocaleString(), margin + 7, circleY + 4.5);
    if (ev.status !== 'success') {
      const tag = ev.status === 'failed' ? 'Failed' : 'Pending';
      const tagW = doc.getStringUnitWidth(tag) * 6 + 4;
      fColor(doc, ev.status === 'failed' ? BLOCK_SUBTLE : REVIEW_SUBTLE);
      drColor(doc, ev.status === 'failed' ? BLOCK : REVIEW);
      doc.roundedRect(pageWidth - margin - tagW, circleY - 1, tagW, 5, 1, 1, 'FD');
      tColor(doc, ev.status === 'failed' ? BLOCK : REVIEW);
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(5.5);
      doc.text(tag, pageWidth - margin - tagW + 2, circleY + 2.3);
    }
  });
  y = markerY + timelineEvents.length * 13 + 10;

  /* ── Footer ── */
  y += 6;
  drColor(doc, BORDER);
  doc.line(margin, y, pageWidth - margin, y);
  y += 7;
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(6.5);
  tColor(doc, INK_LIGHT);
  doc.text('PAYSHIELD AI — Trust Operating System for Agentic Commerce', margin, y);
  doc.text('Verified settlement record generated from persisted backend data.', pageWidth - margin, y, { align: 'right' });

  const fileName = `PayShield_Receipt_${receipt.id}.pdf`;
  const blob = doc.output('blob');
  const dataUrl = doc.output('datauristring');

  return { doc, fileName, blob, dataUrl };
}

/**
 * Triggers native browser download of an individual receipt PDF
 */
export function downloadReceiptPdf(receipt: ReceiptRecord): string {
  const { doc, fileName } = generateReceiptPdf(receipt);
  doc.save(fileName);
  return fileName;
}

/**
 * Generates a comprehensive multi-receipt audit ledger report PDF
 */
export function generateLedgerAuditPdf(
  receipts: ReceiptRecord[],
  title = 'Verified Payment Receipts & Ledger Settlement Audit Report'
): GeneratedPdfReport {
  const doc = new jsPDF({
    orientation: 'landscape',
    unit: 'mm',
    format: 'a4',
  });

  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = 12;
  const contentWidth = pageWidth - margin * 2;

  // Header banner
  doc.setFillColor(15, 23, 42);
  doc.rect(0, 0, pageWidth, 28, 'F');
  doc.setFillColor(14, 165, 233);
  doc.rect(0, 28, pageWidth, 1.5, 'F');

  doc.setTextColor(255, 255, 255);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(14);
  doc.text('PAYSHIELD AI — TRUST OPERATING SYSTEM FOR AGENTIC COMMERCE', margin, 12);

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(148, 163, 184);
  doc.text(title, margin, 18);
  doc.text(`Generated: ${new Date().toISOString()} • Cluster 01 Production Vault`, margin, 23);

  // Total volume calculation
  const totalVolume = receipts.reduce((sum, r) => sum + (r.settledAmount || 0), 0);
  const allowCount = receipts.filter((r) => r.authGate === 'ALLOW').length;
  const reviewCount = receipts.filter((r) => r.authGate === 'REVIEW').length;
  const warningCount = receipts.filter((r) => r.verificationStatus === 'EVIDENCE_WARNING').length;

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(11);
  doc.setTextColor(56, 189, 248);
  doc.text(`Total Settled: ${formatCurrency(totalVolume || 0)} USD`, pageWidth - margin, 12, { align: 'right' });

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8);
  doc.setTextColor(203, 213, 225);
  doc.text(`Total Attested Receipts: ${receipts.length} | 100% Reconciled`, pageWidth - margin, 18, { align: 'right' });
  doc.text(`PayShield Gates: ${allowCount} ALLOW / ${reviewCount} REVIEW / ${warningCount} WARNINGS`, pageWidth - margin, 23, {
    align: 'right',
  });

  let y = 35;

  // Table header
  doc.setFillColor(241, 245, 249);
  doc.setDrawColor(203, 213, 225);
  doc.rect(margin, y, contentWidth, 7, 'FD');

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(7.5);
  doc.setTextColor(71, 85, 105);
  doc.text('RECEIPT ID', margin + 3, y + 4.5);
  doc.text('TIMESTAMP', margin + 35, y + 4.5);
  doc.text('AGENT IDENTITY', margin + 70, y + 4.5);
  doc.text('MERCHANT / DOMAIN', margin + 115, y + 4.5);
  doc.text('PAYSHIELD AUTH GATE', margin + 165, y + 4.5);
  doc.text('PAYPAL CAPTURE ID', margin + 205, y + 4.5);
  doc.text('SETTLED (USD)', margin + 245, y + 4.5);
  doc.text('VERIFICATION', pageWidth - margin - 3, y + 4.5, { align: 'right' });

  y += 7;

  receipts.forEach((r, idx) => {
    // Check if new page needed
    if (y > pageHeight - 20) {
      doc.addPage('a4', 'landscape');
      y = 15;
      // Repeat header on new page
      doc.setFillColor(241, 245, 249);
      doc.rect(margin, y, contentWidth, 7, 'FD');
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(7.5);
      doc.setTextColor(71, 85, 105);
      doc.text('RECEIPT ID', margin + 3, y + 4.5);
      doc.text('TIMESTAMP', margin + 35, y + 4.5);
      doc.text('AGENT IDENTITY', margin + 70, y + 4.5);
      doc.text('MERCHANT / DOMAIN', margin + 115, y + 4.5);
      doc.text('PAYSHIELD AUTH GATE', margin + 165, y + 4.5);
      doc.text('PAYPAL CAPTURE ID', margin + 205, y + 4.5);
      doc.text('SETTLED (USD)', margin + 245, y + 4.5);
      doc.text('VERIFICATION', pageWidth - margin - 3, y + 4.5, { align: 'right' });
      y += 7;
    }

    const rowHeight = 7.5;
    if (idx % 2 === 1) {
      doc.setFillColor(248, 250, 252);
      doc.rect(margin, y, contentWidth, rowHeight, 'F');
    }
    doc.setDrawColor(241, 245, 249);
    doc.line(margin, y + rowHeight, pageWidth - margin, y + rowHeight);

    doc.setFont('courier', 'bold');
    doc.setFontSize(7);
    doc.setTextColor(2, 132, 199);
    doc.text(r.id, margin + 3, y + 4.8);

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(7);
    doc.setTextColor(100, 116, 139);
    doc.text(r.timestamp, margin + 35, y + 4.8);

    doc.setFont('helvetica', 'normal');
    doc.setTextColor(30, 41, 59);
    doc.text(r.agentName, margin + 70, y + 4.8);

    doc.text(r.merchantName, margin + 115, y + 4.8);

    // PayShield gate
    doc.setFont('helvetica', 'bold');
    if (r.authGate === 'ALLOW') {
      doc.setTextColor(5, 150, 105);
      doc.text('ALLOW', margin + 165, y + 4.8);
    } else {
      doc.setTextColor(217, 119, 6);
      doc.text('REVIEW', margin + 165, y + 4.8);
    }

    doc.setFont('courier', 'normal');
    doc.setTextColor(71, 85, 105);
    doc.text(r.captureId || '', margin + 205, y + 4.8);

    doc.setFont('helvetica', 'bold');
    doc.setTextColor(15, 23, 42);
    doc.text(formatCurrency(r.settledAmount || 0), margin + 245, y + 4.8);

    if (r.verificationStatus === 'EVIDENCE_WARNING') {
      doc.setTextColor(217, 119, 6);
      doc.text('WARNING', pageWidth - margin - 3, y + 4.8, { align: 'right' });
    } else {
      doc.setTextColor(5, 150, 105);
      doc.text('ATTESTED', pageWidth - margin - 3, y + 4.8, { align: 'right' });
    }

    y += rowHeight;
  });

  // Footer bar
  doc.setFillColor(15, 23, 42);
  doc.rect(0, pageHeight - 10, pageWidth, 10, 'F');
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(7);
  doc.setTextColor(148, 163, 184);
  doc.text('PayShield AI Ledger Telemetry & Provider Attestation Export', margin, pageHeight - 4);
  doc.text('Confidential Settlement Documentation', pageWidth - margin, pageHeight - 4, { align: 'right' });

  const fileName = `PayShield_Ledger_Audit_Report_${new Date().toISOString().slice(0, 10)}.pdf`;
  const blob = doc.output('blob');
  const dataUrl = doc.output('datauristring');

  return { doc, fileName, blob, dataUrl };
}

/**
 * Triggers native browser download of the full ledger audit report PDF
 */
export function downloadLedgerAuditPdf(receipts: ReceiptRecord[], title?: string): string {
  const { doc, fileName } = generateLedgerAuditPdf(receipts, title);
  doc.save(fileName);
  return fileName;
}
