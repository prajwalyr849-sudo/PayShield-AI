/**
 * PayShield AI — Policies
 * Policy management using real backend policy rules from /policies.
 * Policy toggles are persisted server-side; nothing is simulated.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PageId } from '../../types';
import { listPolicies, togglePolicy, PolicyRuleApi } from '../../services/api';
import { EmptyState } from '../common/EmptyState';

export const PoliciesPage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
  googleLinked?: string | null;
  authError?: string | null;
}> = ({ onNavigate }) => {
  const [policies, setPolicies] = useState<PolicyRuleApi[]>([]);
  const [constitution, setConstitution] = useState<{
    max_auto_payment: number;
    approval_limit: number;
    blocked_categories: string[];
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<PolicyRuleApi | null>(null);
  const [toggling, setToggling] = useState<Set<string>>(new Set());

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const data = await listPolicies();
        if (mounted) {
          setPolicies(data.policies || []);
          setConstitution(data.constitution ?? null);
          if (!selected && data.policies?.[0]) setSelected(data.policies[0]);
        }
      } catch {
        setError('Unable to load policies. Please try again later.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [onNavigate, selected]);

  const filtered = useMemo(() => {
    return policies.filter((p) => {
      const match =
        !query ||
        p.id.toLowerCase().includes(query.toLowerCase()) ||
        p.name.toLowerCase().includes(query.toLowerCase()) ||
        p.dsl.toLowerCase().includes(query.toLowerCase());
      const byCategory =
        categoryFilter === 'all' || p.category === categoryFilter;
      return match && byCategory;
    });
  }, [policies, categoryFilter, query]);

  const togglePolicyRule = useCallback(async (id: string) => {
    setToggling((prev) => new Set([...prev, id]));
    try {
      const result = await togglePolicy(id);
      setPolicies((prev) =>
        prev.map((p) => (p.id === id ? { ...p, enabled: result.enabled } : p))
      );
      setSelected((prev) =>
        prev?.id === id ? { ...prev, enabled: result.enabled } : prev
      );
    } catch {
      setError('Failed to toggle policy. Please try again.');
    } finally {
      setToggling((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }, []);

  const categories = useMemo(() => {
    const set = new Set<string>();
    policies.forEach((p) => set.add(p.category));
    return Array.from(set).sort();
  }, [policies]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-pulse">tune</span>
        <span className="font-body-sm text-sm text-ink-muted">Loading policies…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-block text-2xl mb-3">error</span>
        <h2 className="font-headline-md text-ink mb-1">Unable to load policies</h2>
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
          <h1 className="font-headline-md text-ink">Policies</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Deterministic policy rules enforced by PayShield. Toggle rules to
            enable or disable them server-side.
          </p>
        </div>
      </div>

      {/* Constitution summary */}
      {constitution && (
        <div className="ps-card p-5">
          <h2 className="font-label-sm text-[10px] text-ink-muted uppercase tracking-wider mb-4">
            Policy constitution
          </h2>
          <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <dt className="font-label-xs text-[10px] text-ink-light">Max auto payment</dt>
              <dd className="font-tabular text-sm font-semibold text-ink">{constitution.max_auto_payment.toLocaleString()}</dd>
            </div>
            <div>
              <dt className="font-label-xs text-[10px] text-ink-light">Approval limit</dt>
              <dd className="font-tabular text-sm font-semibold text-ink">{constitution.approval_limit.toLocaleString()}</dd>
            </div>
            <div>
              <dt className="font-label-xs text-[10px] text-ink-light">Blocked categories</dt>
              <dd className="font-mono text-[11px] text-ink-light">
                {constitution.blocked_categories.join(', ') || 'None'}
              </dd>
            </div>
          </dl>
        </div>
      )}

      <div className="ps-card p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
          <div className="md:col-span-2">
            <label className="ps-label">Search policies</label>
            <input
              className="ps-input"
              placeholder="ID, name, or DSL…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="md:col-span-1">
            <label className="ps-label">Category</label>
            <select
              className="ps-input-sm"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
            >
              <option value="all">All categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c.charAt(0).toUpperCase() + c.slice(1)}
                </option>
              ))}
            </select>
          </div>
          <div className="md:col-span-1">
            <div className="h-8"></div>
          </div>
        </div>
      </div>

      <div className="ps-card overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-8 text-center">
            <EmptyState
              icon="tune"
              title="No policies"
              description={
                query || categoryFilter !== 'all'
                  ? 'No policies match your current filters.'
                  : 'The backend has no policy rules configured.'
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="ps-table">
              <thead>
                <tr>
                  <th className="w-32">ID</th>
                  <th>Name</th>
                  <th className="w-32">Category</th>
                  <th className="w-20">Action</th>
                  <th className="w-16">Enabled</th>
                  <th className="w-20">Latency</th>
                  <th className="w-24">Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => (
                  <tr key={p.id} onClick={() => setSelected(p)} className="cursor-pointer">
                    <td className="font-mono text-[11px] text-ink-light">{p.id}</td>
                    <td className="font-body-xs text-xs text-ink">{p.name}</td>
                    <td className="font-mono text-[11px] text-ink-muted">{p.category}</td>
                    <td className="font-mono text-[11px] text-ink-light">{p.action}</td>
                    <td>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); togglePolicyRule(p.id); }}
                        disabled={toggling.has(p.id)}
                        className={`inline-flex h-5 w-9 items-center rounded-full border transition-colors ${
                          p.enabled
                            ? 'bg-accent border-accent'
                            : 'bg-surface border-border'
                        }`}
                      >
                        <span className="block w-2.5 h-2.5 rounded-full bg-white transform transition-transform ${
                          p.enabled ? 'translate-x-[4px]' : 'translate-x-[1px]'
                        }"></span>
                      </button>
                    </td>
                    <td className="font-mono text-[11px] text-ink-light">{p.latency}</td>
                    <td className="text-right">
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); setSelected(p); }}
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

      {/* Rule inspector */}
      {selected && (
        <div className="ps-card p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-headline-sm text-lg text-ink font-semibold">
                Rule inspector · {selected.id}
              </h2>
              <p className="font-body-xs text-xs text-ink-muted">
                {selected.description || 'No description'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="ps-btn-icon"
            >
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <p className="font-label-xs text-[10px] text-ink-muted">DSL</p>
              <pre className="font-mono text-[10px] text-ink-light bg-surface rounded-md p-3 border border-border overflow-x-auto">
                {selected.dsl || '—'}
              </pre>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <p className="font-label-xs text-[10px] text-ink-light">Category</p>
                <p className="font-body-xs text-xs text-ink">{selected.category}</p>
              </div>
              <div>
                <p className="font-label-xs text-[10px] text-ink-light">Action</p>
                <p className="font-body-xs text-xs text-ink">{selected.action}</p>
              </div>
              <div>
                <p className="font-label-xs text-[10px] text-ink-light">Latency</p>
                <p className="font-body-xs text-xs text-ink">{selected.latency}</p>
              </div>
            </div>
            <div className="pt-4 border-t border-border flex items-center gap-2">
              <span
                className={`font-mono text-xs font-semibold ${
                  selected.enabled ? 'text-success' : 'text-block'
                }`}
              >
                {selected.enabled ? 'Enabled' : 'Disabled'}
              </span>
              <button
                type="button"
                onClick={() => togglePolicyRule(selected.id)}
                disabled={toggling.has(selected.id)}
                className="ps-btn ps-btn-ghost text-xs"
              >
                {toggling.has(selected.id) ? 'Toggling…' : 'Toggle rule'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
