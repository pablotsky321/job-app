/**
 * Resolves the post-login navigation destination based on profile-check outcome.
 * Pure, synchronously-testable logic extracted from CallbackView.
 *
 * Requirements: 2.3, 2.4, 6.2
 */
export type ProfileStatus = "exists" | "not_found";

/**
 * Determines where a user should be redirected after login completes.
 * - If profile does not exist (`"not_found"`), always redirect to onboarding, ignoring any saved redirect.
 * - If profile exists (`"exists"`), use the saved redirect when it is a non-empty string, otherwise default to home.
 *
 * @param profileStatus the outcome of the profile-check query
 * @param savedRedirect the route that was saved before login (may be null or empty string)
 * @returns the destination route
 */
export function resolvePostLoginDestination(
  profileStatus: ProfileStatus,
  savedRedirect: string | null,
): string {
  if (profileStatus === "not_found") {
    return "/onboarding/1";
  }

  // profileStatus === "exists"
  if (savedRedirect && savedRedirect.trim()) {
    return savedRedirect;
  }

  return "/";
}
