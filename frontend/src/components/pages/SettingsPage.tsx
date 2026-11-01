/**
 * PayShield AI — Settings / Integrations
 * Simple, functional settings backed by real API state. No fabricated
 * integration statuses or configuration values.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { PageId } from '../../types';
import {
  getSettingsPreferences,
  updateSettingsPreferences,
  getIntegrationStatus,
  getHealth,
} from '../../services/api';

interface Integration {
  name: string;
  category: string;
  configured: boolean;
  status: string;
  note: string;
}

const CATEGORY_ICONS: Record<string, string> = {
  payment: 'account_balance_wallet',
  product: 'search',
  audit: 'fingerprint',
  ai: 'smart_toy',
  auth: 'person',
  default: 'hub',
};

export const SettingsPage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
  googleLinked?: string | null;
  authError?: string | null;
}> = ({ onNavigate, googleLinked = null, authError }) => {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [preferences, setPreferences] = useState<Record<string, unknown>>({});
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [linkedNotice, setLinkedNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (googleLinked) {
      setLinkedNotice('Your Google account has been linked successfully.');
    } else {
      setLinkedNotice(null);
    }
  }, [googleLinked]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const [prefs, integrations, healthResp] = await Promise.allSettled([
          getSettingsPreferences(),
          getIntegrationStatus(),
          getHealth(),
        ]);
        if (mounted) {
          if (prefs.status === 'fulfilled') setPreferences(prefs.value);
          if (integrations.status === 'fulfilled') {
            setIntegrations(integrations.value.integrations || []);
          }
          if (healthResp.status === 'fulfilled') setHealth(healthResp.value);
        }
      } catch {
        setError('Unable to load settings. Please try again later.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [onNavigate]);

  const togglePreference = useCallback(async (key: string) => {
    const next = !(preferences[key] === true);
    setSaving((prev) => new Set([...prev, key]));
    try {
      const result = await updateSettingsPreferences({
        ...preferences,
        [key]: next,
      });
      setPreferences(result);
    } catch {
      setError(`Failed to update ${key}. Please try again.`);
    } finally {
      setSaving((prev) => {
        const n = new Set(prev);
        n.delete(key);
        return n;
      });
    }
  }, [preferences]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-pulse">settings</span>
        <span className="font-body-sm text-sm text-ink-muted">Loading settings…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center text-center px-6">
        <span className="material-symbols-outlined text-block text-2xl mb-3">error</span>
        <h2 className="font-headline-md text-ink mb-1">Unable to load settings</h2>
        <p className="font-body-sm text-sm text-ink-muted mb-6">{error}</p>
        <button type="button" onClick={() => window.location.reload()} className="ps-btn ps-btn-primary">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-start gap-4">
        <div>
          <h1 className="font-headline-md text-ink">Settings</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Payment rails, integrations, and operational preferences.
          </p>
        </div>
      </div>

      {linkedNotice && (
        <div className="p-3 rounded-md bg-success-subtle border border-success/30 text-success text-sm font-medium">
          {linkedNotice}
        </div>
      )}

      {authError && (
        <div className="p-3 rounded-md bg-block/10 border border-block/30 text-block text-sm font-medium">
          {authError}
        </div>
      )}

      {/* Health */}
      <div className="ps-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-headline-sm text-lg text-ink font-semibold">System health</h2>
          <span
            className={`font-mono text-xs font-semibold ${
              health?.status === 'operational' || health?.status === 'ok'
                ? 'text-success'
                : 'text-block'
            }`}
          >
            {health?.status || 'Unknown'}
          </span>
        </div>
        <dl className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <p className="font-label-xs text-[10px] text-ink-light">Database</p>
            <p className="font-body-xs text-xs text-ink">
              {health?.components?.database?.status || '—'}
            </p>
          </div>
          <div>
            <p className="font-label-xs text-[10px] text-ink-light">Audit log</p>
            <p className="font-body-xs text-xs text-ink">
              {health?.components?.audit_log?.status || '—'}
            </p>
          </div>
          <div>
            <p className="font-label-xs text-[10px] text-ink-light">Providers configured</p>
            <p className="font-body-xs text-xs text-ink">
              {health?.providers ? Object.values(health.providers as any).filter((p: any) => p.configured).length : '—'}
            </p>
          </div>
        </dl>
      </div>

      {/* Integrations */}
      <div className="ps-card p-5">
        <h2 className="font-label-sm text-[10px] text-ink-muted uppercase tracking-wider mb-4">
          Integration status
        </h2>
        {integrations.length === 0 ? (
          <p className="font-body-xs text-xs text-ink-muted">
            No integration status reported by the backend.
          </p>
        ) : (
          <div className="space-y-2">
            {integrations.map((it) => (
              <div key={it.name} className="flex items-center justify-between p-3 rounded-md border border-border bg-surface">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-md flex items-center justify-center bg-surface text-ink-light">
                    <span className="material-symbols-outlined text-[13px]">
                      {CATEGORY_ICONS[it.category] || CATEGORY_ICONS.default}
                    </span>
                  </div>
                  <div>
                    <p className="font-body-sm text-sm text-ink">{it.name}</p>
                    <p className="font-label-xs text-[10px] text-ink-muted">{it.category}</p>
                  </div>
                </div>
                <div className="text-right">
                  <span className={`font-mono text-[10px] font-semibold ${
                    it.configured ? 'text-success' : 'text-ink-light'
                  }`}>
                    {it.configured ? 'Configured' : 'Not configured'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Preferences */}
      <div className="ps-card p-5">
        <h2 className="font-label-sm text-[10px] text-ink-muted uppercase tracking-wider mb-4">
          Operational preferences
        </h2>
        <div className="space-y-3">
          <div className="flex items-center justify-between p-3 rounded-md border border-border bg-surface">
            <div>
              <p className="font-body-sm text-sm text-ink">Enforce hardlock pre-flight halt</p>
              <p className="font-label-xs text-[10px] text-ink-muted">
                Blocks autonomous capital outflow without deterministic sign-off.
              </p>
            </div>
            <button
              type="button"
              onClick={() => togglePreference('enforceHardlock')}
              disabled={saving.has('enforceHardlock')}
              className={`inline-flex h-5 w-9 items-center rounded-full border transition-colors ${
                preferences.enforceHardlock === true
                  ? 'bg-accent border-accent'
                  : 'bg-surface border-border'
              }`}
            >
              <span className="block w-2.5 h-2.5 rounded-full bg-white transform transition-transform ${
                preferences.enforceHardlock === true ? 'translate-x-[4px]' : 'translate-x-[1px]'
              }"></span>
            </button>
          </div>
          <div className="flex items-center justify-between p-3 rounded-md border border-border bg-surface">
            <div>
              <p className="font-body-sm text-sm text-ink">Mandatory escrow on unverified vendors</p>
              <p className="font-label-xs text-[10px] text-ink-muted">
                Holds funds in escrow until merchant identity is verified.
              </p>
            </div>
            <button
              type="button"
              onClick={() => togglePreference('escrowMandatory')}
              disabled={saving.has('escrowMandatory')}
              className={`inline-flex h-5 w-9 items-center rounded-full border transition-colors ${
                preferences.escrowMandatory === true
                  ? 'bg-accent border-accent'
                  : 'bg-surface border-border'
              }`}
            >
              <span className="block w-2.5 h-2.5 rounded-full bg-white transform transition-transform ${
                preferences.escrowMandatory === true ? 'translate-x-[4px]' : 'translate-x-[1px]'
              }"></span>
            </button>
          </div>
          <div className="flex items-center justify-between p-3 rounded-md border border-border bg-surface">
            <div>
              <p className="font-body-sm text-sm text-ink">Real-time alerts (Slack / PagerDuty)</p>
              <p className="font-label-xs text-[10px] text-ink-muted">
                Sends risk and decision alerts to configured channels.
              </p>
            </div>
            <button
              type="button"
              onClick={() => togglePreference('slackAlerts')}
              disabled={saving.has('slackAlerts')}
              className={`inline-flex h-5 w-9 items-center rounded-full border transition-colors ${
                preferences.slackAlerts === true
                  ? 'bg-accent border-accent'
                  : 'bg-surface border-border'
              }`}
            >
              <span className="block w-2.5 h-2.5 rounded-full bg-white transform transition-transform ${
                preferences.slackAlerts === true ? 'translate-x-[4px]' : 'translate-x-[1px]'
              }"></span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
