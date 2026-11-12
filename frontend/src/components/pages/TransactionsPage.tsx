/**
 * PayShield AI — Transactions
 * Professional financial data table of real transaction activity.
 * Data comes exclusively from the backend /transactions/activity endpoint.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PageId } from '../../types';
import { ActivityEvent, getReceipts, getTransactionActivity } from '../../services/api';
import { EmptyState } from '../common/EmptyState';
import { formatDateShort, formatAmount } from '../../utils/dateHelpers';

type SortDirection = 'asc' | 'desc' | null;

interface Column {
  key: string;
  label: string;
  sortable: boolean;
}

const COLUMNS: Column[] = [
  { key: 'reference', label: 'Transaction reference', sortable: false },
  { key: 'merchant', label: 'Merchant', sortable: false },
  { key: 'amount', label: 'Amount', sortable: true },
  { key: 'status', label: 'Status', sortable: false },
  { key: 'date', label: 'Date', sortable: true },
];

export const TransactionsPage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
}> = ({ onNavigate }) => {
  const [rows, setRows] = useState<ActivityEvent[]>([]);
  const [receiptMap, setReceiptMap] = useState<Map<string, { receiptId: string; merchantName: string }>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<{ key: string; dir: SortDirection }>({ key: 'date', dir: 'desc' });

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const [activityResp, receiptResp] = await Promise.allSettled([
          getTransactionActivity({ limit: 200 }),
          getReceipts(200),
        ]);

        const activities: ActivityEvent[] =
          activityResp.status === 'fulfilled' ? (activityResp.value.events || []) : [];
        const receipts =
          receiptResp.status === 'fulfilled' ? (receiptResp.value.receipts || []) : [];

        const map = new Map<string, { receiptId: string; merchantName: string }>();
        receipts.forEach((r) => {
          if (r.orderId) map.set(r.orderId, { receiptId: r.id, merchantName: r.merchantName });
        });
        setReceiptMap(map);
        setRows(activities);
      } catch {
        setError('Unable to load transactions. Please try again later.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [onNavigate]);

  const sorted = useMemo(() => {
    const data = [...rows];
    if (!sort.dir) return data;
    return data.sort((a, b) => {
      let av: unknown;
      let bv: unknown;
      if (sort.key === 'amount') {
        av = Number(a.paypal_amount || 0);
        bv = Number(b.paypal_amount || 0);
      } else if (sort.key === 'date') {
        av = new Date(a.received_at || a.paypal_create_time || 0).getTime();
        bv = new Date(b.received_at || b.paypal_create_time || 0).getTime();
      } else {
        av = String(a[sort.key as keyof ActivityEvent] || '');
        bv = String(b[sort.key as keyof ActivityEvent] || '');
      }
      if (av < bv) return sort.dir === 'asc' ? -1 : 1;
      if (av > bv) return sort.dir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [rows, sort]);

  const handleSort = useCallback((key: string) => {
    setSort((prev) => {
      if (prev.key !== key) return { key, dir: 'asc' };
      if (prev.dir === 'asc') return { key, dir: 'desc' };
      return { key, dir: null };
    });
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-pulse">hourglass_empty</span>
        <span className="font-body-sm text-sm text-ink-muted">Loading transactions…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-block text-2xl mb-3">error</span>
        <h2 className="font-headline-md text-ink mb-1">Unable to load transactions</h2>
        <p className="font-body-sm text-sm text-ink-muted mb-6">{error}</p>
        <button type="button" onClick={() => window.location.reload()} className="ps-btn ps-btn-primary">
          Retry
        </button>
      </div>
    );
  }

  if (sorted.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-2">
          <h1 className="font-headline-md text-ink">Transactions</h1>
        </div>
        <p className="font-body-sm text-sm text-ink-muted">
          Transaction activity appears here once payments are evaluated by PayShield.
        </p>
        <EmptyState
          icon="receipt_long"
          title="No transactions yet"
          description="There are no transactions in PayShield. Evaluated payments and receipts appear in this table."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="font-headline-md text-ink">Transactions</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Real transaction activity and authorization decisions.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onNavigate('overview')}
            className="ps-btn ps-btn-ghost text-xs"
          >
            <span className="material-symbols-outlined text-xs">arrow_back</span>
            Back to overview
          </button>
        </div>
      </div>

      <div className="ps-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="ps-table">
            <thead>
              <tr>
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    className={col.sortable ? 'cursor-pointer select-none' : ''}
                    onClick={() => col.sortable && handleSort(col.key)}
                  >
                    {col.label}
                    {col.sortable && sort.key === col.key && (
                      <span className="ml-1 font-mono text-[10px] text-ink-light">
                        {sort.dir === 'asc' ? '▲' : sort.dir === 'desc' ? '▼' : '⋅'}
                      </span>
                    )}
                  </th>
                ))}
                <th className="w-20">Action</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((ev) => {
                const receipt = receiptMap.get(ev.paypal_order_id || '');
                const reference = ev.payshield_transaction_id || ev.paypal_order_id || ev.event_id;
                const decision = String(ev.payshield_decision || '').toUpperCase();
                return (
                  <tr key={ev.event_id || reference}>
                    <td className="font-mono text-[11px] text-ink-muted truncate max-w-[160px]">
                      {reference}
                    </td>
                    <td className="font-body-xs text-xs text-ink truncate max-w-[140px]">
                      {receipt?.merchantName || ev.paypal_order_id || '—'}
                    </td>
                    <td className="font-amount text-xs text-ink text-right">
                      {ev.paypal_amount
                        ? formatAmount(Number(ev.paypal_amount), ev.paypal_currency)
                        : '—'}
                    </td>
                    <td>
                      <span className={`ps-decision ${
                        decision === 'ALLOW' ? 'ps-decision-allow' : decision === 'REVIEW' ? 'ps-decision-review' : 'ps-decision-block'
                      }`}>
                        {decision}
                      </span>
                    </td>
                    <td className="font-mono text-[11px] text-ink-muted">
                      {formatDateShort(ev.received_at || ev.paypal_create_time)}
                    </td>
                    <td className="text-right">
                      <div className="flex items-center gap-1.5">
                        {receipt && (
                          <button
                            type="button"
                            className="ps-btn-icon"
                            title="View receipt"
                            onClick={() => onNavigate('receipt-detail', { receiptId: receipt.receiptId })}
                          >
                            <span className="material-symbols-outlined text-[12px]">receipt_long</span>
                          </button>
                        )}
                        <button
                          type="button"
                          className="ps-btn-icon"
                          title="Copy reference"
                          onClick={() => navigator.clipboard.writeText(reference)}
                        >
                          <span className="material-symbols-outlined text-[12px]">content_copy</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
