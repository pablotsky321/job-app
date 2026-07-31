import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { apiClient } from "../client";
import { profileKey } from "../queryKeys";
import type { MeProfile } from "../types";

/**
 * React Query hook for fetching the authenticated user's profile.
 * Single source of truth for GET /me/profile queries.
 * Used by both ProfileView (full profile data) and useProfileCheckStatus (existence check).
 *
 * Requirements: 4.2, 4.5, 4.6
 */
export function useProfileData(): UseQueryResult<MeProfile> {
  return useQuery({
    queryKey: profileKey(),
    queryFn: async () => {
      const response = await apiClient.get<MeProfile>("/me/profile");
      return response;
    },
  });
}
