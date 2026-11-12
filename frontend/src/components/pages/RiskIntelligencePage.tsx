/**
 * PayShield AI — Risk Intelligence
 * Real risk decisions and risk factors from the backend /risk/incidents endpoint.
 * No fabricated scores, gauges, or charts — only data returned by the decision engine.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PageId } from '../../types';
import { getRiskIncidents, RiskIncidentApi } from '../../services/api';
import { EmptyState } from '../common/EmptyState';
import { formatDateTime } from '../../utils/dateHelpers';

type Verdict = 'ALLOW' | 'REVIEW' | 'BLOCK';

function mapVerdict(v: string): Verdict {
  switch (v) {
    case 'ALLOW': return 'ALLOW';
    case 'QUARANTINE_REVIEW': return 'REVIEW';
    default: return 'BLOCK';
  }
}

export const RiskIntelligencePage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
}> = ({ onNavigate }) => {
  const [incidents, setIncidents] = useState<RiskIncidentApi[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [verdictFilter, setVerdictFilter] = useState('all');
  const [selected, setSelected] = useState<RiskIncidentApi | null>(null);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const data = await getRiskIncidents(200);
        if (mounted) setIncidents(data.incidents || []);
      } catch {
        setError('Unable to load risk incidents. Please try again later.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [onNavigate]);

  const filtered = useMemo(() => {
    return incidents.filter((inc) => {
      const match =
        !query ||
        inc.id.toLowerCase().includes(query.toLowerCase()) ||
        inc.agentId.toLowerCase().includes(query.toLowerCase()) ||
        inc.targetVendor.toLowerCase().includes(query.toLowerCase()) ||
        inc.vector.toLowerCase().includes(query.toLowerCase());
      const byVerdict =
        verdictFilter === 'all' || mapVerdict(inc.verdict).toLowerCase() === verdictFilter;
      return match && byVerdict;
    });
  }, [incidents, query, verdictFilter]);

  const openDrawer = useCallback((inc: RiskIncidentApi) => setSelected(inc), []);
  const closeDrawer = useCallback(() => setSelected(null), []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-pulse">security</span>
        <span className="font-body-sm text-sm text-ink-muted">Loading risk decisions…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-block text-2xl mb-3">error</span>
        <h2 className="font-headline-md text-ink mb-1">Unable to load risk intelligence</h2>
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
          <h1 className="font-headline-md text-ink">Risk Intelligence</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Real risk decisions, risk factors, and policy explanations from the
            PayShield decision engine.
          </p>
        </div>
      </div>

      <div className="ps-card p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
          <div className="md:col-span-3">
            <label className="ps-label">Search incidents</label>
            <input
              className="ps-input"
              placeholder="Incident, agent, vendor, or vector…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="md:col-span-1">
            <label className="ps-label">Decision</label>
            <select
              className="ps-input-sm"
              value={verdictFilter}
              onChange={(e) => setVerdictFilter(e.target.value)}
            >
              <option value="all">All decisions</option>
              <option value="allow">ALLOW</option>
              <option value="review">REVIEW</option>
              <option value="block">BLOCK</option>
            </select>
          </div>
        </div>
      </div>

      <div className="ps-card overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-8 text-center">
            <EmptyState
              icon="security"
              title="No risk decisions"
              description={
                query || verdictFilter !== 'all'
                  ? 'No risk decisions match your current filters.'
                  : 'The decision engine has not intercepted or flagged any transactions.'
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="ps-table">
              <thead>
                <tr>
                  <th className="w-32">Incident</th>
                  <th>Target vendor</th>
                  <th className="w-32">Agent</th>
                  <th className="text-right w-24">Risk score</th>
                  <th className="w-32">Decision</th>
                  <th className="w-20">Severity</th>
                  <th className="w-32">SLA remaining</th>
                  <th className="w-24">Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((inc) => {
                  const verdict = mapVerdict(inc.verdict);
                  return (
                    <tr key={inc.id} onClick={() => openDrawer(inc)} className="cursor-pointer">
                      <td className="font-mono text-[11px] text-ink-light">{inc.id}</td>
                      <td className="font-body-xs text-xs text-ink-muted truncate max-w-[140px]">
                        {inc.targetVendor}
                      </td>
                      <td className="font-mono text-[11px] text-ink-light">{inc.agentId}</td>
                      <td className="font-mono text-xs text-ink font-tabular text-right">
                        {inc.riskScore ?? '—'}
                      </td>
                      <td>
                        <span className={`ps-decision ${
                          verdict === 'ALLOW' ? 'ps-decision-allow' : verdict === 'REVIEW' ? 'ps-decision-review' : 'ps-decision-block'
                        }`}>
                          {verdict}
                        </span>
                      </td>
                      <td className="font-mono text-[11px]">
                        <span className={`ps-badge ${inc.severity === 'CRITICAL' || inc.severity === 'HIGH' ? 'ps-badge-block' : inc.severity === 'MEDIUM' ? 'ps-badge-review' : 'ps-badge-neutral'}`}>
                          {inc.severity}
                        </span>
                      </td>
                      <td className="font-mono text-[11px] text-ink-light">
                        {inc.slaRemaining || '—'}
                      </td>
                      <td className="text-right">
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); openDrawer(inc); }}
                          className="ps-btn ps-btn-ghost text-xs"
                        >
                          Inspect
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

      {/* Detail drawer */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="fixed inset-0 bg-black/30 backdrop-blur-sm" onClick={closeDrawer} />
          <div className="relative w-full max-w-2xl max-h-[90vh] bg-surface-white border border-border rounded-lg shadow-2xl flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <h2 className="font-headline-md text-ink">Incident detail · {selected.id}</h2>
              <button type="button" onClick={closeDrawer} className="ps-btn-icon">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <p className="font-label-xs text-[10px] text-ink-muted">Verdict</p>
                  <span className={`ps-decision ${
                    mapVerdict(selected.verdict) === 'ALLOW' ? 'ps-decision-allow' : mapVerdict(selected.verdict) === 'REVIEW' ? 'ps-decision-review' : 'ps-decision-block'
                  }`}>
                    {mapVerdict(selected.verdict)}
                  </span>
                </div>
                <div>
                  <p className="font-label-xs text-[10px] text-ink-muted">Risk score</p>
                  <p className="font-tabular text-sm font-semibold text-ink">{selected.riskScore ?? '—'}</p>
                </div>
                <div>
                  <p className="font-label-xs text-[10px] text-ink-muted">Severity</p>
                  <p className="font-mono text-xs text-ink">{selected.severity}</p>
                </div>
              </div>

              <div className="bg-surface rounded-lg p-4 border border-border">
                <p className="font-label-xs text-[10px] text-ink-muted uppercase tracking-wider mb-3">
                  Risk factors
                </p>
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div><dt className="font-label-xs text-[10px] text-ink-light">Vector</dt><dd className="font-body-xs text-xs text-ink">{selected.vector}</dd></div>
                  <div><dt className="font-label-xs text-[10px] text-ink-light">Policy</dt><dd className="font-body-xs text-xs text-ink">{selected.policyCode}</dd></div>
                  <div><dt className="font-label-xs text-[10px] text-ink-light">Proposed amount</dt><dd className="font-tabular text-xs font-semibold text-ink">{selected.proposedAmount != null ? selected.proposedAmount.toLocaleString() : '—'}</dd></div>
                  <div><dt className="font-label-xs text-[10px] text-ink-light">Mandate deviation</dt><dd className="font-tabular text-xs text-ink">{selected.mandateDeviationPct != null ? selected.mandateDeviationPct.toFixed(1) + '%' : '—'}</dd></div>
                  <div><dt className="font-label-xs text-[10px] text-ink-light">SLA remaining</dt><dd className="font-mono text-[11px] text-ink-light">{selected.slaRemaining || '—'}</dd></div>
                  <div><dt className="font-label-xs text-[10px] text-ink-light">Agent</dt><dd className="font-mono text-[11px] text-ink-light">{selected.agentId}</dd></div>
                  <div><dt className="font-label-xs text-[10px] text-ink-light">Cluster</dt><dd className="font-mono text-[11px] text-ink-light">{selected.cluster}</dd></div>
                  <div><dt className="font-label-xs text-[10px] text-ink-light">PayPal auth hash</dt><dd className="font-mono text-[10px] text-ink-light break-all">{selected.paypalAuthHash || '—'}</dd></div>
                </dl>
              </div>

              <div className="bg-surface rounded-lg p-4 border border-border">
                <p className="font-label-xs text-[10px] text-ink-muted uppercase tracking-wider mb-3">
                  Decision explanation
                </p>
                <div className="space-y-3">
                  <div>
                    <p className="font-label-xs text-[10px] text-ink-light">Deterministic reason (enforced)</p>
                    <p className="font-body-xs text-xs text-ink whitespace-pre-line">{selected.deterministicReason || '—'}</p>
                  </div>
                  {selected.llmRationale && (
                    <div>
                      <p className="font-label-xs text-[10px] text-ink-light">AI rationale (advisory only — deterministic policy governs)</p>
                      <p className="font-body-xs text-xs text-ink-muted whitespace-pre-line">{selected.llmRationale}</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="bg-surface rounded-lg p-4 border border-border">
                <p className="font-label-xs text-[10px] text-ink-muted uppercase tracking-wider mb-3">
                  Raw payload
                </p>
                <pre className="font-mono text-[10px] text-ink-light overflow-x-auto bg-base rounded-md p-3 border border-border">
                  {JSON.stringify(selected.rawPayload || {}, null, 2)}
                </pre>
              </div>
            </div>
            <div className="px-5 py-4 border-t border-border flex justify-end gap-2">
              <button type="button" onClick={() => onNavigate('audit-investigation')} className="ps-btn ps-btn-ghost text-xs">
                Query audit events
              </button>
              <button type="button" onClick={closeDrawer} className="ps-btn ps-btn-primary text-xs">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
