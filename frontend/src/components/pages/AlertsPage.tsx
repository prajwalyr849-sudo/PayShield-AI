/**
 * PayShield AI — Alerts
 * Real security alerts from /alerts. Acknowledge or resolve alerts;
 * state changes are persisted server-side.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { PageId } from '../../types';
import { listAlerts, acknowledgeAlert, resolveAlert } from '../../services/api';
import { EmptyState } from '../common/EmptyState';

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: 'all', label: 'All alerts' },
  { value: 'active', label: 'Active' },
  { value: 'acknowledged', label: 'Acknowledged' },
  { value: 'resolved', label: 'Resolved' },
];

export const AlertsPage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
}> = ({ onNavigate }) => {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [notice, setNotice] = useState<{ id: string; message: string } | null>(null);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const data = await listAlerts(undefined, undefined, 100);
        if (mounted) setAlerts(data.alerts || []);
      } catch {
        setError('Unable to load alerts. Please try again later.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [onNavigate]);

  const filtered = alerts.filter((a) => {
    if (statusFilter === 'all') return true;
    return a.status === statusFilter;
  });

  const handleAction = useCallback(async (id: string, fn: () => Promise<any>, label: string) => {
    try {
      await fn();
      setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, status: label === 'acknowledged' ? 'acknowledged' : 'resolved' } : a)));
      setNotice({ id, message: `Alert ${id} ${label}.` });
      setTimeout(() => setNotice(null), 3000);
    } catch {
      setError(`Failed to ${label} alert ${id}.`);
    }
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-pulse">error</span>
        <span className="font-body-sm text-sm text-ink-muted">Loading alerts…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-block text-2xl mb-3">error</span>
        <h2 className="font-headline-md text-ink mb-1">Unable to load alerts</h2>
        <p className="font-body-sm text-sm text-ink-muted mb-6">{error}</p>
        <button type="button" onClick={() => window.location.reload()} className="ps-btn ps-btn-primary">
          Retry
        </button>
      </div>
    );
  }

  const activeCount = alerts.filter((a) => a.status === 'active').length;

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <div>
          <h1 className="font-headline-md text-ink">Alerts</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Real security alerts. Acknowledge or resolve an alert to update its
            status server-side.
          </p>
        </div>
      </div>

      {notice && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-lg border border-success/30 bg-success-subtle text-success text-sm font-medium shadow-xl">
          <span className="material-symbols-outlined text-lg">check_circle</span>
          <span>{notice.message}</span>
        </div>
      )}

      <div className="ps-card p-4">
        <div className="flex items-center gap-2">
          <span className="font-label-xs text-[10px] text-ink-muted">Status</span>
          {STATUS_FILTERS.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => setStatusFilter(item.value)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                statusFilter === item.value
                  ? 'bg-accent-subtle text-accent border-accent/30'
                  : 'border-border text-ink-muted hover:text-ink hover:bg-surface'
              }`}
            >
              {item.label} ({alerts.filter((a) => item.value === 'all' || a.status === item.value).length})
            </button>
          ))}
        </div>
      </div>

      <div className="ps-card overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-8 text-center">
            <EmptyState
              icon="error"
              title="No alerts"
              description={statusFilter !== 'all' ? `No ${statusFilter} alerts.` : 'No alerts have been raised.'}
              actionLabel="View policies"
              onAction={() => onNavigate('policies')}
            />
          </div>
        ) : (
          <div className="divide-y divide-border/50">
            {filtered.map((a) => (
              <div key={a.id} className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span
                      className={`ps-badge ${
                        a.severity === 'critical' || a.severity === 'high'
                          ? 'ps-badge-block'
                          : a.severity === 'medium'
                            ? 'ps-badge-review'
                            : 'ps-badge-neutral'
                      }`}>
                      {a.severity}
                    </span>
                    <span className="font-mono text-[11px] text-ink-light">{a.status}</span>
                  </div>
                  <span className="font-mono text-[10px] text-ink-light">
                    {new Date(a.timestamp).toLocaleString()}
                  </span>
                </div>
                <h3 className="font-body-sm text-sm text-ink font-semibold mt-1 mb-1">{a.title}</h3>
                <p className="font-body-xs text-xs text-ink-muted">{a.description}</p>
                <div className="mt-3 flex items-center gap-2">
                  <span className="font-label-xs text-[10px] text-ink-muted">
                    {a.source || 'system'}
                  </span>
                  {a.policyId && (
                    <span className="font-mono text-[10px] text-ink-muted">
                      Policy: {a.policyId}
                    </span>
                  )}
                  {a.agentId && (
                    <span className="font-mono text-[10px] text-ink-muted">
                      Agent: {a.agentId}
                    </span>
                  )}
                </div>
                {a.status === 'active' && (
                  <div className="mt-3 flex gap-2">
                    <button
                      type="button"
                      onClick={() => handleAction(a.id, () => acknowledgeAlert(a.id), 'acknowledged')}
                      className="ps-btn ps-btn-ghost text-xs"
                    >
                      Acknowledge
                    </button>
                    <button
                      type="button"
                      onClick={() => handleAction(a.id, () => resolveAlert(a.id), 'resolved')}
                      className="ps-btn ps-btn-ghost text-xs"
                    >
                      Resolve
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
