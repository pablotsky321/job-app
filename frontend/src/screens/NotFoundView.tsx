import { Link } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { Navbar } from "@/components/Navbar";

/**
 * Public 404 page shown when a user navigates to an unmapped route.
 * This route is registered at the top level (path="*") outside the Layout wrapper,
 * allowing it to render the Navbar directly when authenticated (violating the "no duplication"
 * rule is avoided because it's the same component instance, not a duplicate implementation).
 *
 * Behavior:
 * - Always renders a "Volver al inicio" link to /
 * - If unauthenticated: also renders an "Iniciar sesión" button calling login()
 * - If authenticated: renders the Navbar above the 404 content
 *
 * Requirements: 7.2
 */
export function NotFoundView() {
  const { isAuthenticated, login } = useAuth();

  return (
    <>
      {isAuthenticated && <Navbar />}
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-50 px-4 py-16">
        <div className="text-center">
          {/* 404 Heading */}
          <h1 className="text-6xl font-bold text-gray-900">404</h1>

          {/* Description */}
          <p className="mt-4 text-lg font-semibold text-gray-900">Página no encontrada</p>
          <p className="mt-2 text-sm text-gray-600">
            La página que buscas no existe o ha sido movida.
          </p>

          {/* Actions */}
          <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:justify-center">
            <Link
              to="/"
              className="inline-flex items-center justify-center rounded-md bg-primary-600 px-6 py-3 text-sm font-medium text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
            >
              Volver al inicio
            </Link>

            {!isAuthenticated && (
              <button
                onClick={login}
                className="inline-flex items-center justify-center rounded-md border border-gray-300 bg-white px-6 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
              >
                Iniciar sesión
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
