/**
 * PayShield AI — Audit Investigation
 * Real Elasticsearch audit search from /audit/elastic. Only reachable when the
 * backend reports the index as configured and reachable.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { PageId } from '../../types';
import {
  getElasticStatus,
  searchElasticAudit,
  ElasticStatus,
} from '../../services/api';
import { EmptyState } from '../common/EmptyState';

export const AuditInvestigationPage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
}> = ({ onNavigate }) => {
  const [status, setStatus] = useState<ElasticStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [decisionFilter, setDecisionFilter] = useState('ALL');
  const [riskFilter, setRiskFilter] = useState('ALL');
  const [results, setResults] = useState<any[]>([]);
  const [count, setCount] = useState(0);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<any>(null);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const data = await getElasticStatus();
        if (mounted) setStatus(data);
      } catch (err: any) {
        if (mounted) setStatusError(err.message || 'Unable to reach Elasticsearch status.');
      }
    };
    load();
    return () => { mounted = false; };
  }, []);

  const reachable = status?.reachable === true;
  const configured = status?.configured === true;

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;
    setSearchError(null);
    setSearchLoading(true);
    try {
      const data = await searchElasticAudit({
        query: query.trim(),
        decision: decisionFilter === 'ALL' ? undefined : decisionFilter,
        risk_level: riskFilter === 'ALL' ? undefined : riskFilter,
        size: 50,
      });
      setResults(data.results || []);
      setCount(data.count || 0);
    } catch (err: any) {
      setSearchError(err.message || 'Search failed. Please try again.');
    } finally {
      setSearchLoading(false);
    }
  }, [query, decisionFilter, riskFilter]);

  if (!configured) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-ink-light text-3xl mb-3">fingerprint</span>
        <h2 className="font-headline-md text-ink mb-2">Audit search not configured</h2>
        <p className="font-body-sm text-sm text-ink-muted mb-6">
          The Elasticsearch audit index is not configured on this cluster.
        </p>
        {statusError && <p className="font-body-xs text-xs text-ink-muted">{statusError}</p>}
      </div>
    );
  }

  if (!reachable) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-block text-3xl mb-3">error</span>
        <h2 className="font-headline-md text-ink mb-2">Index unreachable</h2>
        <p className="font-body-sm text-sm text-ink-muted mb-6">
          The audit index could not be reached.
        </p>
        {status?.reason && <p className="font-body-xs text-xs text-ink-muted">{status.reason}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <div>
          <h1 className="font-headline-md text-ink">Audit investigation</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Search the audit index with Lucene DSL. Results come from the live
            backend index.
          </p>
        </div>
      </div>

      <div className="ps-card p-4">
        <div className="flex items-center gap-2">
          <span className={`ps-badge ps-badge-allow`}>
            {status?.cluster_name || 'Audit index'} · reachable
          </span>
          <span className="font-mono text-[11px] text-ink-light">
            {status?.index || '—'}
          </span>
        </div>
      </div>

      <div className="ps-card p-4">
        <form onSubmit={(e) => { e.preventDefault(); handleSearch(); }} className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
          <div className="md:col-span-6">
            <label className="ps-label">Lucene query</label>
            <input
              className="ps-input"
              placeholder={'e.g. agent.id:"procure-cloud-08" AND amount_usd:>5000'}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <label className="ps-label">Decision</label>
            <select
              className="ps-input-sm"
              value={decisionFilter}
              onChange={(e) => setDecisionFilter(e.target.value)}
            >
              <option value="ALL">All decisions</option>
              <option value="ALLOW">ALLOW</option>
              <option value="REVIEW">REVIEW</option>
              <option value="BLOCK">BLOCK</option>
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="ps-label">Risk level</label>
            <select
              className="ps-input-sm"
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
            >
              <option value="ALL">All levels</option>
              <option value="LOW">LOW</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="HIGH">HIGH</option>
              <option value="CRITICAL">CRITICAL</option>
            </select>
          </div>
          <div className="md:col-span-2">
            <button
              type="submit"
              disabled={searchLoading}
              className="ps-btn ps-btn-primary w-full"
            >
              Query index
            </button>
          </div>
        </form>
      </div>

      {searchError && (
        <div className="p-3 rounded-md bg-block/10 border border-block/30 text-block text-sm font-medium">
          {searchError}
        </div>
      )}

      <div className="ps-card overflow-hidden">
        {results.length === 0 && !searchLoading ? (
          <div className="p-8 text-center">
            <EmptyState
              icon="fingerprint"
              title="No results"
              description="No audit events match your query."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="ps-table">
              <thead>
                <tr>
                  <th className="w-40">Order / transaction</th>
                  <th>Merchant</th>
                  <th className="text-right w-28">Amount</th>
                  <th className="w-20">Decision</th>
                  <th className="w-24">Action</th>
                </tr>
              </thead>
              <tbody>
                {results.map((rec) => (
                  <tr key={rec.transaction_id || rec.external_order_id || rec.order_id || rec._id} onClick={() => setSelected(rec)} className="cursor-pointer">
                    <td className="font-mono text-[11px] text-ink-light truncate max-w-[150px]">
                      {rec.transaction_id || rec.external_order_id || rec.order_id || 'UNKNOWN'}
                    </td>
                    <td className="font-body-xs text-xs text-ink-muted truncate max-w-[150px]">
                      {rec.merchant || rec.merchant_name || 'Unknown merchant'}
                    </td>
                    <td className="font-mono text-xs text-ink font-tabular text-right">
                      {rec.amount != null ? new Intl.NumberFormat(undefined, { style: 'currency', currency: rec.currency || 'USD' }).format(Number(rec.amount)) : '—'}
                    </td>
                    <td>
                      <span className={`ps-decision ${
                        rec.final_decision === 'ALLOW' ? 'ps-decision-allow' : rec.final_decision === 'REVIEW' ? 'ps-decision-review' : 'ps-decision-block'
                      }`}>
                        {rec.final_decision || rec.decision || 'UNKNOWN'}
                      </span>
                    </td>
                    <td className="text-right">
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); setSelected(rec); }}
                        className="ps-btn ps-btn-ghost text-xs"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected && (
        <div className="ps-card p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-headline-sm text-lg text-ink font-semibold">Raw record · {selected._id || 'record'}</h2>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="ps-btn-icon"
            >
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>
          <pre className="font-mono text-[10px] text-ink-light bg-surface rounded-md p-3 border border-border overflow-x-auto max-h-[60vh] overflow-y-auto">
            {JSON.stringify(selected, null, 2)}
          </pre>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => onNavigate('receipts')}
              className="ps-btn ps-btn-ghost text-xs"
            >
              <span className="material-symbols-outlined text-xs mr-1">receipt_long</span>
              Receipts
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
