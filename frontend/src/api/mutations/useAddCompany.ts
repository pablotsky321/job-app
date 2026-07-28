import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient, ApiError } from "@/api/client";
import { subscriptionsKey, companiesKey } from "@/api/queryKeys";
import type { CompanyCreateResponse } from "@/api/types";

interface AddCompanyParams {
  boardUrl: string;
}

/**
 * Adds a new company to the catalog (POST /companies) and then subscribes
 * the user to it (POST /me/companies/{companyId}).
 *
 * On HTTP 409 (company already exists), extracts companyId from the error body
 * and subscribes using that ID — no additional user action required.
 */
export function useAddCompany() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ boardUrl }: AddCompanyParams) => {
      let companyId: string;

      try {
        const created = await apiClient.post<CompanyCreateResponse>("/companies", {
          careersUrl: boardUrl,
        });
        companyId = created.companyId;
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          // Company already exists — get companyId from error body
          const body = error.body as { companyId?: string } | null;
          if (body?.companyId) {
            companyId = body.companyId;
          } else {
            throw error;
          }
        } else {
          throw error;
        }
      }

      // Subscribe the user to this company
      await apiClient.post(`/me/companies/${companyId}`);
      return companyId;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: subscriptionsKey() });
      queryClient.invalidateQueries({ queryKey: companiesKey() });
    },
  });
}
