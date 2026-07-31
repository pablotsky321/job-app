import { useAuth } from "@/auth/AuthContext";

/**
 * Landing page for unauthenticated users.
 * Displays static marketing copy, platform name/logo, and a login button.
 * Responsive on mobile/tablet/desktop.
 *
 * Requirements: 1.2, 1.3, 9.1, 9.2
 */
export function LandingPage() {
  const { login } = useAuth();

  return (
    <div className="mx-auto max-w-4xl px-4 py-16 sm:py-24 lg:py-32">
      {/* Hero section */}
      <div className="text-center">
        {/* Logo / Icon */}
        <div className="mb-8 flex justify-center">
          <div className="h-16 w-16 rounded-full bg-primary-500" />
        </div>

        {/* Headline */}
        <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl md:text-6xl">
          Encuentra tu próximo trabajo
        </h1>

        {/* Subheading */}
        <p className="mt-6 text-lg text-gray-600 sm:text-xl md:text-2xl">
          Escanea vacantes de múltiples fuentes, automatiza tu búsqueda y obtén recomendaciones
          personalizadas basadas en tu perfil.
        </p>

        {/* CTA Button */}
        <div className="mt-10">
          <button
            onClick={login}
            className="inline-flex items-center justify-center rounded-md bg-primary-600 px-8 py-3 text-base font-medium text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
          >
            Iniciar sesión
          </button>
        </div>
      </div>

      {/* Features section (optional, for more landing page depth) */}
      <div className="mt-20 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-6">
          <h3 className="text-lg font-semibold text-gray-900">Búsqueda inteligente</h3>
          <p className="mt-2 text-sm text-gray-600">
            Escanea vacantes de múltiples plataformas de empleo automáticamente.
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-gray-50 p-6">
          <h3 className="text-lg font-semibold text-gray-900">Recomendaciones personalizadas</h3>
          <p className="mt-2 text-sm text-gray-600">
            Recibe sugerencias basadas en tu perfil, habilidades y preferencias.
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-gray-50 p-6">
          <h3 className="text-lg font-semibold text-gray-900">Gestión simplificada</h3>
          <p className="mt-2 text-sm text-gray-600">
            Organiza tus postulaciones y mantén un seguimiento centralizado.
          </p>
        </div>
      </div>
    </div>
  );
}
