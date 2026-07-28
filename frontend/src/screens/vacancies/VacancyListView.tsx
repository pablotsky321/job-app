import { useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useVacancies, type VacanciesEstado } from "@/api/queries/useVacancies";
import { vacanciesKey } from "@/api/queryKeys";
import { hasStaleItems, reconcileFrozenOrder } from "@/lib/rescoringFreeze";
import type { VacancyListItem } from "@/lib/types";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { VacancyCard } from "@/components/VacancyCard";
import { EmptyState } from "@/components/EmptyState";

const MAX_REFETCH_ATTEMPTS = 24;

function VacancyTab({ estado }: { estado: VacanciesEstado }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const frozenOrderRef = useRef<VacancyListItem[] | null>(null);
  const refetchCountRef = useRef(0);
  const cappedRef = useRef(false);

  const { data, dataUpdatedAt } = useVacancies(estado, {
    refetchInterval: cappedRef.current
      ? false
      : frozenOrderRef.current !== null
        ? 5_000
        : false,
  });

  // Derive display list with freeze logic
  const displayItems = useComputeDisplay(
    data,
    dataUpdatedAt,
    frozenOrderRef,
    refetchCountRef,
    cappedRef,
  );

  const handleManualRefresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: vacanciesKey(estado) });
  }, [queryClient, estado]);

  if (!data) return null;

  if (displayItems.length === 0) {
    return (
      <EmptyState
        message={
          estado === "activas"
            ? "No hay vacantes activas"
            : "No hay vacantes aplicadas"
        }
        description="Las vacantes aparecerán aquí cuando se encuentren en un escaneo."
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {cappedRef.current && (
        <div className="flex items-center justify-between rounded-md border border-warning-light bg-warning-light/20 px-4 py-2">
          <span className="text-sm text-gray-700">
            Algunos scores siguen actualizándose.
          </span>
          <button
            type="button"
            onClick={handleManualRefresh}
            className="rounded-md bg-primary-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-600 transition-colors"
          >
            Actualizar
          </button>
        </div>
      )}
      {displayItems.map((v) => (
        <VacancyCard
          key={`${v.companyId}#${v.vacancyId}`}
          vacancy={v}
          onClick={() => navigate(`/vacancies/${v.companyId}/${v.vacancyId}`)}
        />
      ))}
    </div>
  );
}

/**
 * Hook-like function that computes the display list applying freeze logic.
 * Mutates refs for freeze state tracking.
 */
function useComputeDisplay(
  data: VacancyListItem[] | undefined,
  dataUpdatedAt: number,
  frozenOrderRef: React.MutableRefObject<VacancyListItem[] | null>,
  refetchCountRef: React.MutableRefObject<number>,
  cappedRef: React.MutableRefObject<boolean>,
): VacancyListItem[] {
  const prevUpdatedAtRef = useRef(0);

  if (!data) return [];

  // Detect new data arrival
  const isNewData = dataUpdatedAt !== prevUpdatedAtRef.current;
  if (isNewData) {
    prevUpdatedAtRef.current = dataUpdatedAt;

    const stale = hasStaleItems(data);

    if (stale && !cappedRef.current) {
      // Increment refetch counter on each new response with stale items
      if (frozenOrderRef.current !== null) {
        refetchCountRef.current += 1;
      }

      if (refetchCountRef.current >= MAX_REFETCH_ATTEMPTS) {
        // Cap reached — stop freezing and refetching
        cappedRef.current = true;
        frozenOrderRef.current = null;
        return data;
      }

      if (frozenOrderRef.current === null) {
        // First time seeing stale — initialize freeze
        frozenOrderRef.current = data;
        refetchCountRef.current = 0;
      } else {
        // Reconcile frozen order with latest data
        frozenOrderRef.current = reconcileFrozenOrder(
          frozenOrderRef.current,
          data,
        );
      }
    } else if (!stale) {
      // No stale items — unfreeze
      frozenOrderRef.current = null;
      refetchCountRef.current = 0;
      cappedRef.current = false;
    }
  }

  return frozenOrderRef.current ?? data;
}

export function VacancyListView() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <h1 className="mb-4 text-lg font-semibold text-gray-900">Vacantes</h1>
      <Tabs defaultValue="activas">
        <TabsList>
          <TabsTrigger value="activas">Activas</TabsTrigger>
          <TabsTrigger value="aplicadas">Aplicadas</TabsTrigger>
        </TabsList>
        <TabsContent value="activas">
          <VacancyTab estado="activas" />
        </TabsContent>
        <TabsContent value="aplicadas">
          <VacancyTab estado="aplicadas" />
        </TabsContent>
      </Tabs>
    </div>
  );
}
