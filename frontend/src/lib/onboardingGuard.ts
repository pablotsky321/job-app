import type { ProfileStatus } from "./postLoginRedirect";

/**
 * Determines whether a user should be allowed to proceed with onboarding or redirected to the profile edit screen.
 * Deliberately takes no `:step` parameter — the outcome must not depend on which step was requested.
 * If a user already has a profile, they should edit it via /profile instead of starting/continuing the wizard.
 *
 * Requirements: 5.2
 */
export type OnboardingGuardAction = "render" | "redirect_to_profile";

/**
 * Resolves the action for the OnboardingGuard.
 * - If the user's profile exists (`"exists"`), they should be redirected to /profile for editing.
 * - If the user has no profile yet (`"not_found"`), they may proceed with the onboarding wizard.
 *
 * This function is independent of the `:step` parameter — it only examines the profile-existence outcome.
 *
 * @param profileStatus the outcome of the profile-check query
 * @returns the action the guard should take
 */
export function resolveOnboardingGuardAction(
  profileStatus: ProfileStatus,
): OnboardingGuardAction {
  if (profileStatus === "exists") {
    return "redirect_to_profile";
  }

  // profileStatus === "not_found"
  return "render";
}
