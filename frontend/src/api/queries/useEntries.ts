import { useQuery } from "@tanstack/react-query";
import { apiClient, ApiError } from "@/api/client";
import { entriesKey } from "@/api/queryKeys";

// TODO(dependencia-externa-pendiente): eliminar cuando openapi.json exponga el esquema
export interface EntryResponse {
  entryId: string;
  tipo: "nota_entrevista" | "preguntas" | "respuesta_ia" | "observacion";
  contenido: string;
  creadoAt: string;
}

export function useEntries(companyId: string, vacancyId: string) {
  const query = useQuery({
    queryKey: entriesKey(companyId, vacancyId),
    queryFn: () =>
      apiClient.get<EntryResponse[]>(
        `/me/vacancies/${companyId}/${vacancyId}/entries`,
      ),
    enabled: !!companyId && !!vacancyId,
  });

  const isNotFound =
    query.error instanceof ApiError && query.error.status === 404;

  return { ...query, isNotFound };
}
