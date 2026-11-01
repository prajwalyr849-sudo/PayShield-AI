/**
 * PayShield AI — Receipts
 * Clean list of verified settlement receipts from the backend.
 * Receipt detail, printing, reference copying, and PDF generation are real,
 * persisted-data operations.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PageId, ReceiptRecord } from '../../types';
import { getReceipts } from '../../services/api';
import { EmptyState } from '../common/EmptyState';
import { PdfReportModal } from '../common/PdfReportModal';
import { formatDateTime, formatAmount } from '../../utils/dateHelpers';

export const ReceiptsPage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
}> = ({ onNavigate }) => {
  const [receipts, setReceipts] = useState<ReceiptRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [pdfModalOpen, setPdfModalOpen] = useState(false);
  const [pdfTarget, setPdfTarget] = useState<'batch' | 'single' | null>(null);
  const [pdfReceipt, setPdfReceipt] = useState<ReceiptRecord | null>(null);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const data = await getReceipts(200);
        if (mounted) setReceipts(data.receipts || []);
      } catch {
        setError('Unable to load receipts. Please try again later.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [onNavigate]);

  const filtered = useMemo(() => {
    return receipts.filter((r) => {
      const match =
        !query ||
        r.merchantName.toLowerCase().includes(query.toLowerCase()) ||
        r.id.toLowerCase().includes(query.toLowerCase()) ||
        (r.orderId && r.orderId.toLowerCase().includes(query.toLowerCase()));
      const byStatus =
        statusFilter === 'all' || r.status?.toLowerCase() === statusFilter;
      return match && byStatus;
    });
  }, [receipts, query, statusFilter]);

  const handleOpenBatchPdf = useCallback(() => {
    setPdfTarget('batch');
    setPdfReceipt(null);
    setPdfModalOpen(true);
  }, []);

  const handleOpenSinglePdf = useCallback((r: ReceiptRecord) => {
    setPdfTarget('single');
    setPdfReceipt(r);
    setPdfModalOpen(true);
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-pulse">receipt</span>
        <span className="font-body-sm text-sm text-ink-muted">Loading receipts…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-block text-2xl mb-3">error</span>
        <h2 className="font-headline-md text-ink mb-1">Unable to load receipts</h2>
        <p className="font-body-sm text-sm text-ink-muted mb-6">{error}</p>
        <button type="button" onClick={() => window.location.reload()} className="ps-btn ps-btn-primary">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="font-headline-md text-ink">Receipts</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Verified settlement receipts persisted by PayShield.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={handleOpenBatchPdf} className="ps-btn ps-btn-ghost text-xs">
            <span className="material-symbols-outlined text-xs mr-1">description</span>
            Generate audit PDF
          </button>
        </div>
      </div>

      <div className="ps-card p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
          <div className="md:col-span-3">
            <label className="ps-label">Search receipts</label>
            <input
              className="ps-input"
              placeholder="Reference, merchant, or order…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="md:col-span-1">
            <label className="ps-label">Status</label>
            <select
              className="ps-input-sm"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="all">All statuses</option>
              <option value="completed">Completed</option>
              <option value="pending">Pending</option>
              <option value="failed">Failed</option>
            </select>
          </div>
        </div>
      </div>

      <div className="ps-card overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-8 text-center">
            <EmptyState
              icon="article"
              title="No receipts yet"
              description={
                query || statusFilter !== 'all'
                  ? 'No receipts match your current filters.'
                  : 'There are no settlement receipts in PayShield. Receipts appear here after verified payments are captured.'
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="ps-table">
              <thead>
                <tr>
                  <th className="w-40">Reference</th>
                  <th>Merchant</th>
                  <th className="text-right w-28">Amount</th>
                  <th className="w-24">Status</th>
                  <th className="w-20">Decision</th>
                  <th className="w-48">Date</th>
                  <th className="w-44">Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.id}>
                    <td className="font-mono text-[11px] text-ink-muted truncate max-w-[150px]">
                      {r.id}
                    </td>
                    <td className="font-body-xs text-xs text-ink truncate max-w-[130px]">
                      {r.merchantName}
                    </td>
                    <td className="font-amount text-xs text-ink text-right">
                      {r.settledAmount != null
                        ? formatAmount(r.settledAmount, r.currency)
                        : '—'}
                    </td>
                    <td>
                      <span className={`ps-badge ps-badge-neutral`}>
                        {r.status}
                      </span>
                    </td>
                    <td>
                      <span className={`ps-decision ${
                        r.decision === 'ALLOW'
                          ? 'ps-decision-allow'
                          : r.decision === 'REVIEW'
                            ? 'ps-decision-review'
                            : 'ps-decision-block'
                      }`}>
                        {r.decision}
                      </span>
                    </td>
                    <td className="font-mono text-[11px] text-ink-muted">
                      {formatDateTime(r.timestamp)}
                    </td>
                    <td className="text-right">
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          className="ps-btn ps-btn-ghost text-xs"
                          onClick={() => onNavigate('receipt-detail', { receiptId: r.id })}
                        >
                          View receipt
                        </button>
                        <button
                          type="button"
                          className="ps-btn-icon"
                          title="Download receipt PDF"
                          onClick={() => handleOpenSinglePdf(r)}
                        >
                          <span className="material-symbols-outlined text-[12px]">description</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <PdfReportModal
        isOpen={pdfModalOpen}
        onClose={() => setPdfModalOpen(false)}
        receipt={pdfTarget === 'single' ? pdfReceipt : null}
        receiptsBatch={pdfTarget === 'batch' ? filtered : null}
      />
    </div>
  );
};
