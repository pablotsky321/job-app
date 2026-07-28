import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { vacanciesKey } from "@/api/queryKeys";
import type { VacancyListItem } from "@/lib/types";

export type VacanciesEstado = "activas" | "aplicadas";

export function useVacancies(
  estado: VacanciesEstado,
  options?: { refetchInterval?: number | false },
) {
  return useQuery({
    queryKey: vacanciesKey(estado),
    queryFn: () =>
      apiClient.get<VacancyListItem[]>(`/me/vacancies?estado=${estado}`),
    refetchInterval: options?.refetchInterval,
  });
}
