import { cn } from "@/lib/cn";
import { scoreColorMapper } from "@/lib/scoreColorMapper";
import type { BadgeColor } from "@/lib/types";

/* ──────────────────────────────────────────────────────────────
   ScoreBadge — renders a colored badge based on `veredicto`.
   Maps BadgeColor → Tailwind classes using project tokens.
   Uses primary-100 bg + primary-900 text for the "primary" variant
   to ensure contrast compliance (Requirement 3 AC 3).
   ────────────────────────────────────────────────────────────── */

/**
 * Color mapping from BadgeColor to Tailwind classes.
 * - success → green (success-*)
 * - primary → blue (primary-*) — uses primary-100 bg + primary-900 text for contrast
 * - warning → amber/yellow (warning-*)
 * - gray → gray (gray-*)
 */
const badgeColorStyles: Record<BadgeColor, string> = {
  success: "bg-success-light text-success-dark",
  primary: "bg-primary-100 text-primary-900",
  warning: "bg-warning-light text-warning-dark",
  gray: "bg-gray-100 text-gray-700",
};

export interface ScoreBadgeProps {
  veredicto: "excelente" | "buen_encaje" | "parcial" | "bajo";
  score?: number | null;
  className?: string;
}

export function ScoreBadge({ veredicto, score, className }: ScoreBadgeProps) {
  const badgeColor = scoreColorMapper(veredicto);
  const label = veredicto.replace("_", " ");

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        badgeColorStyles[badgeColor],
        className,
      )}
    >
      {score !== null && score !== undefined && (
        <span className="font-semibold">{score}</span>
      )}
      <span>{label}</span>
    </span>
  );
}
