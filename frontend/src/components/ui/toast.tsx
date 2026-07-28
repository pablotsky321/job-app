import * as React from "react";
import { cn } from "@/lib/cn";

/* ──────────────────────────────────────────────────────────────
   Toast — accessible toast notification using project tokens.
   Themed with project palette only (primary, gray, semantic).
   ────────────────────────────────────────────────────────────── */

export type ToastVariant = "default" | "success" | "error" | "warning";

export interface ToastProps {
  id: string;
  title?: string;
  description?: string;
  variant?: ToastVariant;
  onDismiss?: (id: string) => void;
  className?: string;
}

const variantStyles: Record<ToastVariant, string> = {
  default: "border-gray-200 bg-white text-gray-900",
  success: "border-success bg-success-light text-success-dark",
  error: "border-error bg-error-light text-error-dark",
  warning: "border-warning bg-warning-light text-warning-dark",
};

export function Toast({
  id,
  title,
  description,
  variant = "default",
  onDismiss,
  className,
}: ToastProps) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
      className={cn(
        "pointer-events-auto relative flex w-full items-center justify-between space-x-4 overflow-hidden rounded-md border p-4",
        variantStyles[variant],
        className,
      )}
    >
      <div className="flex-1">
        {title && <p className="text-sm font-semibold">{title}</p>}
        {description && <p className="text-sm opacity-90">{description}</p>}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={() => onDismiss(id)}
          className="inline-flex h-6 w-6 items-center justify-center rounded-md text-current opacity-70 hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-primary-400"
          aria-label="Cerrar notificación"
        >
          <svg
            className="h-4 w-4"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M18 6 6 18" />
            <path d="m6 6 12 12" />
          </svg>
        </button>
      )}
    </div>
  );
}

/* ── Toast Container (renders at the bottom-right) ── */

export interface ToastContainerProps {
  children: React.ReactNode;
}

export function ToastContainer({ children }: ToastContainerProps) {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-full max-w-sm">
      {children}
    </div>
  );
}
