import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiClient, ApiError } from "@/api/client";
import { companiesKey } from "@/api/queryKeys";
import { ErrorState } from "@/components/ErrorState";
import {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";
import type { CompaniesListResponse, CompanyListItem } from "@/api/types";

interface CompanySelection {
  companyId: string;
  nombre: string;
  status: "pending" | "confirmed" | "error";
  errorMessage?: string;
}

export function Step3Companies() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [selections, setSelections] = useState<Map<string, CompanySelection>>(new Map());

  // Load companies catalog
  const companiesQuery = useQuery({
    queryKey: companiesKey(),
    queryFn: () => apiClient.get<CompaniesListResponse>("/companies?limit=100&offset=0"),
  });

  const companies = companiesQuery.data?.companies ?? [];

  const filteredCompanies = useMemo(() => {
    if (!search.trim()) return companies;
    const lower = search.toLowerCase();
    return companies.filter((c) => c.nombre.toLowerCase().includes(lower));
  }, [companies, search]);

  const confirmedCount = useMemo(
    () => Array.from(selections.values()).filter((s) => s.status === "confirmed").length,
    [selections],
  );

  const isSelected = (companyId: string) => selections.has(companyId);

  const handleSelect = async (company: CompanyListItem) => {
    if (isSelected(company.companyId)) {
      // Deselect: PUT with activa=false
      handleDeselect(company.companyId);
      return;
    }

    // Select: POST /me/companies/{companyId}
    setSelections((prev) => {
      const next = new Map(prev);
      next.set(company.companyId, {
        companyId: company.companyId,
        nombre: company.nombre,
        status: "pending",
      });
      return next;
    });

    try {
      await apiClient.post(`/me/companies/${company.companyId}`);
      setSelections((prev) => {
        const next = new Map(prev);
        const item = next.get(company.companyId);
        if (item) next.set(company.companyId, { ...item, status: "confirmed" });
        return next;
      });
    } catch (error) {
      const message =
        error instanceof ApiError
          ? `Error ${error.status}: ${error.message}`
          : "Error de conexión";
      setSelections((prev) => {
        const next = new Map(prev);
        const item = next.get(company.companyId);
        if (item) next.set(company.companyId, { ...item, status: "error", errorMessage: message });
        return next;
      });
    }
  };

  const handleDeselect = async (companyId: string) => {
    try {
      await apiClient.put(`/me/companies/${companyId}`, { activa: false });
      setSelections((prev) => {
        const next = new Map(prev);
        next.delete(companyId);
        return next;
      });
    } catch (error) {
      const message =
        error instanceof ApiError
          ? `Error ${error.status}: ${error.message}`
          : "Error al deseleccionar";
      setSelections((prev) => {
        const next = new Map(prev);
        const item = next.get(companyId);
        if (item) next.set(companyId, { ...item, status: "error", errorMessage: message });
        return next;
      });
    }
  };

  const handleAdvance = () => {
    navigate("/onboarding/4");
  };

  // --- Loading ---
  if (companiesQuery.isLoading) {
    return (
      <div className="flex flex-col items-center gap-4 py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-300 border-t-primary-600" />
        <p className="text-sm text-gray-600">Cargando catálogo de empresas...</p>
      </div>
    );
  }

  // --- Error loading companies ---
  if (companiesQuery.isError) {
    return (
      <ErrorState
        message="No se pudo cargar el catálogo de empresas"
        description="Verifica tu conexión e intenta de nuevo."
        onRetry={() => companiesQuery.refetch()}
      />
    );
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-gray-800">Paso 3: Empresas</h2>
      <p className="text-sm text-gray-600">
        Selecciona las empresas que quieres monitorear. Necesitas al menos una.
      </p>

      {/* Selected companies chips */}
      {selections.size > 0 && (
        <div className="flex flex-wrap gap-2">
          {Array.from(selections.values()).map((sel) => (
            <span
              key={sel.companyId}
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs ${
                sel.status === "confirmed"
                  ? "bg-success/10 text-success-dark"
                  : sel.status === "error"
                    ? "bg-error/10 text-error-dark"
                    : "bg-gray-100 text-gray-600"
              }`}
            >
              {sel.nombre}
              {sel.status === "pending" && (
                <span className="ml-1 inline-block h-3 w-3 animate-spin rounded-full border border-gray-400 border-t-transparent" />
              )}
              {sel.status === "error" && (
                <span className="ml-1 text-error" title={sel.errorMessage}>
                  ⚠
                </span>
              )}
              {sel.status === "confirmed" && <span className="ml-1 text-success">✓</span>}
            </span>
          ))}
        </div>
      )}

      {/* Command/Combobox */}
      <Command className="border border-gray-200">
        <CommandInput
          placeholder="Buscar empresa..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <CommandList>
          {filteredCompanies.length === 0 ? (
            <CommandEmpty>No se encontraron empresas.</CommandEmpty>
          ) : (
            <CommandGroup>
              {filteredCompanies.map((company) => {
                const selected = isSelected(company.companyId);
                return (
                  <CommandItem
                    key={company.companyId}
                    selected={selected}
                    onSelect={() => handleSelect(company)}
                  >
                    <span className="flex-1">{company.nombre}</span>
                    <span className="text-xs text-gray-400">{company.plataforma}</span>
                    {selected && <span className="ml-2 text-primary-500">✓</span>}
                  </CommandItem>
                );
              })}
            </CommandGroup>
          )}
        </CommandList>
      </Command>

      <button
        type="button"
        onClick={handleAdvance}
        disabled={confirmedCount < 1}
        className="rounded-md bg-primary-500 px-6 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Continuar
      </button>
    </div>
  );
}
