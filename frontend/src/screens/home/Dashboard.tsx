import { Link } from "react-router-dom";
import { tokenStore } from "@/auth/tokenStore";
import { getEmailFromIdToken } from "@/auth/idTokenClaims";

/**
 * Dashboard for authenticated users.
 * Displays a personalized greeting (extracted from id_token) and quick-access links.
 * Falls back gracefully (omits greeting) when the id_token is malformed/undecodable.
 *
 * Requirements: 1.4, 1.5, 9.1, 9.3
 */
export function Dashboard() {
  const email = getEmailFromIdToken(tokenStore.getIdToken() ?? "");

  return (
    <div className="mx-auto max-w-4xl px-4 py-16 sm:py-24">
      {/* Personalized greeting */}
      {email && (
        <div className="mb-12">
          <h1 className="text-3xl font-bold tracking-tight text-gray-900">
            ¡Hola, {email}!
          </h1>
          <p className="mt-2 text-lg text-gray-600">
            Bienvenido de vuelta a Job App.
          </p>
        </div>
      )}

      {!email && (
        <div className="mb-12">
          <h1 className="text-3xl font-bold tracking-tight text-gray-900">
            Bienvenido
          </h1>
          <p className="mt-2 text-lg text-gray-600">
            Inicia tu búsqueda de empleo.
          </p>
        </div>
      )}

      {/* Quick access links */}
      <div className="grid gap-6 sm:grid-cols-2">
        <Link
          to="/vacancies"
          className="flex flex-col rounded-lg border border-gray-200 bg-white p-6 shadow-sm hover:shadow-md hover:border-primary-200 transition-all"
        >
          <h2 className="text-lg font-semibold text-gray-900">Vacantes</h2>
          <p className="mt-2 text-sm text-gray-600">
            Explora vacantes recomendadas para ti.
          </p>
          <span className="mt-4 text-sm font-medium text-primary-600">
            Ver vacantes →
          </span>
        </Link>

        <Link
          to="/applications"
          className="flex flex-col rounded-lg border border-gray-200 bg-white p-6 shadow-sm hover:shadow-md hover:border-primary-200 transition-all"
        >
          <h2 className="text-lg font-semibold text-gray-900">Mis postulaciones</h2>
          <p className="mt-2 text-sm text-gray-600">
            Revisa el estado de tus postulaciones.
          </p>
          <span className="mt-4 text-sm font-medium text-primary-600">
            Ver postulaciones →
          </span>
        </Link>
      </div>
    </div>
  );
}
