import React, { useState, useEffect } from 'react';
import { PageId } from '../../types';

interface CommandModalProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (page: PageId) => void;
  onSearchQuery?: (q: string) => void;
}

export const CommandModal: React.FC<CommandModalProps> = ({
  isOpen,
  onClose,
  onNavigate,
}) => {
  const [query, setQuery] = useState('');

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const quickNav = [
    { id: 'overview' as PageId, label: 'Overview', icon: 'layout', category: 'Workspace' },
    { id: 'assistant-chat' as PageId, label: 'AI Assistant', icon: 'smart_toy', category: 'Workspace' },
    { id: 'product-search' as PageId, label: 'Product Search', icon: 'manage_search', category: 'Workspace' },
    { id: 'transactions' as PageId, label: 'Transactions', icon: 'receipt_long', category: 'Commerce' },
    { id: 'receipts' as PageId, label: 'Receipts', icon: 'article', category: 'Commerce' },
    { id: 'risk-intelligence' as PageId, label: 'Risk Intelligence', icon: 'security', category: 'Security' },
    { id: 'policies' as PageId, label: 'Policies', icon: 'tune', category: 'Security' },
    { id: 'audit-logs' as PageId, label: 'Audit Logs', icon: 'fingerprint', category: 'Security' },
    { id: 'lifecycle' as PageId, label: 'Lifecycle', icon: 'account_tree', category: 'Commerce' },
    { id: 'activity' as PageId, label: 'Activity', icon: 'history', category: 'Commerce' },
    { id: 'audit-investigation' as PageId, label: 'Audit Investigation', icon: 'policy', category: 'Security' },
    { id: 'alerts' as PageId, label: 'Alerts', icon: 'error', category: 'Security' },
    { id: 'budget-intelligence' as PageId, label: 'Budget Intelligence', icon: 'show_chart', category: 'Commerce' },
    { id: 'integrations' as PageId, label: 'Integrations', icon: 'integration_instructions', category: 'System' },
    { id: 'settings' as PageId, label: 'Settings', icon: 'settings', category: 'System' },
  ];

  const filtered = quickNav.filter((item) =>
    item.label.toLowerCase().includes(query.toLowerCase()) ||
    item.category.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 px-4" aria-modal="true" role="dialog" aria-label="Command palette">
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <div
        className="w-full max-w-lg bg-surface-white border border-border rounded-lg shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center px-4 py-3 border-b border-border">
          <span className="material-symbols-outlined text-ink-muted mr-2 text-lg">search</span>
          <input
            autoFocus
            type="text"
            className="flex-1 bg-transparent text-ink font-body-sm placeholder:text-ink-light focus:outline-none"
            placeholder="Go to page…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') onClose();
            }}
          />
          <kbd className="px-2 py-0.5 rounded-md bg-surface text-ink text-[10px] font-mono font-semibold border border-border">
            ESC
          </kbd>
        </div>

        <div className="p-2 max-h-[60vh] overflow-y-auto space-y-1">
          {filtered.length === 0 ? (
            <div className="px-4 py-6 text-center text-ink-light font-body-sm text-sm">
              No matching pages for "{query}".
            </div>
          ) : (
            <div className="space-y-1">
              <div className="px-2 py-1 font-label-xs text-xs text-ink-muted uppercase tracking-wider font-semibold">
                Quick navigation
              </div>
              {filtered.map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    onNavigate(item.id);
                    onClose();
                  }}
                  className="w-full flex items-center justify-between px-3 py-2 rounded-md text-left hover:bg-surface transition-colors group"
                >
                  <div className="flex items-center gap-3">
                    <span className="material-symbols-outlined text-ink-light group-hover:text-accent text-base shrink-0">
                      {item.icon}
                    </span>
                    <span className="font-body-sm text-sm text-ink group-hover:text-ink font-medium truncate">
                      {item.label}
                    </span>
                  </div>
                  <span className="font-label-xs text-xs text-ink-light font-mono shrink-0">
                    {item.category}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="px-4 py-2 border-t border-border flex items-center justify-between font-label-xs text-xs text-ink-muted font-mono">
          <span>Tip: Press ⌘K anywhere to open</span>
        </div>
      </div>
    </div>
  );
};
