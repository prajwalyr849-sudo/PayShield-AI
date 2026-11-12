/**
 * PayShield AI — Sign in
 * Email/password sign-in and Google OAuth. Never auto-signs in a demo user;
 * authentication always goes through the real backend.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { getGoogleSignInUrl, loginUser } from '../../services/api';

interface SignInPageProps {
  onAuthenticated: (profile: any) => void;
  onGoToSignUp: () => void;
  onGoToForgotPassword: () => void;
  googleConfigured: boolean;
  googleError?: string | null;
}

export const SignInPage: React.FC<SignInPageProps> = ({
  onAuthenticated,
  onGoToSignUp,
  onGoToForgotPassword,
  googleConfigured,
  googleError,
}) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  // Strip the login_success param set by the Google OAuth callback without
  // reloading the page; the shell resolves the session via /auth/me.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('login_success')) {
      const url = new URL(window.location.href);
      url.searchParams.delete('login_success');
      window.history.replaceState({}, '', url.toString());
    }
  }, []);

  const handleGoogleSignIn = useCallback(async () => {
    setError(null);
    setGoogleLoading(true);
    try {
      const data = await getGoogleSignInUrl();
      window.location.href = data.authorization_url;
    } catch (err: any) {
      setError(err.message || 'Unable to start Google sign-in.');
      setGoogleLoading(false);
    }
  }, []);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const profile = await loginUser({ email, password });
      onAuthenticated(profile);
    } catch (err: any) {
      setError(err.message || 'Sign in failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [email, password, onAuthenticated]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <div className="ps-card w-full max-w-md p-6 md:p-8">
        <div className="flex items-center gap-3 mb-4">
          <span className="material-symbols-outlined text-accent text-lg">shield</span>
          <h1 className="font-headline-md text-ink">Sign in to PayShield AI</h1>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-md bg-block/10 border border-block/30 text-block text-sm font-medium">
            {error}
          </div>
        )}
        {googleError && (
          <div className="mb-4 p-3 rounded-md bg-block/10 border border-block/30 text-block text-sm font-medium">
            {googleError}
          </div>
        )}

        {googleConfigured && (
          <button
            type="button"
            onClick={handleGoogleSignIn}
            disabled={googleLoading}
            className="w-full ps-btn ps-btn-ghost mb-3 text-sm"
          >
            <span className="material-symbols-outlined text-[14px] mr-2">login</span>
            {googleLoading ? 'Redirecting to Google…' : 'Continue with Google'}
          </button>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="ps-label">Email address</label>
            <input
              type="email"
              className="ps-input"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
            />
          </div>
          <div>
            <label className="ps-label">Password</label>
            <input
              type="password"
              className="ps-input"
              placeholder="••••••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
            />
          </div>
          <button type="submit" disabled={loading} className="ps-btn ps-btn-primary w-full text-sm">
            {loading ? 'Signing in…' : 'Sign in with email'}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-ink-light">
          Don't have an account?{' '}
          <button type="button" onClick={onGoToSignUp} className="text-accent font-medium hover:underline">
            Create an account
          </button>
          &nbsp;·&nbsp;
          <button type="button" onClick={onGoToForgotPassword} className="text-accent font-medium hover:underline">
            Reset password
          </button>
        </p>
      </div>
    </div>
  );
};
