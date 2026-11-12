/**
 * PayShield AI — Audit Logs
 * Compact, searchable table of real audit records from /audit/history.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PageId } from '../../types';
import { getAuditHistory } from '../../services/api';
import { EmptyState } from '../common/EmptyState';
import { formatDateTime, formatAmount } from '../../utils/dateHelpers';

interface AuditRow {
  id: string;
  transactionId: string;
  decision: string;
  merchant: string;
  amount: number | null;
  currency: string;
  timestamp: string;
  eventType: string;
  reason: string;
}

export const AuditLogsPage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
}> = ({ onNavigate }) => {
  const [records, setRecords] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const data = await getAuditHistory(200);
        const rows: AuditRow[] = (data.records || []).map((r) => ({
          id: String(r.record_id || r.transaction_id || '—'),
          transactionId: r.transaction_id || '—',
          decision: String(r.decision || 'UNKNOWN'),
          merchant: r.merchant_name || r.merchant || 'Unknown merchant',
          amount: r.amount != null ? Number(r.amount) : null,
          currency: r.currency || 'USD',
          timestamp: r.timestamp || '—',
          eventType: r.event_type || '—',
          reason: String(r.reason || '—'),
        }));
        if (mounted) setRecords(rows);
      } catch {
        setError('Unable to load audit logs. Please try again later.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [onNavigate]);

  const filtered = useMemo(() => {
    return records.filter((r) => {
      const q = query.toLowerCase();
      return (
        !q ||
        r.id.toLowerCase().includes(q) ||
        r.transactionId.toLowerCase().includes(q) ||
        r.merchant.toLowerCase().includes(q) ||
        r.decision.toLowerCase().includes(q) ||
        r.reason.toLowerCase().includes(q)
      );
    });
  }, [records, query]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-pulse">fingerprint</span>
        <span className="font-body-sm text-sm text-ink-muted">Loading audit logs…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-block text-2xl mb-3">error</span>
        <h2 className="font-headline-md text-ink mb-1">Unable to load audit logs</h2>
        <p className="font-body-sm text-sm text-ink-muted mb-6">{error}</p>
        <button type="button" onClick={() => window.location.reload()} className="ps-btn ps-btn-primary">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <div>
          <h1 className="font-headline-md text-ink">Audit Logs</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Hash-chained server-side audit records. Search by reference, merchant,
            decision, or reason.
          </p>
        </div>
      </div>

      <div className="ps-card p-4">
        <div className="md:col-span-3">
          <label className="ps-label">Search audit events</label>
          <input
            className="ps-input"
            placeholder="Reference, merchant, decision…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="ps-card overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-8 text-center">
            <EmptyState
              icon="fingerprint"
              title="No audit records"
              description={query ? 'No audit records match your search.' : 'No audit records have been logged yet.'}
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="ps-table">
              <thead>
                <tr>
                  <th className="w-40">Record</th>
                  <th className="w-32">Transaction</th>
                  <th>Merchant</th>
                  <th className="text-right w-28">Amount</th>
                  <th className="w-20">Decision</th>
                  <th className="w-32">Event type</th>
                  <th className="w-48">Timestamp</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.id}>
                    <td className="font-mono text-[11px] text-ink-light truncate max-w-[140px]">
                      {r.id}
                    </td>
                    <td className="font-mono text-[11px] text-ink-light truncate max-w-[130px]">
                      {r.transactionId}
                    </td>
                    <td className="font-body-xs text-xs text-ink-muted truncate max-w-[160px]">
                      {r.merchant}
                    </td>
                    <td className="font-mono text-xs text-ink font-tabular text-right">
                      {r.amount != null ? formatAmount(r.amount, r.currency) : '—'}
                    </td>
                    <td>
                      <span className={`ps-decision ${
                        r.decision === 'ALLOW' ? 'ps-decision-allow' : r.decision === 'REVIEW' ? 'ps-decision-review' : 'ps-decision-block'
                      }`}>
                        {r.decision}
                      </span>
                    </td>
                    <td className="font-body-xs text-xs text-ink-muted truncate max-w-[120px]">
                      {r.eventType}
                    </td>
                    <td className="font-mono text-[11px] text-ink-light">
                      {formatDateTime(r.timestamp)}
                    </td>
                    <td className="font-body-xs text-xs text-ink-muted truncate max-w-[200px]">
                      {r.reason}
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
