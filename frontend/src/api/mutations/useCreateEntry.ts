import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { entriesKey } from "@/api/queryKeys";
import type { EntryResponse } from "@/api/queries/useEntries";

interface CreateEntryParams {
  companyId: string;
  vacancyId: string;
  tipo: EntryResponse["tipo"];
  contenido: string;
}

export function useCreateEntry() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ companyId, vacancyId, tipo, contenido }: CreateEntryParams) =>
      apiClient.post<EntryResponse>(
        `/me/vacancies/${companyId}/${vacancyId}/entries`,
        { tipo, contenido },
      ),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: entriesKey(variables.companyId, variables.vacancyId),
      });
    },
  });
}
