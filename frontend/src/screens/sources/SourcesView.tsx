import { useState, useRef, useMemo, useCallback, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, ApiError } from "@/api/client";
import { companiesKey, vacanciesKey } from "@/api/queryKeys";
import { useSubscriptions } from "@/api/queries/useSubscriptions";
import { useScanPolling } from "@/api/queries/useScanPolling";
import { useToggleSubscription } from "@/api/mutations/useToggleSubscription";
import { useAddCompany } from "@/api/mutations/useAddCompany";
import { classifyScanResult } from "@/lib/scanResultClassifier";
import { isScanTerminal } from "@/lib/scanPollingExit";
import { ErrorState } from "@/components/ErrorState";
import {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";
import type {
  CompaniesListResponse,
  CompanyListItem,
  SubscriptionItem,
} from "@/api/types";
import type { VacancyListItem } from "@/lib/types";

/* ──────────────────────────────────────────────────────────────
   Health Indicator
   - Gray: never scanned (lastScannedAt is null)
   - Red: consecutiveFailures >= 3
   - Green: otherwise
   ────────────────────────────────────────────────────────────── */
function HealthDot({ item }: { item: SubscriptionItem }) {
  const color =
    item.lastScannedAt == null
      ? "bg-gray-400"
      : item.consecutiveFailures >= 3
        ? "bg-error"
        : "bg-success";

  return (
    <span
      className={`inline-block h-3 w-3 shrink-0 rounded-full ${color}`}
      aria-label={
        item.lastScannedAt == null
          ? "Nunca escaneada"
          : item.consecutiveFailures >= 3
            ? "Fallando"
            : "Al día"
      }
    />
  );
}

function formatDate(iso: string | null): string {
  if (!iso) return "nunca";
  const d = new Date(iso);
  return d.toLocaleDateString("es-CO", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/* ──────────────────────────────────────────────────────────────
   SourcesView
   ────────────────────────────────────────────────────────────── */
export function SourcesView() {
  const queryClient = useQueryClient();

  // --- State for scan flow ---
  const [scanJobId, setScanJobId] = useState<string | null>(null);
  const scanStartedAtRef = useRef<string | null>(null);
  const [scanTriggered, setScanTriggered] = useState(false);
  const [scanResultMessage, setScanResultMessage] = useState<{
    type: "success" | "error" | "partial";
    message: string;
  } | null>(null);

  // --- State for add company ---
  const [showAddCompany, setShowAddCompany] = useState(false);
  const [addUrl, setAddUrl] = useState("");
  const [addError, setAddError] = useState<string | null>(null);

  // --- Hooks ---
  const subscriptionsQuery = useSubscriptions();
  const toggleSubscription = useToggleSubscription();
  const addCompanyMutation = useAddCompany();
  const scanPolling = useScanPolling(scanJobId);

  // Companies catalog for Command/Combobox
  const companiesQuery = useQuery({
    queryKey: companiesKey(),
    queryFn: () => apiClient.get<CompaniesListResponse>("/companies?limit=100&offset=0"),
    enabled: showAddCompany,
  });

  const subscriptions = subscriptionsQuery.data?.subscriptions ?? [];
  const subscribedIds = useMemo(
    () => new Set(subscriptions.map((s) => s.companyId)),
    [subscriptions],
  );

  // --- Detect scan completion via useEffect ---
  const scanStatus = scanPolling.data?.status;

  useEffect(() => {
    if (!scanTriggered || !scanStatus || !isScanTerminal(scanStatus)) return;

    // Check status PARCIAL explicitly before classifyScanResult (Requirement 12.12)
    if (scanStatus === "PARCIAL" || scanStatus === "FAILED") {
      setScanResultMessage({
        type: scanStatus === "PARCIAL" ? "partial" : "error",
        message: "El escaneo no se completó para todas tus empresas.",
      });
      setScanTriggered(false);
      subscriptionsQuery.refetch();
      return;
    }

    if (scanStatus === "DONE") {
      // Fetch fresh vacancies to count new ones
      apiClient
        .get<VacancyListItem[]>("/me/vacancies?estado=activas")
        .then((allVacancies) => {
          const startedAt = scanStartedAtRef.current;
          const newCount = startedAt
            ? allVacancies.filter((v) => v.firstSeenAt >= startedAt).length
            : 0;

          const outcome = classifyScanResult(scanStatus, newCount);

          if (outcome === "nuevas_encontradas") {
            setScanResultMessage({
              type: "success",
              message: `Se encontraron ${newCount} vacante${newCount === 1 ? "" : "s"} nueva${newCount === 1 ? "" : "s"}.`,
            });
          } else {
            setScanResultMessage({
              type: "success",
              message: `Tus ${subscriptions.length} empresas están al día`,
            });
          }
          setScanTriggered(false);
          subscriptionsQuery.refetch();
          queryClient.invalidateQueries({ queryKey: vacanciesKey("activas") });
        })
        .catch(() => {
          setScanResultMessage({
            type: "success",
            message: `Escaneo completado`,
          });
          setScanTriggered(false);
          subscriptionsQuery.refetch();
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanStatus, scanTriggered]);

  // --- Handlers ---
  const handleRetryScan = useCallback(async () => {
    setScanResultMessage(null);
    try {
      const response = await apiClient.post<{ jobId: string }>("/scans");
      scanStartedAtRef.current = new Date().toISOString();
      setScanJobId(response.jobId);
      setScanTriggered(true);
    } catch {
      setScanResultMessage({
        type: "error",
        message: "No se pudo iniciar el escaneo. Intenta de nuevo.",
      });
    }
  }, []);

  const handleDeactivate = useCallback(
    (companyId: string) => {
      toggleSubscription.mutate({ companyId, activa: false });
    },
    [toggleSubscription],
  );

  const handleAddByUrl = async () => {
    if (!addUrl.trim()) return;
    setAddError(null);
    try {
      await addCompanyMutation.mutateAsync({ boardUrl: addUrl.trim() });
      setAddUrl("");
      setShowAddCompany(false);
    } catch (error) {
      if (error instanceof ApiError) {
        setAddError(`Error ${error.status}: ${error.message}`);
      } else {
        setAddError("Error de conexión");
      }
    }
  };

  const handleSubscribeFromCatalog = async (company: CompanyListItem) => {
    if (subscribedIds.has(company.companyId)) return;
    try {
      await apiClient.post(`/me/companies/${company.companyId}`);
      subscriptionsQuery.refetch();
    } catch (error) {
      // Per-company error — don't discard search text
      setAddError(
        error instanceof ApiError
          ? `Error suscribiendo a ${company.nombre}: ${error.message}`
          : `Error suscribiendo a ${company.nombre}`,
      );
    }
  };

  // --- Loading ---
  if (subscriptionsQuery.isLoading) {
    return (
      <div className="flex flex-col items-center gap-4 py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-300 border-t-primary-600" />
        <p className="text-sm text-gray-600">Cargando fuentes...</p>
      </div>
    );
  }

  // --- Error ---
  if (subscriptionsQuery.isError) {
    return (
      <ErrorState
        message="No se pudieron cargar tus fuentes"
        description="Verifica tu conexión e intenta de nuevo."
        onRetry={() => subscriptionsQuery.refetch()}
      />
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">Fuentes</h1>
        <button
          type="button"
          onClick={() => setShowAddCompany(!showAddCompany)}
          className="rounded-md bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600"
        >
          Agregar empresa
        </button>
      </div>

      {/* Scan result message */}
      {scanResultMessage && (
        <div
          className={`rounded-md border p-4 ${
            scanResultMessage.type === "error" || scanResultMessage.type === "partial"
              ? "border-error/30 bg-error/5 text-error-dark"
              : "border-success/30 bg-success/5 text-success-dark"
          }`}
        >
          <p className="text-sm font-medium">{scanResultMessage.message}</p>
          {scanResultMessage.type === "success" && subscriptions.length > 0 && (
            <p className="mt-1 text-xs text-gray-500">
              Última revisión:{" "}
              {formatDate(subscriptions[0]?.lastScannedAt ?? null)}
            </p>
          )}
        </div>
      )}

      {/* Scan in progress */}
      {scanTriggered && scanJobId && !isScanTerminal(scanStatus ?? "") && (
        <div className="rounded-md border border-primary-200 bg-primary-50 p-4">
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary-300 border-t-primary-600" />
            <p className="text-sm text-primary-800">
              Escaneando todas tus empresas activas...
            </p>
          </div>
          {scanPolling.data && (
            <p className="mt-1 text-xs text-primary-600">
              {scanPolling.data.empresasCompletadas} de {scanPolling.data.empresasTotal} empresas
              revisadas
            </p>
          )}
          <p className="mt-2 text-xs text-gray-500">
            Nota: el escaneo revisa todas tus empresas activas, no solo la señalada.
          </p>
        </div>
      )}

      {/* Add company section */}
      {showAddCompany && (
        <div className="space-y-4 rounded-md border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-700">Agregar empresa nueva</h3>

          {/* Add by URL */}
          <div className="flex gap-2">
            <input
              type="url"
              value={addUrl}
              onChange={(e) => setAddUrl(e.target.value)}
              placeholder="URL de la página de empleos (ej: https://boards.greenhouse.io/empresa)"
              className="flex-1 rounded-md border border-gray-200 px-3 py-2 text-sm outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-400"
            />
            <button
              type="button"
              onClick={handleAddByUrl}
              disabled={!addUrl.trim() || addCompanyMutation.isPending}
              className="rounded-md bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {addCompanyMutation.isPending ? "Agregando..." : "Agregar"}
            </button>
          </div>

          {addError && (
            <p className="text-sm text-error">{addError}</p>
          )}

          {/* Command/Combobox to search catalog */}
          <div>
            <p className="mb-2 text-xs text-gray-500">
              O busca en el catálogo existente:
            </p>
            <CatalogSearch
              companies={companiesQuery.data?.companies ?? []}
              subscribedIds={subscribedIds}
              onSelect={handleSubscribeFromCatalog}
              isLoading={companiesQuery.isLoading}
            />
          </div>
        </div>
      )}

      {/* Subscriptions list */}
      {subscriptions.length === 0 ? (
        <div className="py-12 text-center">
          <p className="text-sm text-gray-500">
            No tienes empresas suscritas. Agrega una para empezar a monitorear vacantes.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-gray-100">
          {subscriptions.map((sub) => (
            <SubscriptionRow
              key={sub.companyId}
              item={sub}
              onRetry={handleRetryScan}
              onDeactivate={handleDeactivate}
              scanInProgress={scanTriggered}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────
   SubscriptionRow
   ────────────────────────────────────────────────────────────── */
function SubscriptionRow({
  item,
  onRetry,
  onDeactivate,
  scanInProgress,
}: {
  item: SubscriptionItem;
  onRetry: () => void;
  onDeactivate: (companyId: string) => void;
  scanInProgress: boolean;
}) {
  const isFailing = item.consecutiveFailures >= 3;

  return (
    <li className="flex flex-col gap-2 py-4">
      <div className="flex items-center gap-3">
        <HealthDot item={item} />
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-800">{item.nombre}</p>
          <p className="text-xs text-gray-500">
            Última revisión: {formatDate(item.lastScannedAt ?? null)}
          </p>
        </div>
        <span className="text-xs text-gray-400">{item.plataforma}</span>
      </div>

      {isFailing && (
        <div className="ml-6 rounded-md border border-error/20 bg-error/5 p-3">
          <p className="text-xs text-error-dark">
            No hemos podido revisar {item.nombre} desde el{" "}
            {formatDate(item.lastScannedAt ?? null)}
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={onRetry}
              disabled={scanInProgress}
              className="rounded bg-primary-500 px-3 py-1 text-xs font-medium text-white hover:bg-primary-600 disabled:opacity-50"
            >
              Reintentar
            </button>
            <button
              type="button"
              onClick={() => onDeactivate(item.companyId)}
              className="rounded bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-200"
            >
              Desactivar
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

/* ──────────────────────────────────────────────────────────────
   CatalogSearch — reuses Command/Combobox
   ────────────────────────────────────────────────────────────── */
function CatalogSearch({
  companies,
  subscribedIds,
  onSelect,
  isLoading,
}: {
  companies: CompanyListItem[];
  subscribedIds: Set<string>;
  onSelect: (company: CompanyListItem) => void;
  isLoading: boolean;
}) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search.trim()) return companies;
    const lower = search.toLowerCase();
    return companies.filter((c) => c.nombre.toLowerCase().includes(lower));
  }, [companies, search]);

  if (isLoading) {
    return <p className="text-xs text-gray-500">Cargando catálogo...</p>;
  }

  return (
    <Command className="border border-gray-200">
      <CommandInput
        placeholder="Buscar empresa en catálogo..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <CommandList>
        {filtered.length === 0 ? (
          <CommandEmpty>No se encontraron empresas.</CommandEmpty>
        ) : (
          <CommandGroup>
            {filtered.map((company) => {
              const alreadySubscribed = subscribedIds.has(company.companyId);
              return (
                <CommandItem
                  key={company.companyId}
                  disabled={alreadySubscribed}
                  onSelect={() => onSelect(company)}
                >
                  <span className="flex-1">{company.nombre}</span>
                  <span className="text-xs text-gray-400">{company.plataforma}</span>
                  {alreadySubscribed && (
                    <span className="ml-2 text-xs text-success">Suscrito</span>
                  )}
                </CommandItem>
              );
            })}
          </CommandGroup>
        )}
      </CommandList>
    </Command>
  );
}
