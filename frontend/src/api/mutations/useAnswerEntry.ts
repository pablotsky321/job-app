import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { entriesKey } from "@/api/queryKeys";
import type { EntryResponse } from "@/api/queries/useEntries";

interface AnswerEntryParams {
  companyId: string;
  vacancyId: string;
  entryId: string;
}

export function useAnswerEntry() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ companyId, vacancyId, entryId }: AnswerEntryParams) =>
      apiClient.post<EntryResponse>(
        `/me/vacancies/${companyId}/${vacancyId}/entries/${entryId}/answer`,
      ),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: entriesKey(variables.companyId, variables.vacancyId),
      });
    },
  });
}
