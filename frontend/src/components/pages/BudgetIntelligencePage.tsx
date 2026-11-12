/**
 * PayShield AI — Budget Intelligence
 * Real agent budgets from /budget/state. Metrics are derived from live data
 * and render honestly (—) when no budget rows exist.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PageId } from '../../types';
import { AgentBudget, getBudgetState } from '../../services/api';
import { EmptyState } from '../common/EmptyState';
import { formatAmount } from '../../utils/dateHelpers';

export const BudgetIntelligencePage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
}> = ({ onNavigate }) => {
  const [budgets, setBudgets] = useState<AgentBudget[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const data = await getBudgetState();
        if (mounted) setBudgets(data.agents || []);
      } catch {
        setError('Unable to load budget state. Please try again later.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [onNavigate]);

  const totalLimitCents = useMemo(() => budgets.reduce((s, b) => s + (b.spending_limit_cents || 0), 0), [budgets]);
  const totalSpentCents = useMemo(() => budgets.reduce((s, b) => s + (b.spent_cents || 0), 0), [budgets]);
  const totalReservedCents = useMemo(() => budgets.reduce((s, b) => s + (b.reserved_cents || 0), 0), [budgets]);
  const totalAvailableCents = useMemo(() => budgets.reduce((s, b) => s + (b.available_cents || 0), 0), [budgets]);
  const poolUtilization = useMemo(() => totalLimitCents > 0 ? Math.round(((totalSpentCents / totalLimitCents) * 100) * 10) / 10 : 0, [totalSpentCents, totalLimitCents]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-pulse">account_balance_wallet</span>
        <span className="font-body-sm text-sm text-ink-muted">Loading budgets…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-block text-2xl mb-3">error</span>
        <h2 className="font-headline-md text-ink mb-1">Unable to load budgets</h2>
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
          <h1 className="font-headline-md text-ink">Budget Intelligence</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Autonomous agent spend limits, usage, and availability from the
            budget service.
          </p>
        </div>
      </div>

      <div className="ps-card p-5">
        <h2 className="font-label-sm text-[10px] text-ink-muted uppercase tracking-wider mb-4">
          Fleet spend pool
        </h2>
        <dl className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <div>
            <p className="font-label-xs text-[10px] text-ink-light">Total limit</p>
            <p className="font-tabular text-sm font-semibold text-ink">{totalLimitCents > 0 ? formatAmount(totalLimitCents / 100, 'USD') : '—'}</p>
          </div>
          <div>
            <p className="font-label-xs text-[10px] text-ink-light">Spent</p>
            <p className="font-tabular text-sm font-semibold text-ink">{totalSpentCents > 0 ? formatAmount(totalSpentCents / 100, 'USD') : '—'}</p>
          </div>
          <div>
            <p className="font-label-xs text-[10px] text-ink-light">Reserved</p>
            <p className="font-tabular text-sm font-semibold text-ink">{totalReservedCents > 0 ? formatAmount(totalReservedCents / 100, 'USD') : '—'}</p>
          </div>
          <div>
            <p className="font-label-xs text-[10px] text-ink-light">Pool utilization</p>
            <p className="font-tabular text-sm font-semibold text-ink">{totalLimitCents > 0 ? poolUtilization + '%' : '—'}</p>
          </div>
        </dl>
        {totalLimitCents > 0 && (
          <div className="mt-4 h-1.5 bg-surface rounded-full overflow-hidden">
            <div className="h-full bg-accent" style={{ width: Math.min(100, poolUtilization) + '%' }}></div>
          </div>
        )}
      </div>

      <div className="ps-card overflow-hidden">
        {budgets.length === 0 ? (
          <div className="p-8 text-center">
            <EmptyState
              icon="account_balance_wallet"
              title="No agent budgets"
              description="No agent spend limits have been configured. Budget envelopes appear here once agents are registered."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="ps-table">
              <thead>
                <tr>
                  <th className="w-40">Agent</th>
                  <th>Tier</th>
                  <th className="text-right w-32">Limit</th>
                  <th className="text-right w-32">Spent</th>
                  <th className="text-right w-32">Available</th>
                  <th className="w-32">Utilization</th>
                  <th className="w-20">Status</th>
                </tr>
              </thead>
              <tbody>
                {budgets.map((b) => {
                  const limit = b.spending_limit_cents || 0;
                  const spent = b.spent_cents || 0;
                  const util = limit > 0 ? Math.round(((spent / limit) * 100) * 10) / 10 : 0;
                  return (
                    <tr key={b.agent_id}>
                      <td className="font-mono text-[11px] text-ink">{b.agent_id}</td>
                      <td className="font-mono text-[11px] text-ink-muted">{b.pending_reservation_count > 0 ? 'Reservations pending' : 'Active'}</td>
                      <td className="font-mono text-xs text-ink font-tabular text-right">{limit > 0 ? formatAmount(limit / 100, 'USD') : '—'}</td>
                      <td className="font-mono text-xs text-ink font-tabular text-right">{spent > 0 ? formatAmount(spent / 100, 'USD') : '—'}</td>
                      <td className="font-mono text-xs text-ink font-tabular text-right">{b.available_cents != null ? formatAmount(b.available_cents / 100, 'USD') : '—'}</td>
                      <td>
                        <div className="h-1.5 bg-surface rounded-full overflow-hidden w-24">
                          <div className="h-full bg-accent" style={{ width: Math.min(100, util) + '%' }}></div>
                        </div>
                        <p className="font-label-xs text-[10px] text-ink-light">{util}%</p>
                      </td>
                      <td className="font-mono text-[11px]">
                        <span className={`ps-badge ${b.pending_reservation_count > 0 ? 'ps-badge-review' : 'ps-badge-allow'}`}>
                          {b.pending_reservation_count > 0 ? 'REVIEW' : 'ACTIVE'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
