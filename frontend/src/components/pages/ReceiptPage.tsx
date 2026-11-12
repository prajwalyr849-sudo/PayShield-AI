/**
 * PayShield AI — Receipt Detail
 * Premium, printable digital payment receipt.
 *
 * Every visible value is fetched from the authoritative backend receipt API;
 * ownership is enforced by the backend on every detail lookup. Missing values
 * render as an em dash — nothing is fabricated.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PageId, ReceiptRecord } from '../../types';
import { getReceipt } from '../../services/api';
import { EmptyState } from '../common/EmptyState';
import { formatDateTime, formatAmount } from '../../utils/dateHelpers';

interface TimelineEvent {
  time: string;
  label: string;
  status: 'success' | 'pending' | 'failed';
}

interface DecisionChip {
  label: string;
  variant: 'allow' | 'review' | 'block' | 'neutral';
}

export const ReceiptPage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
  pendingIntent?: { receiptId?: string } | null;
}> = ({ onNavigate, pendingIntent }) => {
  const [receipt, setReceipt] = useState<ReceiptRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Resolve the receipt reference from the navigation intent or the URL query
  // parameter, matching the backend-enforced lookup contract.
  const receiptId = useMemo(
    () =>
      pendingIntent?.receiptId ??
      (typeof window !== 'undefined'
        ? new URLSearchParams(window.location.search).get('receipt_id') || undefined
        : undefined),
    [pendingIntent]
  );

  const fetchReceipt = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getReceipt(id);
      setReceipt(data);
    } catch (err: any) {
      setError(err.message || 'Unable to load receipt.');
      setReceipt(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (receiptId) fetchReceipt(receiptId);
  }, [receiptId, fetchReceipt]);

  const isSandboxTransaction = useMemo(() => {
    return (
      receipt ? String(receipt.authGate || '').toUpperCase() === 'SANDBOX' || /sandbox/i.test(receipt.merchantDomain || '') : false
    );
  }, [receipt]);

  const paymentSuccessful = useMemo(() => {
    if (!receipt) return false;
    const status = String(receipt.status || '').toUpperCase();
    return status === 'COMPLETED' || status === 'SETTLED' || status === 'CAPTURED';
  }, [receipt]);

  const buildTimeline = useCallback((r: ReceiptRecord): TimelineEvent[] => {
    const events: TimelineEvent[] = [];

    // Canonical events derived only from stored backend fields. Nothing here
    // is invented: each event corresponds to data actually persisted for the
    // receipt (order id, capture id, creation timestamp).
    if (r.orderId) {
      events.push({ time: r.timestamp, label: 'Order recorded', status: 'success' });
    }
    if (r.captureId) {
      events.push({ time: r.updatedAt || r.timestamp, label: 'Payment capture verified', status: 'success' });
    }
    events.push({ time: r.updatedAt || r.timestamp, label: 'Receipt generated', status: 'success' });

    // Events stored by the backend. Preserve their stored status when present.
    (r.events || []).forEach((e: any) => {
      if (e?.received_at || e?.timestamp) {
        const rawStatus = String(e?.status || e?.event_type || '').toLowerCase();
        let status: TimelineEvent['status'] = 'success';
        if (rawStatus.includes('fail') || rawStatus.includes('error')) status = 'failed';
        else if (rawStatus.includes('pend')) status = 'pending';
        events.push({
          time: e.received_at || e.timestamp,
          label: String(e.event_type || e.action || 'Event'),
          status,
        });
      }
    });

    events.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime());
    return events;
  }, []);

  const timeline = useMemo(() => (receipt ? buildTimeline(receipt) : []), [receipt, buildTimeline]);

  const moneyBreakdown = useMemo(() => {
    if (!receipt?.snapshots) return null;
    const s: any = receipt.snapshots;
    const hasBreakdown =
      s.subtotal != null || s.tax != null || s.shipping != null || s.discount != null;
    if (!hasBreakdown) return null;
    return {
      subtotal: s.subtotal,
      tax: s.tax,
      shipping: s.shipping,
      discount: s.discount,
    };
  }, [receipt]);

  const lineItems = useMemo(() => {
    return receipt?.lineItems && receipt.lineItems.length > 0 ? receipt.lineItems : null;
  }, [receipt]);

  const verificationChip = useMemo((): DecisionChip => {
    if (!receipt) return { label: '—', variant: 'neutral' };
    const status = String(receipt.verificationStatus || receipt.status || '').toUpperCase();
    if (status === 'COMPLETED' || status === 'VERIFIED' || status === 'ATTESTED') {
      return { label: 'Verified', variant: 'allow' };
    }
    if (status === 'PENDING') return { label: 'Pending', variant: 'review' };
    if (status === 'EVIDENCE_WARNING' || status === 'REVIEW') {
      return { label: 'Review', variant: 'review' };
    }
    if (status === 'FAILED' || status === 'BLOCKED') return { label: 'Failed', variant: 'block' };
    return { label: receipt.verificationStatus || '—', variant: 'neutral' };
  }, [receipt]);

  const decisionChip = useMemo((): DecisionChip => {
    if (!receipt) return { label: '—', variant: 'neutral' };
    switch (String(receipt.decision || '').toUpperCase()) {
      case 'ALLOW': return { label: 'ALLOW', variant: 'allow' };
      case 'REVIEW': return { label: 'REVIEW', variant: 'review' };
      case 'BLOCK': return { label: 'BLOCK', variant: 'block' };
      default: return { label: receipt.decision || '—', variant: 'neutral' };
    }
  }, [receipt]);

  const paymentMethod = useMemo(() => {
    return receipt?.captureId || receipt?.paypalMid ? 'PayPal' : null;
  }, [receipt]);

  const handlePrint = useCallback(() => {
    window.print();
  }, []);

  const handleCopyReference = useCallback(async () => {
    if (!receipt) return;
    const ref = receipt.id;
    try {
      await navigator.clipboard.writeText(ref);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = ref;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'absolute';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
      } finally {
        document.body.removeChild(textarea);
      }
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [receipt]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-spin">receipt</span>
        <span className="font-body-sm text-sm text-ink-muted">Loading receipt…</span>
      </div>
    );
  }

  if (error || !receipt) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-block text-2xl mb-3">receipt</span>
        <h2 className="font-headline-md text-ink mb-1">Receipt not found</h2>
        <p className="font-body-sm text-sm text-ink-muted mb-6">
          {error || 'No receipt matches that reference. Receipt access is restricted to the owner.'}
        </p>
        <button type="button" onClick={() => onNavigate('receipts')} className="ps-btn ps-btn-primary">
          Back to receipts
        </button>
      </div>
    );
  }

  const capturedAmount = formatAmount(receipt.settledAmount, receipt.currency);
  const referenceShort = receipt.id.length > 22 ? `${receipt.id.slice(0, 12)}…${receipt.id.slice(-6)}` : receipt.id;

  return (
    <div className="ps-receipt-page" id="receipt-page">
      {/* ── Receipt document ── */}
      <div className="ps-receipt">
        <header className="ps-receipt-header">
          <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-primary-deep text-white shadow-sm">
                <span className="material-symbols-outlined text-[14px] font-bold">shield</span>
              </div>
              <div className="flex flex-col">
                <span className="font-headline-sm text-lg text-ink font-semibold tracking-tight leading-none">
                  PayShield<span className="text-primary-deep">AI</span>
                </span>
                <span className="font-label-xs text-[10px] text-ink-light leading-tight">
                  Transaction Security
                </span>
              </div>
            </div>
            <div className="flex items-end gap-3">
              <div>
                <h1 className="font-headline-md text-2xl text-ink font-bold tracking-tight leading-none">
                  Transaction Receipt
                </h1>
                <p className="font-label-xs text-[10px] text-ink-muted">
                  Verified settlement record · PayShield AI
                </p>
              </div>
              <div className="text-right hidden md:block">
                <p className="font-label-xs text-[10px] text-ink-muted">Receipt reference</p>
                <span className="font-mono text-sm text-ink font-semibold break-all">{receipt.id}</span>
                {isSandboxTransaction && (
                  <span className="mt-1 inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-surface text-ink-muted text-[10px] border border-border">
                    <span className="material-symbols-outlined text-[10px]">info</span>
                    PayPal Sandbox
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="mt-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-t border-border pt-4">
            <div className="flex items-center gap-2">
              <span className={`ps-decision ${
                decisionChip.variant === 'allow' ? 'ps-decision-allow' : decisionChip.variant === 'review' ? 'ps-decision-review' : decisionChip.variant === 'block' ? 'ps-decision-block' : 'ps-decision-block'
              }`}>
                {decisionChip.label}
              </span>
              <span className={`ps-badge ${
                verificationChip.variant === 'allow' ? 'ps-badge-allow' : verificationChip.variant === 'review' ? 'ps-badge-review' : verificationChip.variant === 'block' ? 'ps-badge-block' : 'ps-badge-neutral'
              }`}>
                {verificationChip.label}
              </span>
            </div>
            <div className="text-right text-sm">
              <p className="font-mono text-xs text-ink-light">Issued</p>
              <p className="font-mono text-sm text-ink">{formatDateTime(receipt.timestamp)}</p>
            </div>
          </div>
        </header>

        <div className="ps-receipt-body">
          {/* ── Payment summary ── */}
          <section className="ps-receipt-section">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <div className="flex-1">
                <p className="font-label-xs text-[10px] text-ink-muted uppercase tracking-wider">
                  Merchant
                </p>
                <p className="font-headline-sm text-lg text-ink font-semibold leading-tight">{receipt.merchantName}</p>
                <p className="font-label-xs text-[10px] text-ink-light">
                  {receipt.merchantDomain || receipt.paypalMid || 'PayShield merchant'}
                </p>
              </div>
              <div className="text-right">
                <p className="font-label-xs text-[10px] text-ink-muted uppercase tracking-wider">
                  Captured amount
                </p>
                <div className="flex items-baseline gap-1">
                  <span className="font-tabular text-3xl font-bold text-ink tracking-tight">
                    {capturedAmount}
                  </span>
                </div>
                <p className="font-body-xs text-xs text-ink-muted">
                  {receipt.quantity && receipt.quantity > 1
                    ? `× ${receipt.quantity}`
                    : `1 ${receipt.currency}`}
                </p>
              </div>
            </div>
          </section>

          {/* ── Payment details ── */}
          <section className="ps-receipt-section">
            <p className="font-label-sm text-[10px] text-ink-muted uppercase tracking-wider mb-3">
              Payment details
            </p>
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-3">
              <div className="col-span-2 sm:col-span-1">
                <dt className="font-label-xs text-[10px] text-ink-light">Provider order ID</dt>
                <dd className="font-mono text-xs text-ink break-all">{receipt.orderId || '—'}</dd>
              </div>
              <div className="col-span-2 sm:col-span-1">
                <dt className="font-label-xs text-[10px] text-ink-light">PayPal capture reference</dt>
                <dd className="font-mono text-xs text-ink break-all">{receipt.captureId || '—'}</dd>
              </div>
              <div className="col-span-2 sm:col-span-1">
                <dt className="font-label-xs text-[10px] text-ink-light">Payment method</dt>
                <dd className="font-body-xs text-xs text-ink">{paymentMethod || '—'}</dd>
              </div>
              <div className="col-span-2 sm:col-span-1">
                <dt className="font-label-xs text-[10px] text-ink-light">Currency</dt>
                <dd className="font-body-xs text-xs text-ink uppercase tracking-tight">
                  {receipt.currency || '—'}
                </dd>
              </div>
              <div className="col-span-2 sm:col-span-1">
                <dt className="font-label-xs text-[10px] text-ink-light">Transaction date</dt>
                <dd className="font-mono text-xs text-ink">{formatDateTime(receipt.timestamp)}</dd>
              </div>
              <div className="col-span-2 sm:col-span-1">
                <dt className="font-label-xs text-[10px] text-ink-light">Quantity</dt>
                <dd className="font-tabular text-xs text-ink">{receipt.quantity || '—'}</dd>
              </div>
              {paymentMethod && receipt.paypalMid && (
                <div className="col-span-2 sm:col-span-1">
                  <dt className="font-label-xs text-[10px] text-ink-light">Merchant ID</dt>
                  <dd className="font-mono text-[10px] text-ink-light break-all">{receipt.paypalMid}</dd>
                </div>
              )}
              {moneyBreakdown && (
                <>
                  <div className="col-span-2 sm:col-span-1">
                    <dt className="font-label-xs text-[10px] text-ink-light">Subtotal</dt>
                    <dd className="font-tabular text-xs text-ink">{formatAmount(moneyBreakdown.subtotal, receipt.currency)}</dd>
                  </div>
                  <div className="col-span-2 sm:col-span-1">
                    <dt className="font-label-xs text-[10px] text-ink-light">Tax</dt>
                    <dd className="font-tabular text-xs text-ink">{formatAmount(moneyBreakdown.tax, receipt.currency)}</dd>
                  </div>
                  <div className="col-span-2 sm:col-span-1">
                    <dt className="font-label-xs text-[10px] text-ink-light">Shipping</dt>
                    <dd className="font-tabular text-xs text-ink">{formatAmount(moneyBreakdown.shipping, receipt.currency)}</dd>
                  </div>
                  <div className="col-span-2 sm:col-span-1">
                    <dt className="font-label-xs text-[10px] text-ink-light">Discount</dt>
                    <dd className="font-tabular text-xs text-ink">{formatAmount(moneyBreakdown.discount, receipt.currency)}</dd>
                  </div>
                </>
              )}
            </dl>
          </section>

          {/* ── Product details (only when available) ── */}
          {lineItems && (
            <section className="ps-receipt-section">
              <p className="font-label-sm text-[10px] text-ink-muted uppercase tracking-wider mb-3">
                Product details
              </p>
              <table className="ps-table w-full">
                <thead>
                  <tr>
                    <th className="w-12">#</th>
                    <th>Item</th>
                    <th className="text-right w-32">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {lineItems.map((item: any, i: number) => (
                    <tr key={i}>
                      <td className="font-mono text-[10px] text-ink-light">{i + 1}</td>
                      <td className="font-body-xs text-xs text-ink">
                        {String(item?.description || item?.title || 'Item')}
                      </td>
                      <td className="font-tabular text-xs text-ink text-right">
                        {formatAmount(Number(item?.amount || 0), receipt.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {/* ── Security verification ── */}
          <section className="ps-receipt-section">
            <div className="flex items-center justify-between mb-3">
              <p className="font-label-sm text-[10px] text-ink-muted uppercase tracking-wider">
                Security verification
              </p>
            </div>
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-3">
              <div className="col-span-2 sm:col-span-1">
                <dt className="font-label-xs text-[10px] text-ink-light">PayShield decision</dt>
                <dd className={`ps-decision ${
                  decisionChip.variant === 'allow' ? 'ps-decision-allow' : decisionChip.variant === 'review' ? 'ps-decision-review' : decisionChip.variant === 'block' ? 'ps-decision-block' : 'ps-decision-block'
                }`}>
                  {decisionChip.label}
                </dd>
              </div>
              <div className="col-span-2 sm:col-span-1">
                <dt className="font-label-xs text-[10px] text-ink-light">Risk level</dt>
                <dd className={`font-mono text-xs ${
                  receipt.riskLevel?.toLowerCase() === 'high' || receipt.riskLevel?.toLowerCase() === 'critical'
                    ? 'text-block'
                    : receipt.riskLevel?.toLowerCase() === 'medium'
                      ? 'text-review'
                      : 'text-success'
                } font-semibold`}>
                  {receipt.riskLevel || '—'}
                </dd>
              </div>
              <div className="col-span-2 sm:col-span-1">
                <dt className="font-label-xs text-[10px] text-ink-light">Verification status</dt>
                <dd className={`ps-badge ${
                  verificationChip.variant === 'allow' ? 'ps-badge-allow' : verificationChip.variant === 'review' ? 'ps-badge-review' : verificationChip.variant === 'block' ? 'ps-badge-block' : 'ps-badge-neutral'
                }`}>
                  {verificationChip.label}
                </dd>
              </div>
              <div className="col-span-2 sm:col-span-1">
                <dt className="font-label-xs text-[10px] text-ink-light">Verification timestamp</dt>
                <dd className="font-mono text-xs text-ink">
                  {receipt.updatedAt ? formatDateTime(receipt.updatedAt) : '—'}
                </dd>
              </div>
              <div className="col-span-2 sm:col-span-1">
                <dt className="font-label-xs text-[10px] text-ink-light">Risk score</dt>
                <dd className="font-tabular text-xs text-ink font-semibold">
                  {receipt.riskScore != null ? receipt.riskScore : '—'}
                </dd>
              </div>
              <div className="col-span-2 sm:col-span-1">
                <dt className="font-label-xs text-[10px] text-ink-light">Reason</dt>
                <dd className="font-body-xs text-xs text-ink">{receipt.reason || '—'}</dd>
              </div>
            </dl>

            {isSandboxTransaction && (
              <div className="mt-4 p-3 rounded-md bg-block/10 border border-block/30">
                <p className="font-body-xs text-xs text-block">
                  This is a PayPal Sandbox receipt. No real money was transferred and no actual settlement occurred.
                </p>
              </div>
            )}
          </section>

          {/* ── Payment timeline ── */}
          <section className="ps-receipt-section">
            <p className="font-label-sm text-[10px] text-ink-muted uppercase tracking-wider mb-3">
              Payment timeline
            </p>
            {timeline.length === 0 ? (
              <p className="font-body-xs text-xs text-ink-muted">No timeline events recorded.</p>
            ) : (
              <div className="ps-timeline">
                {timeline.map((ev, i) => {
                  const isLast = i === timeline.length - 1;
                  const statusColor =
                    ev.status === 'failed' ? 'text-block' : ev.status === 'pending' ? 'text-review' : 'text-success';
                  return (
                    <div key={i} className="ps-timeline-item">
                      <div className={`ps-timeline-marker ${statusColor}`} />
                      <div className="ps-timeline-content">
                        <p className="font-body-xs text-xs text-ink">{ev.label}</p>
                        <div className="flex items-center gap-1.5">
                          <p className="font-label-xs text-[10px] text-ink-light">
                            {new Date(ev.time).toLocaleString(undefined, {
                              month: 'short',
                              day: 'numeric',
                              year: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </p>
                          {ev.status !== 'success' && (
                            <span className={`px-1.5 py-0.5 rounded-md text-[9px] font-semibold border ${
                              ev.status === 'failed' ? 'bg-block/10 text-block border-block/30' : 'bg-review/10 text-review border-review/30'
                            }`}>
                              {ev.status === 'failed' ? 'Failed' : 'Pending'}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>

        <footer className="ps-receipt-footer">
          <p className="font-label-xs text-[10px] text-ink-light text-center uppercase tracking-wider">
            PayShield AI — Trust Operating System for Agentic Commerce
          </p>
        </footer>
      </div>

      {/* ── Receipt actions (screen only, hidden when printing) ── */}
      <div className="no-print flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex-1 sm:w-auto">
          <button type="button" onClick={handlePrint} className="ps-btn ps-btn-receipt">
            <span className="material-symbols-outlined text-[13px] mr-2">print</span>
            Print receipt
          </button>
        </div>
        <div className="flex-1 sm:w-auto">
          <button
            type="button"
            onClick={handleCopyReference}
            className="ps-btn ps-btn-ghost-muted"
          >
            <span className="material-symbols-outlined text-[13px] mr-2">{copied ? 'done' : 'content_copy'}</span>
            {copied ? 'Copied' : 'Copy receipt reference'}
          </button>
        </div>
        <div className="flex-1 sm:w-auto">
          <button type="button" onClick={() => onNavigate('receipts')} className="ps-btn ps-btn-ghost-muted">
            <span className="material-symbols-outlined text-[13px] mr-2">arrow_back</span>
            Back to receipts
          </button>
        </div>
      </div>
    </div>
  );
};
