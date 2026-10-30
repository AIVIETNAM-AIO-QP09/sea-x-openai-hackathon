import { Inbox, RefreshCw, TriangleAlert, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { ApiError } from '../api/client';
import { viText } from '../lib/i18n';

export function PageHeader({ title, description, actions }: { title: string; description: string; actions?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 max-w-3xl text-muted">{description}</p>
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function EmptyState({
  title,
  body,
  icon: Icon = Inbox,
  action,
}: {
  title: string;
  body: string;
  icon?: LucideIcon;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center rounded-lg border border-dashed border-border bg-surface px-6 py-12 text-center">
      <Icon aria-hidden className="mb-3 size-8 text-muted" strokeWidth={1.5} />
      <h2 className="font-medium">{title}</h2>
      <p className="mt-1 max-w-md text-muted">{body}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  const code = error instanceof ApiError ? error.code : null;
  return (
    <div role="alert" className="flex items-start gap-3 rounded-lg border border-danger/40 bg-danger-soft px-4 py-3">
      <TriangleAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-danger" />
      <div className="min-w-0 flex-1">
        <p className="font-medium">{viText.state.errorTitle}</p>
        <p className="mt-0.5 text-muted">{message}</p>
        {code ? <p className="mt-0.5 text-xs text-muted">{viText.state.errorCode(code)}</p> : null}
      </div>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="btn-secondary">
          <RefreshCw aria-hidden className="size-4" />
          {viText.state.retry}
        </button>
      ) : null}
    </div>
  );
}

/** Layout-shaped placeholder rows (09 §4: skeleton, not a centered spinner). */
export function SkeletonRows({ rows = 3, label = viText.state.loading }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-2">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-14 animate-pulse rounded-lg bg-surface-2" />
      ))}
    </div>
  );
}
