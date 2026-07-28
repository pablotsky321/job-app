import { useNavigate } from "react-router-dom";
import { useVacancies } from "@/api/queries/useVacancies";
import { VacancyCard } from "@/components/VacancyCard";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";

/* ──────────────────────────────────────────────────────────────
   ApplicationsListView — Requirement 10: shows applied vacancies
   using VacancyCard with hideAppliedCheck=true.
   ────────────────────────────────────────────────────────────── */

export function ApplicationsListView() {
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useVacancies("aplicadas");

  if (isLoading) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-6">
        <p className="text-sm text-gray-500">Cargando postulaciones…</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-6">
        <ErrorState
          message="Error al cargar postulaciones"
          description="Ocurrió un problema. Intenta de nuevo."
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-6">
        <EmptyState
          message="Sin postulaciones"
          description="Aún no te has presentado a ninguna vacante."
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <h1 className="mb-4 text-lg font-semibold text-gray-900">
        Postulaciones
      </h1>
      <div className="flex flex-col gap-3">
        {data.map((vacancy) => (
          <VacancyCard
            key={`${vacancy.companyId}-${vacancy.vacancyId}`}
            vacancy={vacancy}
            hideAppliedCheck
            onClick={() =>
              navigate(`/applications/${vacancy.companyId}/${vacancy.vacancyId}`)
            }
          />
        ))}
      </div>
    </div>
  );
}
