import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { apiClient, ApiError } from "@/api/client";
import { ErrorState } from "@/components/ErrorState";

interface ProfileResponse {
  resumenGenerating: boolean;
  resumenParaMatching: string | null;
  cargosActivos: string[];
}

interface SuggestResponse {
  suggestions: string[];
  suggestedAt: string;
}

const MAX_ROLES = 10;
const MAX_ROLE_LENGTH = 50;
const POLL_INTERVAL = 3_000;
const POLL_TIMEOUT = 30_000;

export function Step2Roles() {
  const navigate = useNavigate();
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [customRole, setCustomRole] = useState("");
  const [phase, setPhase] = useState<"loading" | "polling" | "selecting" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollStartRef = useRef<number>(0);

  // Suggest roles mutation
  const suggestMutation = useMutation({
    mutationFn: () => apiClient.post<SuggestResponse>("/me/profile/roles/suggest"),
    onSuccess: (data) => {
      stopPolling();
      setSuggestions(data.suggestions);
      setPhase("selecting");
    },
    onError: (error: Error) => {
      if (error instanceof ApiError && error.status === 424) {
        // Resume not ready — start polling
        startPolling();
      } else {
        setErrorMessage("No se pudieron obtener sugerencias. Intenta de nuevo.");
        setPhase("error");
      }
    },
  });

  // Save roles mutation
  const saveRolesMutation = useMutation({
    mutationFn: (roles: string[]) =>
      apiClient.put<{ profileVersion: number; cargosActivos: string[]; updatedAt: string }>(
        "/me/profile/roles",
        { cargosActivos: roles },
      ),
    onSuccess: () => {
      navigate("/onboarding/3");
    },
    onError: (error: Error) => {
      if (error instanceof ApiError && error.status === 400) {
        setSaveError("Algunos cargos no son válidos. Revisa la lista.");
      } else {
        setSaveError("No se pudieron guardar los cargos. Intenta de nuevo.");
      }
    },
  });

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    setPhase("polling");
    pollStartRef.current = Date.now();

    pollTimerRef.current = setInterval(async () => {
      // Check timeout
      if (Date.now() - pollStartRef.current > POLL_TIMEOUT) {
        stopPolling();
        setErrorMessage("El resumen está tardando más de lo esperado.");
        setPhase("error");
        return;
      }

      try {
        const profile = await apiClient.get<ProfileResponse>("/me/profile");
        if (!profile.resumenGenerating) {
          stopPolling();
          // Retry suggest
          suggestMutation.mutate();
        }
      } catch {
        // Ignore polling errors, keep trying
      }
    }, POLL_INTERVAL);
  }, [stopPolling, suggestMutation]);

  // Initial trigger
  useEffect(() => {
    suggestMutation.mutate();
    return () => stopPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleRole = (role: string) => {
    setSelectedRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role],
    );
  };

  const addCustomRole = () => {
    const trimmed = customRole.trim();
    if (!trimmed || trimmed.length > MAX_ROLE_LENGTH) return;
    if (selectedRoles.length >= MAX_ROLES) return;
    if (selectedRoles.includes(trimmed)) return;
    setSelectedRoles((prev) => [...prev, trimmed]);
    setCustomRole("");
  };

  const handleConfirm = () => {
    setSaveError(null);
    saveRolesMutation.mutate(selectedRoles);
  };

  const handleRetry = () => {
    setPhase("loading");
    setErrorMessage("");
    suggestMutation.mutate();
  };

  // --- Loading ---
  if (phase === "loading" || suggestMutation.isPending) {
    return (
      <div className="flex flex-col items-center gap-4 py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-300 border-t-primary-600" />
        <p className="text-sm text-gray-600">Generando sugerencias de cargos...</p>
      </div>
    );
  }

  // --- Polling ---
  if (phase === "polling") {
    return (
      <div className="flex flex-col items-center gap-4 py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-300 border-t-primary-600" />
        <p className="text-sm text-gray-600">
          Tu resumen se está generando. Esperando...
        </p>
      </div>
    );
  }

  // --- Error ---
  if (phase === "error") {
    return (
      <ErrorState
        message={errorMessage}
        description="Puedes reintentar manualmente."
        onRetry={handleRetry}
      />
    );
  }

  // --- Selecting roles ---
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-gray-800">Paso 2: Cargos objetivo</h2>
      <p className="text-sm text-gray-600">
        Selecciona los cargos que te interesan o agrega los tuyos.
      </p>

      {/* Suggestions */}
      <div className="flex flex-wrap gap-2">
        {suggestions.map((role) => (
          <button
            key={role}
            type="button"
            onClick={() => toggleRole(role)}
            disabled={!selectedRoles.includes(role) && selectedRoles.length >= MAX_ROLES}
            className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
              selectedRoles.includes(role)
                ? "border-primary-400 bg-primary-50 text-primary-700"
                : "border-gray-200 text-gray-600 hover:border-primary-200"
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            {role}
          </button>
        ))}
      </div>

      {/* Custom role input */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={customRole}
          onChange={(e) => setCustomRole(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addCustomRole();
            }
          }}
          maxLength={MAX_ROLE_LENGTH}
          placeholder="Agregar cargo personalizado"
          className="flex-1 rounded-md border border-gray-200 px-3 py-2 text-sm focus:border-primary-400 focus:outline-none"
        />
        <button
          type="button"
          onClick={addCustomRole}
          disabled={
            !customRole.trim() ||
            customRole.trim().length > MAX_ROLE_LENGTH ||
            selectedRoles.length >= MAX_ROLES
          }
          className="rounded-md bg-gray-100 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Agregar
        </button>
      </div>

      {/* Selected count */}
      <p className="text-xs text-gray-400">
        {selectedRoles.length} de {MAX_ROLES} cargos seleccionados
      </p>

      {/* Selected tags */}
      {selectedRoles.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {selectedRoles.map((role) => (
            <span
              key={role}
              className="inline-flex items-center gap-1 rounded-full bg-primary-100 px-2.5 py-1 text-xs text-primary-700"
            >
              {role}
              <button
                type="button"
                onClick={() => toggleRole(role)}
                className="text-primary-400 hover:text-primary-600"
                aria-label={`Quitar ${role}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {saveError && (
        <div className="rounded-md border border-error/30 bg-error/5 px-4 py-3 text-sm text-error-dark">
          {saveError}
        </div>
      )}

      <button
        type="button"
        onClick={handleConfirm}
        disabled={saveRolesMutation.isPending}
        className="rounded-md bg-primary-500 px-6 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {saveRolesMutation.isPending ? "Guardando..." : "Confirmar cargos"}
      </button>
    </div>
  );
}
