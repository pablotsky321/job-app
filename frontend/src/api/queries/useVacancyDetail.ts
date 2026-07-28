import { useQuery } from "@tanstack/react-query";
import { apiClient, ApiError } from "@/api/client";
import { vacancyKey } from "@/api/queryKeys";

// TODO(dependencia-externa-pendiente): eliminar cuando openapi.json exponga el esquema real
export interface VacancyDetailResponse {
  companyId: string;
  vacancyId: string;
  titulo: string;
  empresa: string;
  ubicacion: string;
  modalidad: string;
  descripcion: string;
  urlPublicacion: string;
  estado: "activa" | "cerrada";
  score: number | null;
  veredicto: "excelente" | "buen_encaje" | "parcial" | "bajo" | null;
  coincidencias: string[];
  faltantes: string[];
  resumen: string | null;
  cvAtsTexto: string | null;
  appliedAt: string | null;
}

export function useVacancyDetail(companyId: string, vacancyId: string) {
  const query = useQuery({
    queryKey: vacancyKey(companyId, vacancyId),
    queryFn: () =>
      apiClient.get<VacancyDetailResponse>(
        `/me/vacancies/${companyId}/${vacancyId}`,
      ),
    enabled: !!companyId && !!vacancyId,
  });

  const isNotFound =
    query.error instanceof ApiError && query.error.status === 404;

  return { ...query, isNotFound };
}
