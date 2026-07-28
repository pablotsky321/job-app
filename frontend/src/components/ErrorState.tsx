import { cn } from "@/lib/cn";

/* ──────────────────────────────────────────────────────────────
   ErrorState — configurable error message + optional retry button.
   Visually distinct from EmptyState (uses error/red tones).
   ────────────────────────────────────────────────────────────── */

export interface ErrorStateProps {
  message: string;
  description?: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}

export function ErrorState({
  message,
  description,
  onRetry,
  retryLabel = "Reintentar",
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-12 text-center",
        className,
      )}
    >
      <svg
        className="mb-4 h-12 w-12 text-error"
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="12" r="10" />
        <path d="m15 9-6 6" />
        <path d="m9 9 6 6" />
      </svg>
      <p className="text-sm font-medium text-error-dark">{message}</p>
      {description && (
        <p className="mt-1 text-sm text-gray-500">{description}</p>
      )}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded-md bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2"
        >
          {retryLabel}
        </button>
      )}
    </div>
  );
}
