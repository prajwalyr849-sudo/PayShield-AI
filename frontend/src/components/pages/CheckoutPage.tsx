/**
 * PayShield AI — Checkout
 * PayPal Sandbox return page. Verifies the capture server-side before
 * confirming anything. PayPal approval alone is never treated as proof of
 * payment — only a backend-verified COMPLETED capture is.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { PageId } from '../../types';
import { capturePayPalOrder, CapturePayPalOrderResponse } from '../../services/api';
import { EmptyState } from '../common/EmptyState';

export const CheckoutPage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
}> = ({ onNavigate }) => {
  const [orderId, setOrderId] = useState<string | null>(null);
  const [cancelled, setCancelled] = useState(false);
  const [captureResult, setCaptureResult] = useState<CapturePayPalOrderResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [captured, setCaptured] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Parse the PayPal order token from the return URL.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token') || params.get('order_id') || params.get('orderID') || null;
    if (params.has('cancelled')) {
      setCancelled(true);
    } else if (token) {
      setOrderId(token);
    }
  }, []);

  const handleCapture = useCallback(async () => {
    if (!orderId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await capturePayPalOrder(orderId);
      setCaptureResult(result);
      setCaptured(true);
    } catch (err: any) {
      setError(err.message || 'Unable to verify the payment. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [orderId]);

  // Auto-capture when the buyer returns from PayPal.
  useEffect(() => {
    if (orderId && !captured && !loading && !error) {
      handleCapture();
    }
  }, [orderId, captured, loading, error, handleCapture]);

  // Only a backend-verified COMPLETED capture with a receipt navigates onward.
  useEffect(() => {
    const isSuccess =
      captureResult?.success === true &&
      captureResult.payment_status === 'COMPLETED';
    if (isSuccess && captureResult?.receipt_id) {
      onNavigate('receipt-detail', { receiptId: captureResult.receipt_id });
    }
  }, [captureResult, onNavigate]);

  const isFinal = cancelled || error || (captured && captureResult);
  const isSuccess =
    captured &&
    captureResult?.success === true &&
    captureResult.payment_status === 'COMPLETED';

  const statusLabel = captureResult?.payment_status || 'Payment status unavailable';

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <div>
          <h1 className="font-headline-md text-ink">Payment confirmation</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Your payment outcome is verified server-side before any
            confirmation is shown.
          </p>
        </div>
      </div>

      {cancelled ? (
        <div className="ps-card p-8 text-center">
          <span className="material-symbols-outlined text-ink-light text-3xl mb-3">cancel</span>
          <h2 className="font-headline-md text-ink mb-2">Payment cancelled</h2>
          <p className="font-body-sm text-sm text-ink-muted">
            You cancelled the PayPal approval flow. No payment was initiated
            or captured.
          </p>
          <div className="mt-6">
            <button type="button" onClick={() => onNavigate('product-search')} className="ps-btn ps-btn-primary">
              Return to shopping
            </button>
          </div>
        </div>
      ) : (
        <div className="ps-card p-6">
          <div className="flex items-start gap-3">
            <div className="shrink-0 w-10 h-10 rounded-md flex items-center justify-center">
              {loading ? (
                <span className="material-symbols-outlined text-accent text-lg animate-spin">hourglass_empty</span>
              ) : isSuccess ? (
                <span className="material-symbols-outlined text-success text-lg">check_circle</span>
              ) : (
                <span className="material-symbols-outlined text-ink-muted text-lg">pending</span>
              )}
            </div>
            <div className="flex-1">
              <h2 className="font-headline-sm text-lg text-ink font-semibold">
                {statusLabel}
              </h2>
              {captureResult?.reason && (
                <p className="font-body-xs text-xs text-ink-muted mt-1">{captureResult.reason}</p>
              )}
              {orderId && (
                <p className="font-mono text-[11px] text-ink-light mt-2">
                  Order reference: {orderId}
                </p>
              )}
            </div>
          </div>

          {captured && captureResult && (
            <dl className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <p className="font-label-xs text-[10px] text-ink-light">Payment status</p>
                <p className="font-body-xs text-xs text-ink">{captureResult.payment_status}</p>
              </div>
              {captureResult.risk_score != null && (
                <div>
                  <p className="font-label-xs text-[10px] text-ink-light">Risk score</p>
                  <p className="font-tabular text-xs font-semibold text-ink">
                    {captureResult.risk_score}
                  </p>
                </div>
              )}
              <div>
                <p className="font-label-xs text-[10px] text-ink-light">Risk level</p>
                <p className="font-body-xs text-xs text-ink">{captureResult.risk_level || '—'}</p>
              </div>
            </dl>
          )}

          {captureResult?.reconciliation_required && (
            <div className="mt-4 p-3 rounded-md bg-review-subtle border border-review/30 text-review text-sm">
              Reconciliation required for this transaction.
            </div>
          )}

          {!isFinal && (
            <div className="mt-4 p-3 rounded-md border border-border bg-surface">
              <p className="font-body-xs text-xs text-ink-muted">
                Waiting for PayPal buyer approval. Return to this page after
                completing the PayPal flow.
              </p>
            </div>
          )}

          {error && (
            <div className="mt-4 p-3 rounded-md bg-block/10 border border-block/30 text-block text-sm font-medium">
              {error}
              <button
                type="button"
                onClick={handleCapture}
                className="mt-2 ps-btn ps-btn-ghost text-xs underline"
              >
                Retry
              </button>
            </div>
          )}

          {isFinal && !error && (
            <div className="mt-6 flex items-center gap-3">
              {isSuccess && captureResult?.receipt_id && (
                <button
                  type="button"
                  onClick={() => onNavigate('receipt-detail', { receiptId: captureResult.receipt_id })}
                  className="ps-btn ps-btn-primary"
                >
                  <span className="material-symbols-outlined text-xs mr-2">receipt_long</span>
                  View receipt
                </button>
              )}
              <button type="button" onClick={() => onNavigate('product-search')} className="ps-btn ps-btn-ghost">
                Return to shopping
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

function useMemoStatus(status: string | undefined): string {
  switch (status) {
    case 'COMPLETED': return 'Payment verified';
    case 'CAPTURE_PENDING': return 'Capture pending';
    case 'PENDING_AUTH': return 'Pending authorization';
    case 'REVIEW_REQUIRED': return 'Review required';
    case 'FAILED': return 'Payment failed';
    case 'CANCELLED': return 'Payment cancelled';
    case 'BLOCKED': return 'Payment blocked';
    default: return 'Verifying payment…';
  }
}
