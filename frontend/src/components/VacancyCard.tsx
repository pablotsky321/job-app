import { cn } from "@/lib/cn";
import type { VacancyListItem } from "@/lib/types";
import { PlainText } from "./PlainText";
import { ScoreBadge } from "./ScoreBadge";
import { StaleBadge } from "./StaleBadge";

/* ──────────────────────────────────────────────────────────────
   VacancyCard — single-column card shared by Listado and
   Postulaciones views.
   
   Exact rendering order:
   1. Date + check (if applicable)
   2. ScoreBadge (or StaleBadge if staleFlag=true)
   3. Title
   4. Company
   5. Location / modality

   Border: 1px primary-100 / gray-200, NO shadow-* without re-theming.
   Optional prop `hideAppliedCheck` for reuse in Applications view.
   ────────────────────────────────────────────────────────────── */

export interface VacancyCardProps {
  vacancy: VacancyListItem;
  hideAppliedCheck?: boolean;
  onClick?: () => void;
  className?: string;
}

export function VacancyCard({
  vacancy,
  hideAppliedCheck = false,
  onClick,
  className,
}: VacancyCardProps) {
  const isApplied = vacancy.estadoAplicacion === "aplicada";
  const formattedDate = formatDate(vacancy.lastSeenAt);

  return (
    <article
      onClick={onClick}
      className={cn(
        "flex flex-col gap-2 rounded-md border border-primary-100 p-4",
        "transition-colors hover:border-primary-200 hover:bg-primary-50/30",
        onClick && "cursor-pointer",
        className,
      )}
    >
      {/* 1. Date + applied check */}
      <div className="flex items-center gap-2 text-xs text-gray-500">
        <time dateTime={vacancy.lastSeenAt}>
          <PlainText>{formattedDate}</PlainText>
        </time>
        {!hideAppliedCheck && isApplied && (
          <span className="inline-flex items-center gap-1 text-success">
            <svg
              className="h-3.5 w-3.5"
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M20 6 9 17l-5-5" />
            </svg>
            <span>aplicada</span>
          </span>
        )}
      </div>

      {/* 2. ScoreBadge or StaleBadge */}
      <div className="flex items-center gap-2">
        {vacancy.veredicto && !vacancy.staleFlag && (
          <ScoreBadge veredicto={vacancy.veredicto} score={vacancy.score} />
        )}
        {vacancy.veredicto && vacancy.staleFlag && (
          <>
            <ScoreBadge veredicto={vacancy.veredicto} score={vacancy.score} />
            <StaleBadge />
          </>
        )}
        {!vacancy.veredicto && vacancy.staleFlag && <StaleBadge />}
      </div>

      {/* 3. Title */}
      <h3 className="text-sm font-semibold text-gray-900">
        <PlainText>{vacancy.titulo}</PlainText>
      </h3>

      {/* 4. Company */}
      <p className="text-sm text-gray-600">
        <PlainText>{vacancy.empresa}</PlainText>
      </p>

      {/* 5. Location / modality */}
      <p className="text-xs text-gray-500">
        <PlainText>
          {vacancy.ubicacion}
          {vacancy.modalidad && vacancy.modalidad !== "sin_dato"
            ? ` · ${vacancy.modalidad}`
            : ""}
        </PlainText>
      </p>
    </article>
  );
}

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("es", {
      day: "numeric",
      month: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}
