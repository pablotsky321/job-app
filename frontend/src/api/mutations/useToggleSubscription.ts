import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { subscriptionsKey } from "@/api/queryKeys";
import type { SubscriptionUpdateResponse } from "@/api/types";

interface ToggleSubscriptionParams {
  companyId: string;
  activa: boolean;
}

export function useToggleSubscription() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ companyId, activa }: ToggleSubscriptionParams) =>
      apiClient.put<SubscriptionUpdateResponse>(`/me/companies/${companyId}`, {
        activa,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: subscriptionsKey() });
    },
  });
}
