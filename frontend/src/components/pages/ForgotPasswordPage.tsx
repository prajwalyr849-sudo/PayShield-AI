/**
 * PayShield AI — Forgot password
 * Password reset request via /auth/password-reset/request.
 */

import React, { useCallback, useState } from 'react';
import { requestPasswordReset } from '../../services/api';

interface ForgotPasswordPageProps {
  onGoToSignIn: () => void;
}

export const ForgotPasswordPage: React.FC<ForgotPasswordPageProps> = ({
  onGoToSignIn,
}) => {
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setLoading(true);
    try {
      const result = await requestPasswordReset({ email });
      if (result.dev_mode && result.reset_token) {
        setSuccess(
          `Reset token (dev mode): ${result.reset_token}. Use it on the reset password page.`
        );
      } else {
        setSuccess('If an account exists for that email, a reset link has been sent.');
      }
    } catch (err: any) {
      setError(err.message || 'Unable to request a reset. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [email]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <div className="ps-card w-full max-w-md p-6 md:p-8">
        <div className="flex items-center gap-3 mb-4">
          <span className="material-symbols-outlined text-accent text-lg">email</span>
          <h1 className="font-headline-md text-ink">Forgot your password?</h1>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-md bg-block/10 border border-block/30 text-block text-sm font-medium">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-4 p-3 rounded-md bg-success-subtle border border-success/30 text-success text-sm font-medium">
            {success}
          </div>
        )}

        {!success && (
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
            <button type="submit" disabled={loading} className="ps-btn ps-btn-primary w-full text-sm">
              {loading ? 'Sending reset link…' : 'Send reset link'}
            </button>
          </form>
        )}

        <p className="mt-6 text-center text-xs text-ink-light">
          <button type="button" onClick={onGoToSignIn} className="text-accent font-medium hover:underline">
            Go to sign in
          </button>
        </p>
      </div>
    </div>
  );
};
