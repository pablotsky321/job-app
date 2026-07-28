import * as React from "react";
import { cn } from "@/lib/cn";

/* ──────────────────────────────────────────────────────────────
   Progress — accessible progress bar using project tokens.
   Themed with project palette only (primary, gray, semantic).
   ────────────────────────────────────────────────────────────── */

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number;
  max?: number;
}

export const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  ({ className, value = 0, max = 100, ...props }, ref) => {
    const percentage = Math.min(100, Math.max(0, (value / max) * 100));

    return (
      <div
        ref={ref}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        className={cn(
          "relative h-3 w-full overflow-hidden rounded-full bg-gray-100",
          className,
        )}
        {...props}
      >
        <div
          className="h-full rounded-full bg-primary-500 transition-all duration-300"
          style={{ width: `${percentage}%` }}
        />
      </div>
    );
  },
);
Progress.displayName = "Progress";
