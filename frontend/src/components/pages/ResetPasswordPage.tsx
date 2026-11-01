/**
 * PayShield AI — Reset password
 * Password reset confirmation via /auth/password-reset/confirm.
 * The token is read from the URL query parameter.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { confirmPasswordReset } from '../../services/api';

interface ResetPasswordPageProps {
  onGoToSignIn: () => void;
}

export const ResetPasswordPage: React.FC<ResetPasswordPageProps> = ({
  onGoToSignIn,
}) => {
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const t = params.get('token') || null;
    setToken(t);
    if (t && success) {
      // Clean the token from the URL after a successful reset.
      const url = new URL(window.location.href);
      url.searchParams.delete('token');
      window.history.replaceState({}, '', url.toString());
    }
  }, [token, success]);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!token) {
      setError('No reset token provided.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    try {
      const result = await confirmPasswordReset({ token, password });
      if (result.status === 'password_updated') {
        setSuccess('Your password has been reset. You can sign in now.');
      }
    } catch (err: any) {
      setError(err.message || 'Unable to reset password. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [token, password, confirmPassword]);

  const meets = {
    length: password.length >= 12 && password.length <= 128,
    upper: /[A-Z]/.test(password),
    lower: /[a-z]/.test(password),
    digit: /[0-9]/.test(password),
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <div className="ps-card w-full max-w-md p-6 md:p-8">
        <div className="flex items-center gap-3 mb-4">
          <span className="material-symbols-outlined text-accent text-lg">key</span>
          <h1 className="font-headline-md text-ink">Reset your password</h1>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-md bg-block/10 border border-block/30 text-block text-sm font-medium">
            {error}
          </div>
        )}

        {!token && (
          <div className="text-center">
            <p className="font-body-sm text-sm text-ink-muted">Invalid or missing reset link.</p>
            <button type="button" onClick={onGoToSignIn} className="mt-4 text-accent font-medium hover:underline">
              Go to sign in
            </button>
          </div>
        )}

        {token && !success && (
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="ps-label">New password</label>
              <input
                type="password"
                className="ps-input"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
              />
              <div className="mt-1 space-y-1">
                <div className="flex items-center gap-1">
                  <span className={`text-[10px] ${meets.length ? 'text-success' : 'text-ink-light'}`}>{meets.length ? '✓' : '•'}</span>
                  <span className="text-[10px] text-ink-light">12–128 characters</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className={`text-[10px] ${meets.upper ? 'text-success' : 'text-ink-light'}`}>{meets.upper ? '✓' : '•'}</span>
                  <span className="text-[10px] text-ink-light">Uppercase letter</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className={`text-[10px] ${meets.lower ? 'text-success' : 'text-ink-light'}`}>{meets.lower ? '✓' : '•'}</span>
                  <span className="text-[10px] text-ink-light">Lowercase letter</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className={`text-[10px] ${meets.digit ? 'text-success' : 'text-ink-light'}`}>{meets.digit ? '✓' : '•'}</span>
                  <span className="text-[10px] text-ink-light">Number</span>
                </div>
              </div>
            </div>
            <div>
              <label className="ps-label">Confirm password</label>
              <input
                type="password"
                className="ps-input"
                placeholder="••••••••••••"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={loading}
              />
            </div>
            <button type="submit" disabled={loading} className="ps-btn ps-btn-primary w-full text-sm">
              {loading ? 'Resetting password…' : 'Reset password'}
            </button>
          </form>
        )}

        {success && (
          <div className="text-center">
            <p className="font-body-sm text-sm text-success font-medium">{success}</p>
            <button type="button" onClick={onGoToSignIn} className="mt-4 text-accent font-medium hover:underline">
              Go to sign in
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
