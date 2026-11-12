import React from 'react';

interface EmptyStateProps {
  title: string;
  description: string;
  icon?: string;
  actionLabel?: string;
  onAction?: () => void;
  requirementNote?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  icon = 'inbox',
  actionLabel,
  onAction,
  requirementNote,
}) => {
  return (
    <div className="flex flex-col items-center justify-center p-8 sm:p-12 text-center rounded-lg border border-border shadow-sm max-w-2xl mx-auto my-6">
      <div className="w-12 h-12 rounded-md bg-surface text-ink-muted flex items-center justify-center mb-4">
        <span className="material-symbols-outlined text-2xl">{icon}</span>
      </div>
      <h3 className="font-headline-md text-ink font-semibold tracking-tight mb-2">
        {title}
      </h3>
      <p className="font-body-sm text-ink-muted max-w-md mb-6 leading-relaxed">
        {description}
      </p>

      {requirementNote && (
        <div className="w-full p-3 rounded-md bg-surface text-left font-label-sm text-xs text-ink-muted mb-6 border border-border flex items-start gap-2.5">
          <span className="material-symbols-outlined text-accent text-base shrink-0 mt-0.5">info</span>
          <div>
            <span className="text-ink font-semibold block mb-0.5">Note</span>
            <span>{requirementNote}</span>
          </div>
        </div>
      )}

      {actionLabel && onAction && (
        <button
          onClick={onAction}
          type="button"
          className="ps-btn ps-btn-primary flex items-center gap-2"
        >
          <span className="material-symbols-outlined text-xs">add</span>
          <span>{actionLabel}</span>
        </button>
      )}
    </div>
  );
};
