import { cn } from "@/lib/cn";

/* ──────────────────────────────────────────────────────────────
   EmptyState — configurable empty state message.
   Visually distinct from ErrorState (uses gray tones, neutral icon).
   ────────────────────────────────────────────────────────────── */

export interface EmptyStateProps {
  message: string;
  description?: string;
  className?: string;
}

export function EmptyState({ message, description, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-12 text-center",
        className,
      )}
    >
      <svg
        className="mb-4 h-12 w-12 text-gray-300"
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
      <p className="text-sm font-medium text-gray-600">{message}</p>
      {description && (
        <p className="mt-1 text-sm text-gray-400">{description}</p>
      )}
    </div>
  );
}
