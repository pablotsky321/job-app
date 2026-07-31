import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";

/**
 * Navigation bar component shown on authenticated routes.
 * Three sections per Requirement 3.4:
 * - Left: logo/platform name linking to /
 * - Center: links (Vacantes, Postulaciones, Fuentes) visible only when authenticated
 * - Right: swaps between Iniciar sesión (unauth) and Perfil + Cerrar sesión (auth)
 *
 * Mobile disclosure panel below md breakpoint using aria-expanded/aria-controls + Tailwind responsive.
 *
 * Requirements: 3.1, 3.4, 9.4
 */
export function Navbar() {
  const { isAuthenticated, login, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <nav className="border-b border-gray-200 bg-white">
      <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between">
          {/* Left: Logo / Platform name */}
          <Link
            to="/"
            className="flex items-center gap-2 text-lg font-semibold text-gray-900 hover:text-gray-700"
          >
            <div className="h-8 w-8 rounded-full bg-primary-500" />
            <span>Job App</span>
          </Link>

          {/* Center: Navigation links (hidden on mobile, visible on md+) */}
          {isAuthenticated && (
            <div className="hidden md:flex gap-8">
              <Link
                to="/vacancies"
                className="text-sm font-medium text-gray-700 hover:text-gray-900"
              >
                Vacantes
              </Link>
              <Link
                to="/applications"
                className="text-sm font-medium text-gray-700 hover:text-gray-900"
              >
                Postulaciones
              </Link>
              <Link
                to="/sources"
                className="text-sm font-medium text-gray-700 hover:text-gray-900"
              >
                Fuentes
              </Link>
            </div>
          )}

          {/* Right: Auth buttons / Perfil */}
          <div className="flex items-center gap-4">
            {/* Desktop right section */}
            <div className="hidden md:flex items-center gap-4">
              {isAuthenticated ? (
                <>
                  <Link
                    to="/profile"
                    className="text-sm font-medium text-gray-700 hover:text-gray-900"
                  >
                    Perfil
                  </Link>
                  <button
                    onClick={logout}
                    className="text-sm font-medium text-gray-700 hover:text-gray-900"
                  >
                    Cerrar sesión
                  </button>
                </>
              ) : (
                <button
                  onClick={login}
                  className="text-sm font-medium text-primary-600 hover:text-primary-700"
                >
                  Iniciar sesión
                </button>
              )}
            </div>

            {/* Mobile menu toggle */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-expanded={mobileMenuOpen}
              aria-controls="mobile-menu"
              className="md:hidden inline-flex items-center justify-center rounded-md p-2 text-gray-700 hover:bg-gray-100 hover:text-gray-900"
            >
              <span className="sr-only">Abrir menú</span>
              {mobileMenuOpen ? (
                <svg
                  className="h-6 w-6"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              ) : (
                <svg
                  className="h-6 w-6"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 6h16M4 12h16M4 18h16"
                  />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* Mobile menu panel */}
        {mobileMenuOpen && (
          <div id="mobile-menu" className="mt-4 space-y-3 md:hidden">
            {isAuthenticated && (
              <>
                <Link
                  to="/vacancies"
                  className="block px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-gray-100"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Vacantes
                </Link>
                <Link
                  to="/applications"
                  className="block px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-gray-100"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Postulaciones
                </Link>
                <Link
                  to="/sources"
                  className="block px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-gray-100"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Fuentes
                </Link>
                <Link
                  to="/profile"
                  className="block px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-gray-100"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Perfil
                </Link>
              </>
            )}
            {isAuthenticated ? (
              <button
                onClick={() => {
                  logout();
                  setMobileMenuOpen(false);
                }}
                className="block w-full text-left px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-gray-100"
              >
                Cerrar sesión
              </button>
            ) : (
              <button
                onClick={() => {
                  login();
                  setMobileMenuOpen(false);
                }}
                className="block w-full text-left px-3 py-2 rounded-md text-base font-medium text-primary-600 hover:bg-gray-100"
              >
                Iniciar sesión
              </button>
            )}
          </div>
        )}
      </div>
    </nav>
  );
}
