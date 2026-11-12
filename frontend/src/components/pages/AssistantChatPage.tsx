/**
 * PayShield AI — AI Assistant
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PageId, PendingIntentPayload, ProductOffer } from '../../types';
import {
  getAssistantStatus,
  sendAssistantChat,
  getAssistantRecommendations,
  guardBuy,
  approveGuardBuyReview,
  guardBuyCheckout,
  guardBuyHandoff,
  recordHandoffOpened,
} from '../../services/api';
import { EmptyState } from '../common/EmptyState';
import { formatAmount } from '../../utils/dateHelpers';

type Stage = 'idle' | 'decision' | 'checkout' | 'handoff';

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  recommendations?: ProductOffer[];
  decision?: { verdict: string; reason: string; reference: string };
}

export const AssistantChatPage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
  pendingIntent?: PendingIntentPayload | null;
}> = ({ onNavigate, pendingIntent }) => {
  const [status, setStatus] = useState<any>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [stage, setStage] = useState<Stage>('idle');
  const [decision, setDecision] = useState<{ verdict: string; reason: string; reference: string; product: ProductOffer } | null>(null);
  const [deliveryAddress, setDeliveryAddress] = useState('');
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [suggested, setSuggested] = useState<string[]>([
    'Search for a laptop under $1,000',
    'Show me verified software subscriptions',
    'Compare two cloud storage plans',
  ]);
  const purchaseInFlight = useRef(false);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const data = await getAssistantStatus();
        if (mounted) setStatus(data);
      } catch {
        if (mounted) setStatus(null);
      } finally {
        if (mounted) setStatusLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (pendingIntent?.product && messages.length === 0 && input === '') {
      setInput(`Evaluate this product: ${pendingIntent.product.title} (${pendingIntent.product.merchantName})`);
    }
  }, [pendingIntent, messages.length, input]);

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const handleSearch = useCallback(async (query: string) => {
    setChatError(null);
    setChatLoading(true);
    try {
      const data = await getAssistantRecommendations({
        query,
        category: undefined,
        currency: 'USD',
        country: 'US',
        max_results: 6,
      });
      const offers = (data.search_results || []).map((o: any) => ({
        id: o.id,
        title: o.title,
        category: o.category,
        merchantName: o.merchantName,
        merchantDomain: o.merchantDomain,
        price: o.price,
        currency: o.currency,
        verification: o.verification,
        dnssec: o.dnssec ?? false,
        kycTrustmark: o.kycTrustmark ?? false,
        reputationScore: o.reputationScore ?? 0,
        specifications: o.specifications ?? [],
        imageUrl: o.imageUrl,
        merchantUrl: o.merchantUrl,
        withinCeiling: o.withinCeiling,
      }));
      addMessage({
        role: 'assistant',
        content: data.summary || `Found ${offers.length} offers for "${query}".`,
        timestamp: new Date().toISOString(),
        recommendations: offers,
      });
    } catch (err: any) {
      setChatError(err.message || 'Search failed. Please try again.');
    } finally {
      setChatLoading(false);
    }
  }, [addMessage]);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const q = input.trim();
    if (!q || chatLoading) return;
    setChatError(null);
    setChatLoading(true);
    const userMsg: ChatMessage = { role: 'user', content: q, timestamp: new Date().toISOString() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');

    const lower = q.toLowerCase();
    try {
      if (lower.includes('buy this') || lower.includes('buy the')) {
        const offer = messages[messages.length - 2]?.recommendations?.[0];
        if (!offer) throw new Error('No product selected to buy.');
        await runGuardBuy(offer);
        return;
      }
      if (lower.includes('approve purchase') || lower.includes('approve review')) {
        if (!decision) throw new Error('No review decision pending.');
        await runApproveReview();
        return;
      }
      if (lower.includes('proceed to checkout')) {
        await runCheckout();
        return;
      }
      if (lower.includes('continue to merchant') || lower.includes('open merchant')) {
        if (!decision) throw new Error('No decision to hand off.');
        await runHandoff();
        return;
      }

      const data = await sendAssistantChat({
        query: q,
        messages: messages.map((m) => ({ role: m.role, content: m.content })),
        currency: 'USD',
        country: 'US',
      });
      addMessage({
        role: 'assistant',
        content: data.reply || '',
        timestamp: data.timestamp || new Date().toISOString(),
        recommendations: (data.search_results || []).map((o: any) => ({
          id: o.id,
          title: o.title,
          category: o.category ?? 'general',
          merchantName: o.merchantName,
          merchantDomain: o.merchantDomain,
          price: o.price,
          currency: o.currency,
          verification: o.verification,
          dnssec: o.dnssec ?? false,
          kycTrustmark: o.kycTrustmark ?? false,
          reputationScore: o.reputationScore ?? 0,
          specifications: o.specifications ?? [],
          imageUrl: o.imageUrl,
          merchantUrl: o.merchantUrl,
          withinCeiling: o.withinCeiling,
        })),
      });
    } catch (err: any) {
      setChatError(err.message || 'Assistant error. Please try again.');
    } finally {
      setChatLoading(false);
    }
  }, [input, chatLoading, messages, decision, addMessage]);

  const runGuardBuy = useCallback(async (offer: ProductOffer) => {
    if (purchaseInFlight.current) return;
    purchaseInFlight.current = true;
    setStage('decision');
    setDecision(null);
    try {
      const result = await guardBuy({
        product_reference: offer.id,
        quantity: 1,
      });
      const verdict = String(result.decision || '').toUpperCase();
      setDecision({
        verdict: verdict === 'ALLOW' ? 'ALLOW' : verdict === 'REVIEW' ? 'REVIEW' : 'BLOCK',
        reason: result.reason || '',
        reference: result.decision_reference || '',
        product: offer,
      });
      addMessage({
        role: 'assistant',
        content: `Guard Buy decision for "${offer.title}": ${verdict}. ${result.reason || ''}`,
        timestamp: new Date().toISOString(),
      });
    } catch (err: any) {
      setChatError(err.message || 'Guard Buy evaluation failed.');
      setStage('idle');
    } finally {
      setChatLoading(false);
      purchaseInFlight.current = false;
    }
  }, []);

  const runApproveReview = useCallback(async () => {
    if (!decision) return;
    setChatLoading(true);
    try {
      const result = await approveGuardBuyReview({
        decision_reference: decision.reference,
        approved: true,
      });
      const verdict = String(result.decision || '').toUpperCase();
      setDecision((prev) => prev ? { ...prev, verdict: verdict === 'ALLOW' ? 'ALLOW' : 'BLOCK' } : null);
      addMessage({
        role: 'assistant',
        content: `Review decision updated: ${verdict}. ${result.reason || ''}`,
        timestamp: new Date().toISOString(),
      });
      if (verdict === 'ALLOW') setStage('checkout');
      else setStage('idle');
    } catch (err: any) {
      setChatError(err.message || 'Review approval failed.');
    } finally {
      setChatLoading(false);
    }
  }, [decision]);

  const runCheckout = useCallback(async () => {
    if (!decision) return;
    if (!deliveryAddress.trim()) {
      setStage('checkout');
      return;
    }
    setCheckoutLoading(true);
    try {
      const result = await guardBuyCheckout({
        decision_reference: decision.reference,
        delivery_address: deliveryAddress,
      });
      if (result.approval_url && /^https:\/\/(.*\.)?paypal\.com/i.test(result.approval_url)) {
        window.location.assign(result.approval_url);
      } else {
        setChatError(result.reason || 'Checkout was not authorized by PayShield.');
        setCheckoutLoading(false);
      }
    } catch (err: any) {
      setChatError(err.message || 'Checkout failed.');
      setCheckoutLoading(false);
    }
  }, [decision, deliveryAddress]);

  const runHandoff = useCallback(async () => {
    if (!decision) return;
    setChatLoading(true);
    try {
      const result = await guardBuyHandoff({
        decision_reference: decision.reference,
        idempotency_key: `gb-handoff-${Date.now()}`,
      });
      if (result.merchant_url) {
        window.open(result.merchant_url, '_blank', 'noopener');
        await recordHandoffOpened({
          decision_reference: decision.reference,
          idempotency_key: `gb-handoff-opened-${Date.now()}`,
        });
        addMessage({
          role: 'assistant',
          content: `Opened ${decision.product.merchantName} in a new tab. PayShield does not verify payment or fulfillment on merchant sites.`,
          timestamp: new Date().toISOString(),
        });
      }
      setStage('idle');
    } catch (err: any) {
      setChatError(err.message || 'Merchant handoff failed.');
    } finally {
      setChatLoading(false);
    }
  }, [decision]);

  const configureMessage = useMemo(() => {
    if (!status) return 'Assistant status unavailable.';
    return status.configured
      ? `Assistant ready · ${status.provider || 'Ollama'}`
      : 'Assistant not configured';
  }, [status]);

  const decisionPanel = useMemo(() => {
    if (!decision) return null;
    const allow = decision.verdict === 'ALLOW';
    const review = decision.verdict === 'REVIEW';
    return (
      <div className="rounded-lg p-4 border shadow-sm">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-2">
            <span className={`ps-badge ${allow ? 'ps-badge-allow' : review ? 'ps-badge-review' : 'ps-badge-block'}`}>
              {allow ? 'AUTHORIZED' : review ? 'UNDER REVIEW' : 'BLOCKED'}
            </span>
            <span className="font-mono text-[10px] text-ink-light">{decision.reference}</span>
          </div>
          <span className="font-mono text-[11px] text-ink-light">
            {decision.product.title}
          </span>
        </div>
        <p className="font-body-xs text-xs text-ink mb-3">{decision.reason}</p>
        <div className="space-y-2">
          {allow && stage !== 'checkout' && (
            <>
              <p className="font-label-xs text-[10px] text-ink-light">Delivery address</p>
              <input
                className="ps-input-sm"
                placeholder="Street address, city, postal code, country"
                value={deliveryAddress}
                onChange={(e) => setDeliveryAddress(e.target.value)}
              />
              <button
                type="button"
                disabled={checkoutLoading}
                onClick={runCheckout}
                className="ps-btn ps-btn-primary w-full text-sm"
              >
                {checkoutLoading ? 'Processing…' : 'Proceed to PayPal checkout'}
              </button>
            </>
          )}
          {review && (
            <button
              type="button"
              disabled={chatLoading}
              onClick={runApproveReview}
              className="ps-btn ps-btn-primary w-full text-sm"
            >
              {chatLoading ? 'Approving…' : 'Approve purchase'}
            </button>
          )}
          {!allow && !review && (
            <p className="font-body-xs text-xs text-block">
              Payment blocked by PayShield. No checkout was initiated.
            </p>
          )}
          {allow && review === false && stage === 'idle' && decision.verdict === 'ALLOW' && (
            <button
              type="button"
              onClick={runHandoff}
              className="ps-btn ps-btn-ghost w-full text-sm"
            >
              Continue to merchant instead
            </button>
          )}
        </div>
      </div>
    );
  }, [decision, stage, deliveryAddress, chatLoading, checkoutLoading, runCheckout, runApproveReview, runHandoff]);

  if (statusLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-pulse">smart_toy</span>
        <span className="font-body-sm text-sm text-ink-muted">Resolving assistant session…</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 className="font-headline-md text-ink">AI Assistant</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Conversational product evaluation and governed purchase flow.
            All decisions are enforced by the backend.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`ps-badge ${status?.configured ? 'ps-badge-allow' : 'ps-badge-neutral'}`}>
            {configureMessage}
          </span>
          <button
            type="button"
            onClick={() => onNavigate('audit-logs')}
            className="ps-btn ps-btn-ghost text-xs"
          >
            <span className="material-symbols-outlined text-xs">receipt_long</span>
            Export audit session
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-3">
          <div className="ps-card p-4 sticky top-6">
            <h2 className="font-label-sm text-[10px] text-ink-muted uppercase tracking-wider mb-3">
              Conversation
            </h2>
            {messages.length === 0 ? (
              <div className="h-32 flex flex-col items-center justify-center rounded-lg border border-dashed border-border p-3">
                <span className="material-symbols-outlined text-ink-light text-xl mb-2">chat</span>
                <p className="font-body-xs text-xs text-ink-muted text-center">No conversation yet.</p>
              </div>
            ) : (
              <div className="space-y-3 max-h-[60vh] overflow-y-auto">
                {messages.map((m, i) => (
                  <div key={i} className={`p-2 rounded-md ${
                    m.role === 'user' ? 'bg-accent-subtle' : 'bg-surface'
                  } border border-border/50`}>
                    <p className="font-label-xs text-[10px] text-ink-light mb-1">
                      {m.role === 'user' ? 'You' : 'PayShield Assistant'}
                    </p>
                    <p className="font-body-xs text-xs text-ink whitespace-pre-line break-words">{m.content}</p>
                    </div>
                  ))}
                </div>
            )}
          </div>
        </div>

        <div className="lg:col-span-6 flex flex-col">
          <div className="flex-1 min-h-0 flex flex-col">
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.length === 0 && (
                <div className="flex flex-col items-center justify-center h-48 text-center">
                  <span className="material-symbols-outlined text-ink-light text-3xl mb-3">smart_toy</span>
                  <p className="font-body-sm text-sm text-ink-muted">
                    Ask me to search for products, evaluate a purchase, or explain a decision.
                  </p>
                </div>
              )}
              {messages.map((m) =>
                <div key={m.timestamp + m.role} className="flex gap-3">
                  <div className="shrink-0 w-8 h-8 rounded-md flex items-center justify-center">
                    <span className="material-symbols-outlined text-[13px]">
                      {m.role === 'user' ? 'person' : 'shield'}
                    </span>
                  </div>
                  <div className={`flex-1 p-3 rounded-lg ${
                    m.role === 'user'
                      ? 'bg-accent text-white shadow-sm'
                      : 'bg-surface border border-border shadow-sm'
                  }`}>
                    {m.role === 'user' ? (
                      <p className="font-body-sm text-sm text-white whitespace-pre-line break-words">{m.content}</p>
                    ) : (
                      <>
                        <p className="font-body-sm text-sm text-ink whitespace-pre-line break-words mb-2">{m.content}</p>
                        {m.recommendations && m.recommendations.length > 0 && (
                          <div className="mt-2 space-y-2">
                            <p className="font-label-xs text-[10px] text-ink-light">Product recommendations</p>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              {m.recommendations.map((offer) => (
                                <div key={offer.id} className="p-2 rounded-md border border-border bg-surface">
                                  <p className="font-body-xs text-xs text-ink line-clamp-1 mb-1">{offer.title}</p>
                                  <p className="font-tabular text-xs font-semibold text-ink">
                                    {formatAmount(offer.price, offer.currency)}
                                  </p>
                                  <p className="font-label-xs text-[10px] text-ink-muted">
                                    {offer.merchantName}
                                  </p>
                                  <button
                                    type="button"
                                    className="mt-1 ps-btn ps-btn-ghost w-full text-[10px] px-2 py-1"
                                    onClick={() => {
                                      setInput('');
                                      runGuardBuy(offer);
                                    }}
                                  >
                                    Buy this
                                  </button>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
                )}
                {chatLoading && (
                  <div className="flex gap-2">
                    <div className="shrink-0 w-8 h-8 rounded-md flex items-center justify-center">
                      <span className="material-symbols-outlined text-[13px]">shield</span>
                    </div>
                    <div className="flex-1 p-3 rounded-lg bg-surface border border-border shadow-sm">
                      <div className="h-4 bg-surface rounded-full animate-pulse"></div>
                    </div>
                  </div>
                )}
            </div>
            {chatError && (
              <div className="p-3 rounded-md bg-block/10 border border-block/30 text-block text-sm font-medium">
                {chatError}
                <button
                  type="button"
                  onClick={() => setChatError(null)}
                  className="ml-2 font-label-xs text-[10px] underline"
                >
                  Dismiss
                </button>
              </div>
            )}
            <form onSubmit={handleSubmit} className="p-3 border-t border-border bg-surface">
              <div className="flex gap-2">
                <input
                  className="flex-1 ps-input"
                  placeholder="Ask PayShield…"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  disabled={chatLoading}
                />
                <button
                  type="submit"
                  disabled={chatLoading || !input.trim()}
                  className="ps-btn ps-btn-primary"
                >
                  Send
                </button>
              </div>
            </form>
          </div>
        </div>

        <div className="lg:col-span-3">
          {decision && <div className="sticky top-6">{decisionPanel}</div>}
          {!decision && (
            <div className="ps-card p-4">
              <h2 className="font-label-sm text-[10px] text-ink-muted uppercase tracking-wider mb-3">
                Suggested prompts
              </h2>
              <div className="space-y-2">
                {suggested.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setInput(p)}
                    className="ps-btn ps-btn-ghost w-full text-xs text-left"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
