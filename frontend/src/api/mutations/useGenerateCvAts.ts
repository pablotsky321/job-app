import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

interface GenerateCvAtsParams {
  companyId: string;
  vacancyId: string;
}

export function useGenerateCvAts() {
  return useMutation({
    mutationFn: ({ companyId, vacancyId }: GenerateCvAtsParams) =>
      apiClient.post<string>(
        `/me/vacancies/${companyId}/${vacancyId}/cv`,
      ),
  });
}
