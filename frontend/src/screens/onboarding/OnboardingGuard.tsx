import { type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useProfileCheckStatus } from "../../api/queries/useProfileCheckStatus";
import { resolveOnboardingGuardAction } from "../../lib/onboardingGuard";
import { ErrorState } from "../../components/ErrorState";

/**
 * Route guard for the /onboarding/:step route.
 * Ensures users with an existing profile are redirected to /profile for editing,
 * while users without a profile are allowed to proceed with the wizard.
 *
 * Wraps OnboardingWizard inside the /onboarding/:step route (which is itself nested inside AuthGuard).
 *
 * Requirements: 5.1, 5.2
 */
interface OnboardingGuardProps {
  children: ReactNode;
}

export function OnboardingGuard({ children }: OnboardingGuardProps) {
  const outcome = useProfileCheckStatus();

  // Loading state
  if (outcome.status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-300 border-t-primary-600" />
      </div>
    );
  }

  // Error state
  if (outcome.status === "error") {
    return (
      <ErrorState
        message="No se pudo verificar tu perfil"
        description={outcome.message}
        onRetry={() => window.location.reload()}
      />
    );
  }

  // Determine the action based on profile status
  const action = resolveOnboardingGuardAction(
    outcome.status === "exists" ? "exists" : "not_found",
  );

  // Redirect to profile edit screen if profile already exists
  if (action === "redirect_to_profile") {
    return <Navigate to="/profile" replace />;
  }

  // Render the wrapped onboarding wizard if no profile exists
  return <>{children}</>;
}
