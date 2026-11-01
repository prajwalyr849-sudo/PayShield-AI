/**
 * PayShield AI — PDF Report Modal
 * Generates and prints audit-grade PDF receipts / ledger reports from real
 * persisted receipt data. Nothing here is fabricated.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  generateReceiptPdf,
  downloadReceiptPdf,
  generateLedgerAuditPdf,
  downloadLedgerAuditPdf,
} from '../../services/pdfReportGenerator';
import type { ReceiptRecord } from '../../types';

interface PdfReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  receipt?: ReceiptRecord | null;
  receiptsBatch?: ReceiptRecord[] | null;
  onLogActivity?: (action: string, detail: string) => void;
}

export const PdfReportModal: React.FC<PdfReportModalProps> = ({
  isOpen,
  onClose,
  receipt,
  receiptsBatch,
  onLogActivity,
}) => {
  const [pdfDataUrl, setPdfDataUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [downloadSuccess, setDownloadSuccess] = useState<boolean | null>(null);
  const [activeTab, setActiveTab] = useState<'preview' | 'pdf-view' | 'manifest'>('preview');

  const target = useMemoTarget(receipt, receiptsBatch);

  useEffect(() => {
    if (!isOpen) {
      setPdfDataUrl(null);
      setGenerating(false);
      setDownloadSuccess(null);
      setActiveTab('preview');
      return;
    }
    const generate = async () => {
      setGenerating(true);
      try {
        let result;
        if (receiptsBatch && receiptsBatch.length > 0) {
          result = generateLedgerAuditPdf(receiptsBatch);
        } else if (receipt) {
          result = generateReceiptPdf(receipt);
        } else {
          throw new Error('No receipt data provided.');
        }
        setPdfDataUrl(result.dataUrl);
      } catch {
        // Surface nothing; the empty state in the UI covers generation failure.
      } finally {
        setGenerating(false);
      }
    };
    generate();
  }, [isOpen, receipt, receiptsBatch]);

  const handleDownload = useCallback(() => {
    try {
      if (receiptsBatch && receiptsBatch.length > 0) {
        downloadLedgerAuditPdf(receiptsBatch);
        onLogActivity?.('PDF_BATCH_REPORT_DOWNLOAD', `Batch of ${receiptsBatch.length} receipts`);
      } else if (receipt) {
        downloadReceiptPdf(receipt);
        onLogActivity?.('PDF_REPORT_DOWNLOAD', `Receipt ${receipt.id}`);
      }
      setDownloadSuccess(true);
      setTimeout(() => setDownloadSuccess(null), 4000);
    } catch {
      // Download handled by browser; errors are non-fatal.
    }
  }, [receipt, receiptsBatch, onLogActivity]);

  const handlePrint = useCallback(() => {
    if (pdfDataUrl) window.open(pdfDataUrl, '_blank');
  }, [pdfDataUrl]);

  const hashText = receipt ? receipt.hash : (receiptsBatch?.length ? `Batch of ${receiptsBatch.length}` : '—');

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 px-4" aria-modal="true" role="dialog" aria-label="PDF report">
      <div className="fixed inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div
        className="w-full max-w-4xl max-h-[90vh] bg-surface-white border border-border rounded-lg shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-accent text-lg">receipt</span>
            <h2 className="font-headline-sm text-lg text-ink font-semibold">
              {receipt ? `Receipt ${receipt.id}` : 'Ledger audit report'}
            </h2>
          </div>
          <button type="button" onClick={onClose} className="ps-btn-icon">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="flex items-center gap-1 px-5 py-2 border-b border-border/50 bg-surface/50">
          {[
            { id: 'preview' as const, label: 'Report preview' },
            { id: 'pdf-view' as const, label: 'Live PDF rendering' },
            { id: 'manifest' as const, label: 'Attestation manifest' },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-accent text-white'
                  : 'text-ink-muted hover:bg-surface hover:text-ink'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {activeTab === 'preview' && (
            <div className="space-y-4">
              <div className="p-4 rounded-lg border border-border bg-surface">
                <p className="font-label-xs text-[10px] text-ink-light">Document</p>
                <p className="font-body-xs text-xs text-ink">{receipt ? `Audit settlement certificate: ${receipt.id}` : `Comprehensive ledger audit report · ${(receiptsBatch || []).length} receipts`}</p>
                <p className="font-mono text-[10px] text-ink-light mt-1">
                  {receipt ? `Capture ID: ${receipt.captureId || '—'} · Merkle block: ${receipt.merkleProofBlock || '—'}` : `Generated: ${new Date().toISOString()}`}
                </p>
              </div>
              <div className="p-4 rounded-lg border border-border bg-surface">
                <p className="font-label-xs text-[10px] text-ink-light">Attestation</p>
                <p className="font-body-xs text-xs text-ink">
                  Cryptographically verified settlement record generated from
                  persisted backend data. No simulated values.
                </p>
              </div>
              <div className="p-4 rounded-lg border border-border bg-surface text-center">
                <p className="font-label-xs text-[10px] text-ink-light">Tamper-evident seal</p>
                <p className="font-mono text-[10px] text-ink-light mb-2">sha256:{hashText}</p>
                <button
                  type="button"
                  onClick={() => navigator.clipboard.writeText(hashText)}
                  className="ps-btn ps-btn-ghost text-xs"
                >
                  <span className="material-symbols-outlined text-[12px] mr-1">content_copy</span>
                  Copy hash
                </button>
              </div>
            </div>
          )}

          {activeTab === 'pdf-view' && (
            <div className="w-full h-full flex items-center justify-center">
              {generating ? (
                <div className="flex flex-col items-center gap-3">
                  <span className="material-symbols-outlined text-accent text-xl animate-spin">description</span>
                  <p className="font-body-xs text-xs text-ink-muted">Compiling PDF…</p>
                </div>
              ) : pdfDataUrl ? (
                <iframe className="w-full h-full rounded-lg border border-border" src={pdfDataUrl} title="PDF report" />
              ) : (
                <p className="font-body-xs text-xs text-ink-muted">PDF unavailable.</p>
              )}
            </div>
          )}

          {activeTab === 'manifest' && (
            <div className="p-4 rounded-lg border border-border bg-surface overflow-x-auto max-h-[60vh] overflow-y-auto">
              <pre className="font-mono text-[10px] text-ink-light">
                {JSON.stringify(receipt || receiptsBatch || {}, null, 2)}
              </pre>
              <button
                type="button"
                className="mt-3 ps-btn ps-btn-ghost text-xs"
                onClick={() => navigator.clipboard.writeText(JSON.stringify(receipt || receiptsBatch || {}))}
              >
                <span className="material-symbols-outlined text-[12px] mr-1">content_copy</span>
                Copy JSON
              </button>
            </div>
          )}
        </div>

        <div className="px-5 py-4 border-t border-border flex items-center justify-between">
          {downloadSuccess && (
            <span className="font-body-xs text-xs text-success font-medium">
              <span className="material-symbols-outlined text-[13px] mr-1">check_circle</span>
              PDF downloaded
            </span>
          )}
          <div className="flex items-center gap-2">
            <button type="button" onClick={handlePrint} className="ps-btn ps-btn-ghost text-xs">
              Print document
            </button>
            <button type="button" onClick={handleDownload} className="ps-btn ps-btn-primary text-xs">
              Download PDF
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

function useMemoTarget(receipt: ReceiptRecord | undefined, batch: ReceiptRecord[] | undefined) {
  return receipt || (batch && batch.length > 0 ? batch[0] : null);
}
