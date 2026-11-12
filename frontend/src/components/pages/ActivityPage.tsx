/**
 * PayShield AI — Activity
 * Compact, searchable stream of real transaction activity from
 * /transactions/activity. Only persisted events are shown.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PageId } from '../../types';
import { getTransactionActivity } from '../../services/api';
import { EmptyState } from '../common/EmptyState';
import { formatDateTime } from '../../utils/dateHelpers';

type ActivityStatus = 'success' | 'warning' | 'error' | 'intercepted' | 'blocked';

function statusOf(decision: string): ActivityStatus {
  switch (decision) {
    case 'ALLOW': return 'success';
    case 'REVIEW': return 'warning';
    case 'BLOCK':
    case 'HARD_BLOCK': return 'blocked';
    default: return 'intercepted';
  }
}

export const ActivityPage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
}> = ({ onNavigate }) => {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const data = await getTransactionActivity({ limit: 200 });
        if (mounted) setEvents(data.events || []);
      } catch {
        setError('Unable to load activity. Please try again later.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [onNavigate]);

  const filtered = useMemo(() => {
    return events.filter((e) => {
      const q = query.toLowerCase();
      const match =
        !q ||
        String(e.event_id || '').toLowerCase().includes(q) ||
        String(e.payshield_transaction_id || '').toLowerCase().includes(q) ||
        String(e.paypal_order_id || '').toLowerCase().includes(q) ||
        String(e.payshield_reason || '').toLowerCase().includes(q) ||
        String(e.actor || '').toLowerCase().includes(q);
      const st = statusOf(e.payshield_decision || '');
      const byStatus =
        statusFilter === 'all' || st === statusFilter;
      return match && byStatus;
    });
  }, [events, query, statusFilter]);

  const counts = useMemo(() => {
    return {
      all: events.length,
      success: events.filter((e) => statusOf(e.payshield_decision || '') === 'success').length,
      warning: events.filter((e) => statusOf(e.payshield_decision || '') === 'warning').length,
      blocked: events.filter((e) => statusOf(e.payshield_decision || '') === 'blocked').length,
    };
  }, [events]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-pulse">history</span>
        <span className="font-body-sm text-sm text-ink-muted">Loading activity…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-block text-2xl mb-3">error</span>
        <h2 className="font-headline-md text-ink mb-1">Unable to load activity</h2>
        <p className="font-body-sm text-sm text-ink-muted mb-6">{error}</p>
        <button type="button" onClick={() => window.location.reload()} className="ps-btn ps-btn-primary">
          Retry
        </button>
      </div>
    );
  }

  const statusPills: { key: ActivityStatus | 'all'; label: string; count: number }[] = [
    { key: 'all', label: 'All events', count: counts.all },
    { key: 'success', label: 'Allowed', count: counts.success },
    { key: 'warning', label: 'Under review', count: counts.warning },
    { key: 'blocked', label: 'Blocked', count: counts.blocked },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <div>
          <h1 className="font-headline-md text-ink">Activity</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Real transaction activity and authorization events.
          </p>
        </div>
      </div>

      <div className="ps-card p-4">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
          <div className="md:col-span-5">
            <label className="ps-label">Search activity</label>
            <input
              className="ps-input"
              placeholder="Reference, order, actor, or reason…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="md:col-span-7">
            <div className="flex gap-2 flex-wrap">
              {statusPills.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  onClick={() => setStatusFilter(p.key === 'all' ? 'all' : p.key)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${
                    statusFilter === (p.key === 'all' ? 'all' : p.key)
                      ? 'bg-accent-subtle text-accent border-accent/30'
                      : 'border-border text-ink-muted hover:text-ink hover:bg-surface'
                  }`}
                >
                  {p.label} ({p.count})
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="ps-card overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-8 text-center">
            <EmptyState
              icon="history"
              title="No activity"
              description={query || statusFilter !== 'all' ? 'No activity events match your filters.' : 'No transaction activity has been recorded yet.'}
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="ps-table">
              <thead>
                <tr>
                  <th className="w-40">Reference</th>
                  <th>Order</th>
                  <th className="text-right w-28">Amount</th>
                  <th className="w-20">Status</th>
                  <th className="w-32">Reason</th>
                  <th className="w-48">Date</th>
                  <th className="w-20">Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((e) => {
                  const st = statusOf(e.payshield_decision || '');
                  return (
                    <tr key={e.event_id || e.payshield_transaction_id || e.paypal_order_id}>
                      <td className="font-mono text-[11px] text-ink-light truncate max-w-[150px]">
                        {e.payshield_transaction_id || e.paypal_order_id || e.event_id}
                      </td>
                      <td className="font-body-xs text-xs text-ink-muted truncate max-w-[130px]">
                        {e.paypal_order_id || '—'}
                      </td>
                      <td className="font-mono text-xs text-ink font-tabular text-right">
                        {e.paypal_amount ? `${e.paypal_currency || 'USD'} ${Number(e.paypal_amount).toLocaleString()}` : '—'}
                      </td>
                      <td>
                        <span className={`ps-decision ${
                          st === 'success' ? 'ps-decision-allow' : st === 'warning' ? 'ps-decision-review' : 'ps-decision-block'
                        }`}>
                          {e.payshield_decision}
                        </span>
                      </td>
                      <td className="font-body-xs text-xs text-ink-muted truncate max-w-[180px]">
                        {e.payshield_reason || '—'}
                      </td>
                      <td className="font-mono text-[11px] text-ink-light">
                        {formatDateTime(e.received_at || e.paypal_create_time)}
                      </td>
                      <td className="text-right">
                        <button
                          type="button"
                          className="ps-btn-icon"
                          title="Copy reference"
                          onClick={() => navigator.clipboard.writeText(e.payshield_transaction_id || e.paypal_order_id || '')}
                        >
                          <span className="material-symbols-outlined text-[12px]">content_copy</span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
