import { useEffect, useState, useCallback, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { useProfileCheckStatus } from "../../api/queries/useProfileCheckStatus";
import { resolvePostLoginDestination } from "../../lib/postLoginRedirect";
import { ErrorState } from "../../components/ErrorState";

/**
 * Helper: log structured errors without revealing sensitive data (CV text, profile content).
 */
function logStructuredError(event: string, detail: unknown): void {
  console.error(
    JSON.stringify({
      event,
      detail:
        detail instanceof Error
          ? {
              name: detail.name,
              message: detail.message,
            }
          : detail,
      timestamp: new Date().toISOString(),
    }),
  );
}

/**
 * Handles the OAuth callback route (/callback).
 * After exchanging the code for tokens (which handleCallback does synchronously),
 * CallbackView takes over navigation based on a profile-existence check.
 *
 * Post-login flow:
 * 1. User is redirected from Cognito with ?code=...
 * 2. handleCallback exchanges code for tokens and sets isAuthenticated
 * 3. sessionStorage keys are cleared immediately after token exchange succeeds
 * 4. useProfileCheckStatus reads the profile-existence outcome
 * 5. Navigation is determined based on that outcome + any saved redirect
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 6.2, 6.3, 8.2, 8.3, 10.1, 10.2, 10.3, 10.4
 *
 * Nota (fix post-checkpoint-16): el efecto de intercambio de código está protegido con
 * `exchangeAttempted` (useRef) porque React.StrictMode invoca los efectos dos veces en
 * desarrollo, y el código de autorización de Cognito es de un solo uso — sin este candado,
 * la segunda invocación siempre falla con 400 aunque la primera haya tenido éxito.
 */
export function CallbackView() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { handleCallback, login } = useAuth();
  const profileCheckOutcome = useProfileCheckStatus();
  const [tokenExchangeError, setTokenExchangeError] = useState<string | null>(null);
  const exchangeAttempted = useRef(false);

  const code = searchParams.get("code");
  const oauthError = searchParams.get("error");

  // Effect 1: Exchange code for tokens (if present) — guarded against StrictMode double-invoke
  useEffect(() => {
    if (code && !tokenExchangeError && !exchangeAttempted.current) {
      exchangeAttempted.current = true;
      handleCallback(code)
        .then(() => {
          // Token exchange succeeded — clear sessionStorage keys immediately
          sessionStorage.removeItem("post_login_redirect");
          sessionStorage.removeItem("pkce_code_verifier");
          // Profile check will now run via useProfileCheckStatus()
        })
        .catch((err) => {
          logStructuredError("token_exchange_failed", err);
          setTokenExchangeError(
            err instanceof Error ? err.message : "Token exchange failed",
          );
        });
    }
  }, [code, handleCallback, tokenExchangeError]);

  // Effect 2: Navigate based on profile check outcome (only after token exchange succeeded)
  useEffect(() => {
    if (!tokenExchangeError && code && profileCheckOutcome.status !== "loading") {
      const savedRedirect = sessionStorage.getItem("post_login_redirect");

      if (profileCheckOutcome.status === "error") {
        // Profile check failed — show error state with retry
        logStructuredError("profile_check_failed", profileCheckOutcome.message);
        return; // Render error UI; user can retry via refetch button
      }

      // Determine destination based on profile status
      const profileStatus = profileCheckOutcome.status === "exists" ? "exists" : "not_found";
      const destination = resolvePostLoginDestination(profileStatus, savedRedirect);

      navigate(destination, { replace: true });
    }
  }, [profileCheckOutcome, tokenExchangeError, code, navigate]);

  const handleRetryProfileCheck = useCallback(() => {
    // The refetch function will be injected when we integrate with useProfileCheckStatus's query
    // For now, this is a placeholder; the ErrorState will handle calling refetch() directly
  }, []);

  // --- OAuth error (user cancelled login) ---
  if (oauthError) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <p className="mb-4 text-gray-700">El inicio de sesión no se completó.</p>
          <button
            onClick={() => login()}
            className="rounded bg-primary-600 px-4 py-2 text-white hover:bg-primary-700"
          >
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  // --- Token exchange error ---
  if (tokenExchangeError) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <p className="mb-4 text-red-600">Error: {tokenExchangeError}</p>
          <button
            onClick={() => login()}
            className="rounded bg-primary-600 px-4 py-2 text-white hover:bg-primary-700"
          >
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  // --- Profile check error (after token exchange succeeded) ---
  if (profileCheckOutcome.status === "error") {
    return (
      <ErrorState
        message="No se pudo verificar tu perfil"
        description={profileCheckOutcome.message}
        onRetry={handleRetryProfileCheck}
      />
    );
  }

  // --- Loading state (exchanging code or checking profile) ---
  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-gray-500">Autenticando...</p>
    </div>
  );
}