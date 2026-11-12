/**
 * PayShield AI — Sign up
 * Account registration via the real /auth/register endpoint.
 */

import React, { useCallback, useState } from 'react';
import { registerUser } from '../../services/api';

interface SignUpPageProps {
  onAuthenticated: (profile: any) => void;
  onGoToSignIn: () => void;
}

export const SignUpPage: React.FC<SignUpPageProps> = ({
  onAuthenticated,
  onGoToSignIn,
}) => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    if (password.length < 12 || password.length > 128) {
      setError('Password must be between 12 and 128 characters.');
      return;
    }
    if (!/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/[0-9]/.test(password)) {
      setError('Password must contain uppercase, lowercase, and a number.');
      return;
    }
    setLoading(true);
    try {
      const profile = await registerUser({ email, name, password, confirm_password: confirmPassword });
      onAuthenticated(profile);
    } catch (err: any) {
      setError(err.message || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [name, email, password, confirmPassword, onAuthenticated]);

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
          <span className="material-symbols-outlined text-accent text-lg">person_add</span>
          <h1 className="font-headline-md text-ink">Create your PayShield account</h1>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-md bg-block/10 border border-block/30 text-block text-sm font-medium">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="ps-label">Full name</label>
            <input
              type="text"
              className="ps-input"
              placeholder="Jane Doe"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={loading}
            />
          </div>
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
            {loading ? 'Creating account…' : 'Create account'}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-ink-light">
          Already have an account?{' '}
          <button type="button" onClick={onGoToSignIn} className="text-accent font-medium hover:underline">
            Sign in
          </button>
        </p>
      </div>
    </div>
  );
};
