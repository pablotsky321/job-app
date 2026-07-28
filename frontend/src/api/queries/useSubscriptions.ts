import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { subscriptionsKey } from "@/api/queryKeys";
import type { SubscriptionListResponse } from "@/api/types";

export function useSubscriptions() {
  return useQuery({
    queryKey: subscriptionsKey(),
    queryFn: () => apiClient.get<SubscriptionListResponse>("/me/companies"),
  });
}
