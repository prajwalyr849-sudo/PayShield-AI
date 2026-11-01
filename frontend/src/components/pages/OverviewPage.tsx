/**
 * PayShield AI — Overview
 * Operational summary of real transaction activity from the backend.
 * No fabricated metrics: empty backend data renders honest empty states.
 */

import React, { useEffect, useState } from 'react';
import { PageId } from '../../types';
import { ActivityEvent, getTransactionActivity } from '../../services/api';
import { getReceipts } from '../../services/api';
import { EmptyState } from '../common/EmptyState';
import { formatDateShort } from '../../utils/dateHelpers';

interface Metric {
  label: string;
  value: string | number;
  subtitle?: string;
}

export const OverviewPage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
}> = ({ onNavigate }) => {
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [recent, setRecent] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const [activityResp, receiptResp] = await Promise.allSettled([
          getTransactionActivity({ limit: 100 }),
          getReceipts(100),
        ]);

        const activities: ActivityEvent[] =
          activityResp.status === 'fulfilled' ? (activityResp.value.events || []) : [];
        const receipts =
          receiptResp.status === 'fulfilled' ? (receiptResp.value.receipts || []) : [];

        const allowed = activities.filter((a) => a.payshield_decision === 'ALLOW').length;
        const review = activities.filter((a) => a.payshield_decision === 'REVIEW').length;
        const blocked = activities.filter(
          (a) => a.payshield_decision === 'BLOCK' || a.payshield_decision === 'HARD_BLOCK'
        ).length;

        setMetrics([
          { label: 'Total transactions', value: activities.length, subtitle: `${receipts.length} settled receipts` },
          { label: 'Allowed', value: allowed },
          { label: 'Review', value: review },
          { label: 'Blocked', value: blocked },
        ]);

        setRecent(activities.slice(0, 10));
      } catch {
        setError('Unable to load activity. Please try again later.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [onNavigate]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-pulse">hourglass_empty</span>
        <span className="font-body-sm text-sm text-ink-muted">Loading activity…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-block text-2xl mb-3">error</span>
        <h2 className="font-headline-md text-ink mb-1">Unable to load overview</h2>
        <p className="font-body-sm text-sm text-ink-muted mb-6">{error}</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="ps-btn ps-btn-primary"
        >
          Retry
        </button>
      </div>
    );
  }

  const hasActivity = recent.length > 0;

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 className="font-headline-md text-ink">Overview</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Real transaction activity and authorization decisions from PayShield.
          </p>
        </div>
        <button
          type="button"
          onClick={() => onNavigate('transactions')}
          className="ps-btn ps-btn-ghost flex items-center gap-2"
        >
          <span className="material-symbols-outlined text-xs">open_in_new</span>
          View all transactions
        </button>
      </div>

      {/* Compact metrics row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {metrics.map((m) => (
          <div
            key={m.label}
            className="ps-card p-4"
          >
            <p className="font-label-xs text-[10px] text-ink-muted mb-1">{m.label}</p>
            <div className="flex items-baseline gap-1">
              <span className="font-headline-sm text-lg font-tabular text-ink font-semibold">
                {m.value}
              </span>
              {m.subtitle && (
                <span className="font-body-xs text-xs text-ink-light">{m.subtitle}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Recent activity */}
      <div className="ps-card overflow-hidden">
        <div className="ps-section-header">
          <div>
            <h2 className="ps-section-title">Recent activity</h2>
            <p className="ps-section-subtitle">
              {hasActivity
                ? `Last ${recent.length} authorization events`
                : 'No transactions yet.'}
            </p>
          </div>
          {!hasActivity && (
            <button
              type="button"
              onClick={() => onNavigate('product-search')}
              className="ps-btn ps-btn-ghost text-xs"
            >
              Start a product search
            </button>
          )}
        </div>

        {!hasActivity ? (
          <EmptyState
            icon="receipt_long"
            title="No transactions yet"
            description="There are no authorization events in PayShield. Activity appears here once transactions are evaluated by the decision engine."
            actionLabel="Search products"
            onAction={() => onNavigate('product-search')}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="ps-table">
              <thead>
                <tr>
                  <th className="w-32">Reference</th>
                  <th>Order</th>
                  <th className="text-right w-24">Amount</th>
                  <th className="w-20">Decision</th>
                  <th className="w-48">Date</th>
                  <th className="w-20">Action</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((ev) => (
                  <tr key={ev.event_id || ev.payshield_transaction_id}>
                    <td className="font-mono text-[11px] text-ink-light truncate max-w-[140px]">
                      {ev.payshield_transaction_id || ev.paypal_order_id || ev.event_id}
                    </td>
                    <td className="font-body-xs text-xs text-ink-muted truncate max-w-[120px]">
                      {ev.paypal_order_id || '—'}
                    </td>
                    <td className="font-mono text-xs text-ink font-tabular text-right">
                      {ev.paypal_amount ? `${ev.paypal_currency || 'USD'} ${Number(ev.paypal_amount).toLocaleString()}` : '—'}
                    </td>
                    <td>
                      <span className={`ps-decision ${
                        ev.payshield_decision === 'ALLOW'
                          ? 'ps-decision-allow'
                          : ev.payshield_decision === 'REVIEW'
                            ? 'ps-decision-review'
                            : 'ps-decision-block'
                      }`}>
                        {ev.payshield_decision}
                      </span>
                    </td>
                    <td className="font-mono text-[11px] text-ink-light">
                      {formatDateShort(ev.received_at || ev.paypal_create_time)}
                    </td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="ps-btn-icon"
                        title="Copy reference"
                        onClick={() => {
                          navigator.clipboard.writeText(ev.payshield_transaction_id || ev.paypal_order_id || '');
                        }}
                      >
                        <span className="material-symbols-outlined text-[12px]">content_copy</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
