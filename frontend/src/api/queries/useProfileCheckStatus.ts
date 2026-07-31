import { useProfileData } from "./useProfileData";
import { mapProfileQueryToOutcome } from "../profileCheck";
import type { ProfileCheckOutcome } from "../profileCheck";

/**
 * Derived hook that wraps useProfileData and maps its result to a navigation outcome.
 * Used by CallbackView (post-login navigation) and OnboardingGuard (route protection).
 *
 * Both useProfileData (full profile) and useProfileCheckStatus (outcome) share the same
 * queryKey (profileKey()) — there is only one cache entry under one shape (MeProfile),
 * never a duplicate query under the same key.
 *
 * Requirements: 2.2, 2.3, 2.4, 2.5, 5.2
 */
export function useProfileCheckStatus(): ProfileCheckOutcome {
  const query = useProfileData();
  return mapProfileQueryToOutcome({
    data: query.data,
    error: query.error,
    isError: query.isError,
    isLoading: query.isLoading,
  });
}
