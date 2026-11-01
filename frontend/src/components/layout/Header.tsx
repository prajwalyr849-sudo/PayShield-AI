import React, { useState } from 'react';
import { PageId, UserPublicProfile } from '../../types';

interface HeaderProps {
  currentPage: PageId;
  onOpenCommand: () => void;
  onOpenMobileMenu: () => void;
  alertCount?: number;
  user?: UserPublicProfile | null;
  onSignOut?: () => void;
}

const PAGE_TITLES: Record<string, string> = {
  overview: 'Overview',
  'assistant-chat': 'AI Assistant',
  'product-search': 'Product Search',
  transactions: 'Transactions',
  receipts: 'Receipts',
  'risk-intelligence': 'Risk Intelligence',
  policies: 'Policies',
  'audit-logs': 'Audit Logs',
  integrations: 'Integrations',
  settings: 'Settings',
  lifecycle: 'Lifecycle',
  activity: 'Activity',
  'audit-investigation': 'Audit Investigation',
  alerts: 'Alerts',
  checkout: 'Checkout',
};

export const Header: React.FC<HeaderProps> = ({
  currentPage,
  onOpenCommand,
  onOpenMobileMenu,
  alertCount = 0,
  user,
  onSignOut,
}) => {
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const title = PAGE_TITLES[currentPage] || 'PayShield AI';

  return (
    <header className="fixed top-0 left-0 lg:left-64 right-0 h-14 border-b border-border px-4 sm:px-6 flex items-center justify-between bg-white">
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenMobileMenu}
          className="lg:hidden p-2 rounded-md text-ink-light hover:text-ink hover:bg-surface transition-colors"
          aria-label="Open navigation menu"
        >
          <span className="material-symbols-outlined text-xl">menu</span>
        </button>
        <button
          type="button"
          onClick={onOpenCommand}
          className="ps-btn ps-btn-ghost flex items-center gap-2 text-sm px-3 py-1.5"
          aria-label="Open command palette"
        >
          <span className="material-symbols-outlined text-xs">search</span>
          <span className="font-label-sm text-[10px] text-ink-muted">K</span>
        </button>
      </div>

      <div className="hidden lg:flex items-center gap-4">
        <span className="font-label-sm text-[10px] text-ink-muted uppercase tracking-wider font-semibold">
          {title}
        </span>
        <div className="h-4 w-px border-border"></div>
        <ProfileTrigger
          user={user}
          onToggle={() => setProfileDropdownOpen(!profileDropdownOpen)}
        />
        {profileDropdownOpen && (
          <ProfileDropdown
            user={user}
            onSignOut={onSignOut}
            onClose={() => setProfileDropdownOpen(false)}
          />
        )}
      </div>
    </header>
  );
};

interface ProfileTriggerProps {
  user: UserPublicProfile | null;
  onToggle: () => void;
}

export const ProfileTrigger: React.FC<ProfileTriggerProps> = ({ user, onToggle }) => {
  return (
    <div
      onClick={onToggle}
      className="flex items-center gap-2 cursor-pointer px-2 py-1 rounded-md hover:bg-surface transition-colors"
    >
      <div className="w-8 h-8 rounded-md bg-accent text-white flex items-center justify-center text-accent-hover shadow-sm">
        <span className="material-symbols-outlined text-[12px] font-bold">
          {(user?.primary_email || '').charAt(0).toUpperCase()}
        </span>
      </div>
      {user ? (
        <div className="hidden md:flex flex-col text-left">
          <span className="font-body-sm text-xs font-semibold text-ink leading-tight">
            {user.full_name || user.primary_email}
          </span>
          <span className="font-label-xs text-[10px] text-ink-muted font-mono leading-none">
            {user.primary_email}
          </span>
        </div>
      ) : (
        <div className="hidden md:flex flex-col text-left">
          <span className="font-body-sm text-xs font-semibold text-ink leading-tight">
            Sign in
          </span>
          <span className="font-label-xs text-[10px] text-ink-muted font-mono leading-none">
            PayShield account
          </span>
        </div>
      )}
      <span className="material-symbols-outlined text-sm text-ink-muted">expand_more</span>
    </div>
  );
};

interface ProfileDropdownProps {
  user: UserPublicProfile | null;
  onSignOut: () => void;
  onClose: () => void;
}

export const ProfileDropdown: React.FC<ProfileDropdownProps> = ({
  user,
  onSignOut,
  onClose,
}) => {
  return (
    <div
      className="absolute right-0 mt-2 w-56 rounded-lg bg-white border border-border shadow-xl py-1"
      onClick={onClose}
    >
      {user ? (
        <>
          <div className="px-3 py-2 border-b border-border">
            <p className="text-xs font-semibold text-ink">{user.full_name || user.primary_email}</p>
            <p className="text-[11px] text-ink-muted font-mono">{user.primary_email}</p>
          </div>
          <div className="px-3 py-1">
            <button
              type="button"
              onClick={() => {
                onClose();
                onSignOut?.();
              }}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-xs font-medium text-block hover:bg-block/10 transition-colors"
            >
              <span className="material-symbols-outlined text-[14px]">logout</span>
              Sign out
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="px-3 py-2 border-b border-border">
            <p className="text-xs font-semibold text-ink">Not signed in</p>
            <p className="text-[11px] text-ink-muted font-mono">PayShield account</p>
          </div>
          <div className="px-3 py-1">
            <button
              type="button"
              onClick={onClose}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-xs font-medium text-accent hover:bg-accent-subtle transition-colors"
            >
              <span className="material-symbols-outlined text-[14px]">login</span>
              Sign in
            </button>
          </div>
        </>
      )}
    </div>
  );
};
