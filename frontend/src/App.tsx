/**
 * PayShield AI — Transaction Security
 * Main Application Shell & Master Router
 *
 * Enforces:
 * - Strict Decoupling Protocol: PayShield Deterministic Decisions vs. PayPal Provider Settlement Status
 * - Clean, minimal, premium fintech UI
 * - Responsive navigation
 * - Global ⌘K Command Palette & Hotkey support
 */

import React, { useState, useEffect } from 'react';
import { PageId, PendingIntentPayload, UserPublicProfile } from './types';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { CommandModal } from './components/common/CommandModal';
import { getAuthMe, getAuthProviderStatus, logoutUser, listAlerts } from './services/api';

// Application Pages
import { OverviewPage } from './components/pages/OverviewPage';
import { AssistantChatPage } from './components/pages/AssistantChatPage';
import { ProductSearchPage } from './components/pages/ProductSearchPage';
import { TransactionsPage } from './components/pages/TransactionsPage';
import { LifecyclePage } from './components/pages/LifecyclePage';
import { ReceiptsPage } from './components/pages/ReceiptsPage';
import { ReceiptPage } from './components/pages/ReceiptPage';
import { CheckoutPage } from './components/pages/CheckoutPage';
import { RiskIntelligencePage } from './components/pages/RiskIntelligencePage';
import { BudgetIntelligencePage } from './components/pages/BudgetIntelligencePage';
import { ActivityPage } from './components/pages/ActivityPage';
import { AuditInvestigationPage } from './components/pages/AuditInvestigationPage';
import { AlertsPage } from './components/pages/AlertsPage';
import { PoliciesPage } from './components/pages/PoliciesPage';
import { AuditLogsPage } from './components/pages/AuditLogsPage';
import { SettingsPage } from './components/pages/SettingsPage';
import { SignInPage } from './components/pages/SignInPage';
import { SignUpPage } from './components/pages/SignUpPage';
import { ForgotPasswordPage } from './components/pages/ForgotPasswordPage';
import { ResetPasswordPage } from './components/pages/ResetPasswordPage';

export default function App() {
  const [currentPage, setCurrentPage] = useState<PageId>('overview');
  // Default operational cluster. The cluster switcher was removed from the
  // minimal shell; pages that gate on cluster state run on cluster-01-live.
  const [currentCluster, setCurrentCluster] = useState<'cluster-01-live'>('cluster-01-live');
  const [commandModalOpen, setCommandModalOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [pendingIntent, setPendingIntent] = useState<PendingIntentPayload | null>(null);
  const [alertCount, setAlertCount] = useState(0);
  const [user, setUser] = useState<UserPublicProfile | null>(null);
  const [signUp, setSignUp] = useState(false);
  const [forgotPassword, setForgotPassword] = useState(false);
  const [resetPassword, setResetPassword] = useState(false);
  const [authInitializing, setAuthInitializing] = useState(true);
  const [googleConfigured, setGoogleConfigured] = useState(false);
  const [googleLinked, setGoogleLinked] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  // Resolve the authenticated session from the existing secure session cookie
  // (payshield_session, HttpOnly). Never auto-sign in a demo user: the browser
  // must authenticate through the real /auth/login, /auth/register, or the
  // backend-managed Google OAuth callback.
  useEffect(() => {
    let mounted = true;
    const initAuth = async () => {
      if (mounted && typeof window !== 'undefined') {
        const path = window.location.pathname;
        const pageFromPath = path.replace(/^\//, '') || 'overview';
        const validPages: PageId[] = [
          'overview', 'assistant-chat', 'product-search', 'transactions',
          'lifecycle', 'receipts', 'receipt-detail', 'risk-intelligence', 'budget-intelligence',
          'activity', 'audit-investigation', 'alerts', 'policies', 'audit-logs',
          'settings', 'integrations', 'forgot-password', 'reset-password',
        ];
        // PayPal Sandbox redirects the buyer back to /checkout/return?token=...
        // after approval. The SPA must render the CheckoutPage so it can read
        // the PayPal token, verify the capture server-side, and show the receipt.
        if (pageFromPath === 'checkout' || pageFromPath.startsWith('checkout/')) {
          setCurrentPage('checkout');
        } else if (validPages.includes(pageFromPath as PageId)) {
          setCurrentPage(pageFromPath as PageId);
        }

        // Parse auth-related query params set by the backend OAuth callback.
        const params = new URLSearchParams(window.location.search);
        const linked = params.get('linked');
        if (linked === 'google') {
          setGoogleLinked('google');
        } else if (linked) {
          setGoogleLinked(linked);
        }
        const error = params.get('error');
        if (error) {
          setAuthError(decodeURIComponent(error));
        }
        const loginSuccess = params.get('login_success');
        if (loginSuccess) {
          try {
            const url = new URL(window.location.href);
            url.searchParams.delete('login_success');
            window.history.replaceState({}, '', url.toString());
          } catch {
            // Ignore URL cleanup failures.
          }
        }
      }

      try {
        const profile = await getAuthMe();
        if (mounted) setUser(profile);
      } catch {
        if (mounted) setUser(null);
      }
      try {
        const status = await getAuthProviderStatus();
        if (mounted) setGoogleConfigured(!!status?.google?.configured);
      } catch {
        if (mounted) setGoogleConfigured(false);
      } finally {
        if (mounted) setAuthInitializing(false);
      }
    };
    initAuth();
    return () => { mounted = false; };
  }, []);

  const handleSignOut = async () => {
    try {
      await logoutUser();
    } catch {
      // Sign out is best-effort on the client; clear local state regardless.
    }
    setUser(null);
    setCurrentPage('overview');
  };

  const handleSignIn = (profile: UserPublicProfile) => {
    setUser(profile);
    setGoogleLinked(null);
    setCurrentPage('overview');
  };

  // Keyboard shortcut listener for ⌘K / Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCommandModalOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Live active-alert count for the nav badge. On failure the count stays 0
  // (badge hidden) — an unreachable backend must not show a fabricated count.
  useEffect(() => {
    let mounted = true;
    const loadAlerts = async () => {
      try {
        const data = await listAlerts(undefined, undefined, 100);
        if (mounted) {
          setAlertCount(
            (data.alerts || []).filter((a) => a.status === 'active').length
          );
        }
      } catch {
        if (mounted) setAlertCount(0);
      }
    };
    loadAlerts();
    return () => { mounted = false; };
  }, []);

  const handleNavigate = (page: PageId, pendingIntent?: PendingIntentPayload) => {
    setCurrentPage(page);
    setPendingIntent(pendingIntent ?? null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const renderCurrentPage = () => {
    switch (currentPage) {
      case 'overview':
        return <OverviewPage currentCluster={currentCluster} onNavigate={handleNavigate} />;
      case 'assistant-chat':
        return <AssistantChatPage currentCluster={currentCluster} onNavigate={handleNavigate} pendingIntent={pendingIntent} />;
      case 'product-search':
        return <ProductSearchPage currentCluster={currentCluster} onNavigate={handleNavigate} />;
      case 'transactions':
        return <TransactionsPage currentCluster={currentCluster} onNavigate={handleNavigate} />;
      case 'lifecycle':
        return <LifecyclePage currentCluster={currentCluster} onNavigate={handleNavigate} />;
      case 'receipts':
        return <ReceiptsPage currentCluster={currentCluster} onNavigate={handleNavigate} />;
      case 'receipt-detail':
        return <ReceiptPage currentCluster={currentCluster} onNavigate={handleNavigate} pendingIntent={pendingIntent} />;
      case 'checkout':
        return <CheckoutPage currentCluster={currentCluster} onNavigate={handleNavigate} />;
      case 'risk-intelligence':
        return <RiskIntelligencePage currentCluster={currentCluster} onNavigate={handleNavigate} />;
      case 'budget-intelligence':
        return <BudgetIntelligencePage currentCluster={currentCluster} onNavigate={handleNavigate} />;
      case 'activity':
        return <ActivityPage currentCluster={currentCluster} onNavigate={handleNavigate} />;
      case 'audit-investigation':
        return <AuditInvestigationPage currentCluster={currentCluster} onNavigate={handleNavigate} />;
      case 'alerts':
        return <AlertsPage currentCluster={currentCluster} onNavigate={handleNavigate} />;
      case 'policies':
        return <PoliciesPage currentCluster={currentCluster} onNavigate={handleNavigate} googleLinked={googleLinked} authError={authError} />;
      case 'audit-logs':
        return <AuditLogsPage currentCluster={currentCluster} onNavigate={handleNavigate} />;
      case 'settings':
      case 'integrations':
        return (
          <SettingsPage
            currentCluster={currentCluster}
            onNavigate={handleNavigate}
            googleLinked={googleLinked}
            authError={authError}
          />
        );
      case 'forgot-password':
        return <ForgotPasswordPage onGoToSignIn={() => setForgotPassword(false)} />;
      case 'reset-password':
        return <ResetPasswordPage onGoToSignIn={() => setResetPassword(false)} />;
      default:
        return <OverviewPage currentCluster={currentCluster} onNavigate={handleNavigate} />;
    }
  };

  return (
    <div className="app-shell font-body-md antialiased">
      {/* Navigation Sidebar */}
      <Sidebar
        currentPage={currentPage}
        onNavigate={handleNavigate}
        alertCount={alertCount}
        isOpenMobile={mobileMenuOpen}
        onCloseMobile={() => setMobileMenuOpen(false)}
      />

      {/* Main Content Area offset by desktop sidebar */}
      <div className="app-main">
        <Header
          currentPage={currentPage}
          onOpenCommand={() => setCommandModalOpen(true)}
          onOpenMobileMenu={() => setMobileMenuOpen(true)}
          alertCount={alertCount}
          user={user}
          onSignOut={handleSignOut}
        />

        {/* Dynamic Page Component */}
        <main className="app-page">
          {authInitializing ? (
            <div className="flex flex-col items-center justify-center h-96 gap-3">
              <span className="material-symbols-outlined text-accent text-xl animate-pulse">login</span>
              <span className="font-body-sm text-sm text-ink-muted">Resolving session…</span>
            </div>
          ) : user === null ? (
            <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
              {signUp ? (
                <SignUpPage
                  onAuthenticated={handleSignIn}
                  onGoToSignIn={() => setSignUp(false)}
                />
              ) : (
                <SignInPage
                  onAuthenticated={handleSignIn}
                  onGoToSignUp={() => setSignUp(true)}
                  onGoToForgotPassword={() => {
                    setForgotPassword(true);
                    setCurrentPage('forgot-password');
                  }}
                  googleConfigured={googleConfigured}
                  googleError={authError}
                />
              )}
            </div>
          ) : (
            renderCurrentPage()
          )}
        </main>
      </div>

      {/* Global ⌘K Command Palette Modal */}
      <CommandModal
        isOpen={commandModalOpen}
        onClose={() => setCommandModalOpen(false)}
        onNavigate={handleNavigate}
      />
    </div>
  );
}
