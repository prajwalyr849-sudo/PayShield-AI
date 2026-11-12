import React, { useEffect } from 'react';
import { PageId } from '../../types';

interface SidebarProps {
  currentPage: PageId;
  onNavigate: (page: PageId) => void;
  alertCount?: number;
  isOpenMobile?: boolean;
  onCloseMobile?: () => void;
}

const navSections = [
  {
    title: 'WORKSPACE',
    items: [
      { id: 'overview' as PageId, label: 'Overview', icon: 'layout' },
      { id: 'assistant-chat' as PageId, label: 'AI Assistant', icon: 'smart_toy' },
      { id: 'product-search' as PageId, label: 'Product Search', icon: 'manage_search' },
    ],
  },
  {
    title: 'COMMERCE',
    items: [
      { id: 'transactions' as PageId, label: 'Transactions', icon: 'receipt_long' },
      { id: 'receipts' as PageId, label: 'Receipts', icon: 'article' },
    ],
  },
  {
    title: 'SECURITY',
    items: [
      { id: 'risk-intelligence' as PageId, label: 'Risk Intelligence', icon: 'security' },
      { id: 'policies' as PageId, label: 'Policies', icon: 'tune' },
      { id: 'audit-logs' as PageId, label: 'Audit Logs', icon: 'fingerprint' },
    ],
  },
  {
    title: 'SYSTEM',
    items: [
      { id: 'integrations' as PageId, label: 'Integrations', icon: 'integration_instructions' },
      { id: 'settings' as PageId, label: 'Settings', icon: 'settings' },
    ],
  },
];

export const Sidebar: React.FC<SidebarProps> = ({
  currentPage,
  onNavigate,
  alertCount = 0,
  isOpenMobile,
  onCloseMobile,
}) => {
  // Escape closes the mobile navigation drawer for keyboard users.
  useEffect(() => {
    if (!isOpenMobile) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && onCloseMobile) onCloseMobile();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpenMobile, onCloseMobile]);

  const sidebarContent = (
    <div className="h-full flex flex-col">
      {/* Brand */}
      <div className="px-5 py-6 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-md bg-accent text-white flex items-center justify-center text-accent-hover shadow-sm">
            <span className="material-symbols-outlined text-xs font-bold">shield</span>
          </div>
          <div className="flex flex-col">
            <span className="font-headline-sm text-lg text-ink font-semibold tracking-tight leading-none">
              PayShield<span className="text-accent">AI</span>
            </span>
            <span className="font-label-xs text-[10px] text-ink-muted leading-tight">
              Transaction Security
            </span>
          </div>
        </div>
        {onCloseMobile && (
          <button
            onClick={onCloseMobile}
            className="lg:hidden p-2 rounded-md text-ink-light hover:text-ink hover:bg-surface transition-colors"
            aria-label="Close menu"
          >
            <span className="material-symbols-outlined text-lg">close</span>
          </button>
        )}
      </div>

      {/* Navigation Sections */}
      <div className="overflow-y-auto px-3 py-4 space-y-5">
        {navSections.map((sec) => (
          <nav key={sec.title} className="space-y-0.5">
            <div className="px-2 mb-1 font-label-xs text-[10px] text-ink-muted uppercase tracking-wider font-semibold">
              {sec.title}
            </div>
            {sec.items.map((item) => {
              const isActive = currentPage === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  aria-current={isActive ? 'page' : undefined}
                  onClick={() => {
                    onNavigate(item.id);
                    if (onCloseMobile) onCloseMobile();
                  }}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors font-body-sm text-sm ${
                    isActive
                      ? 'bg-accent-subtle text-accent font-medium'
                      : 'text-ink-muted hover:text-ink hover:bg-surface'
                  }`}
                >
                  <span
                    className={`material-symbols-outlined text-[15px] shrink-0 ${
                      isActive ? 'text-accent' : 'text-ink-muted'
                    }`}
                  >
                    {item.icon}
                  </span>
                  <span className="truncate">{item.label}</span>
                  {item.id === 'alerts' && alertCount > 0 && (
                    <span className="px-1.5 py-0.5 rounded-md bg-block text-white font-mono text-[10px] font-bold">
                      {alertCount}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        ))}
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Persistent Aside */}
      <aside className="hidden lg:flex fixed left-0 top-0 h-full w-64 bg-surface-white z-40 flex-col border-r border-border">
        {sidebarContent}
      </aside>

      {/* Mobile Drawer */}
      {isOpenMobile && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div className="fixed inset-0 bg-black/30 backdrop-blur-sm" onClick={onCloseMobile} />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Navigation menu"
            className="relative w-72 max-w-[85vw] h-full bg-surface-white z-50 flex flex-col shadow-xl border-r border-border"
          >
            {sidebarContent}
          </aside>
        </div>
      )}
    </>
  );
};
