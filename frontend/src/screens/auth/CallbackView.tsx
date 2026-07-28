import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";

/**
 * Handles the OAuth callback route (/callback).
 * - If `code` is present: exchanges it for tokens via handleCallback.
 * - If `error` is present (e.g. user cancelled): shows cancellation message with retry.
 */
export function CallbackView() {
  const [searchParams] = useSearchParams();
  const { handleCallback, login } = useAuth();
  const [error, setError] = useState<string | null>(null);

  const code = searchParams.get("code");
  const oauthError = searchParams.get("error");

  useEffect(() => {
    if (code) {
      handleCallback(code).catch((err) => {
        setError(err instanceof Error ? err.message : "Token exchange failed");
      });
    }
  }, [code, handleCallback]);

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

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <p className="mb-4 text-red-600">Error: {error}</p>
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

  // Loading state while exchanging code for tokens
  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-gray-500">Autenticando...</p>
    </div>
  );
}
