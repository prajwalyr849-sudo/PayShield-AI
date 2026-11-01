/**
 * PayShield AI — Lifecycle
 * Real agent commerce lifecycle sessions from /lifecycle/sessions.
 * Only persisted session state is displayed; no simulated metrics.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PageId, LifecycleSessionApi } from '../../types';
import { listLifecycleSessions } from '../../services/api';
import { EmptyState } from '../common/EmptyState';
import { formatDateTime } from '../../utils/dateHelpers';

export const LifecyclePage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
}> = ({ onNavigate }) => {
  const [sessions, setSessions] = useState<LifecycleSessionApi[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stateFilter, setStateFilter] = useState('all');
  const [selected, setSelected] = useState<LifecycleSessionApi | null>(null);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const data = await listLifecycleSessions(undefined, 200);
        if (mounted) setSessions(data.sessions || []);
      } catch {
        setError('Unable to load lifecycle sessions. Please try again later.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [onNavigate]);

  const filtered = useMemo(() => {
    return sessions.filter((s) => {
      if (stateFilter === 'all') return true;
      return s.currentState?.toLowerCase() === stateFilter.toLowerCase();
    });
  }, [sessions, stateFilter]);

  const states = useMemo(() => {
    const set = new Set<string>();
    sessions.forEach((s) => set.add(s.currentState));
    return Array.from(set).sort();
  }, [sessions]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-pulse">account_tree</span>
        <span className="font-body-sm text-sm text-ink-muted">Loading sessions…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-block text-2xl mb-3">error</span>
        <h2 className="font-headline-md text-ink mb-1">Unable to load sessions</h2>
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
          <h1 className="font-headline-md text-ink">Lifecycle</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Real agent commerce lifecycle sessions and their current state.
          </p>
        </div>
      </div>

      <div className="ps-card p-4">
        <div className="flex items-center gap-2">
          <span className="font-label-xs text-[10px] text-ink-muted">Session state</span>
          {[
            'all',
            ...states,
          ].map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => setStateFilter(st)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                stateFilter === st
                  ? 'bg-accent-subtle text-accent border-accent/30'
                  : 'border-border text-ink-muted hover:text-ink hover:bg-surface'
              }`}
            >
              {st.charAt(0).toUpperCase() + st.slice(1)} ({filtered.length})
            </button>
          ))}
        </div>
      </div>

      <div className="ps-card overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-8 text-center">
            <EmptyState
              icon="account_tree"
              title="No lifecycle sessions"
              description="No agent commerce sessions have been recorded yet."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="ps-table">
              <thead>
                <tr>
                  <th className="w-40">Session</th>
                  <th className="w-32">Agent</th>
                  <th>Target vendor</th>
                  <th className="text-right w-32">Requested amount</th>
                  <th className="w-32">Current state</th>
                  <th className="w-48">Created</th>
                  <th className="w-24">Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <tr key={s.sessionId} onClick={() => setSelected(s)} className="cursor-pointer">
                    <td className="font-mono text-[11px] text-ink-light">{s.sessionId}</td>
                    <td className="font-mono text-[11px] text-ink-light">{s.agentId}</td>
                    <td className="font-body-xs text-xs text-ink-muted truncate max-w-[150px]">{s.targetVendor}</td>
                    <td className="font-mono text-xs text-ink font-tabular text-right">{s.requestedAmount != null ? s.requestedAmount.toLocaleString() : '—'}</td>
                    <td className="font-mono text-[11px] text-ink-muted">{s.currentState}</td>
                    <td className="font-mono text-[11px] text-ink-light">{formatDateTime(s.createdAt)}</td>
                    <td className="text-right">
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); setSelected(s); }}
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
            <h2 className="font-headline-sm text-lg text-ink font-semibold">Session · {selected.sessionId}</h2>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="ps-btn-icon"
            >
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div><p className="font-label-xs text-[10px] text-ink-light">Agent</p><p className="font-body-xs text-xs text-ink">{selected.agentId}</p></div>
            <div><p className="font-label-xs text-[10px] text-ink-light">Target vendor</p><p className="font-body-xs text-xs text-ink">{selected.targetVendor}</p></div>
            <div><p className="font-label-xs text-[10px] text-ink-light">Requested amount</p><p className="font-tabular text-xs font-semibold text-ink">{selected.requestedAmount != null ? selected.requestedAmount.toLocaleString() : '—'}</p></div>
            <div><p className="font-label-xs text-[10px] text-ink-light">Current state</p><p className="font-body-xs text-xs text-ink">{selected.currentState}</p></div>
            <div><p className="font-label-xs text-[10px] text-ink-light">Policy</p><p className="font-mono text-[11px] text-ink-light">{selected.policyId || '—'}</p></div>
            <div><p className="font-label-xs text-[10px] text-ink-light">Created</p><p className="font-mono text-[11px] text-ink-light">{formatDateTime(selected.createdAt)}</p></div>
            <div><p className="font-label-xs text-[10px] text-ink-light">Updated</p><p className="font-mono text-[11px] text-ink-light">{formatDateTime(selected.updatedAt)}</p></div>
            {selected.receiptId && (<div><p className="font-label-xs text-[10px] text-ink-light">Receipt</p><p className="font-mono text-[11px] text-ink-light">{selected.receiptId}</p></div>)}
          </dl>
          {selected.stateHistory && selected.stateHistory.length > 0 && (
            <div className="mt-4">
              <p className="font-label-xs text-[10px] text-ink-muted uppercase tracking-wider mb-2">State history</p>
              <div className="space-y-2">
                {selected.stateHistory.map((h, i) => (
                  <div key={i} className="flex gap-3">
                    <div className="shrink-0 w-2 h-2 rounded-full bg-success mt-1"></div>
                    <div className="flex-1">
                      <p className="font-body-xs text-xs text-ink">{String(h.state || h)}</p>
                      <p className="font-label-xs text-[10px] text-ink-light">{String(h.timestamp || h.at || h.time || '')}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
