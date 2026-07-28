import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

interface ApplyVacancyParams {
  companyId: string;
  vacancyId: string;
}

export function useApplyVacancy() {
  return useMutation({
    mutationFn: ({ companyId, vacancyId }: ApplyVacancyParams) =>
      apiClient.post<void>(
        `/me/vacancies/${companyId}/${vacancyId}/apply`,
      ),
  });
}
