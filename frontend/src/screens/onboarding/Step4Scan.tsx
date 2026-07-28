import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useScanPolling } from "@/api/queries/useScanPolling";
import { isScanTerminal } from "@/lib/scanPollingExit";
import { ErrorState } from "@/components/ErrorState";

interface StartScanResponse {
  jobId: string;
}

export function Step4Scan() {
  const navigate = useNavigate();
  const [jobId, setJobId] = useState<string | null>(null);

  // Start scan mutation
  const startScanMutation = useMutation({
    mutationFn: () => apiClient.post<StartScanResponse>("/scans"),
    onSuccess: (data) => {
      setJobId(data.jobId);
    },
  });

  // Polling
  const scanQuery = useScanPolling(jobId);
  const scanData = scanQuery.data;
  const status = scanData?.status ?? "";
  const isTerminal = isScanTerminal(status);

  const handleFinish = () => {
    navigate("/vacancies");
  };

  const handleStartScan = () => {
    startScanMutation.mutate();
  };

  // --- Not started yet ---
  if (!jobId && !startScanMutation.isPending && !startScanMutation.isError) {
    // Auto-start on mount
    if (!startScanMutation.isSuccess) {
      startScanMutation.mutate();
    }
  }

  // --- POST error ---
  if (startScanMutation.isError && !jobId) {
    return (
      <ErrorState
        message="No se pudo iniciar el escaneo"
        description="Verifica tu conexión e intenta de nuevo."
        onRetry={handleStartScan}
      />
    );
  }

  // --- Waiting for scan to start ---
  if (startScanMutation.isPending || (!jobId && !startScanMutation.isError)) {
    return (
      <div className="flex flex-col items-center gap-4 py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-300 border-t-primary-600" />
        <p className="text-sm text-gray-600">Iniciando escaneo...</p>
      </div>
    );
  }

  // --- Timed out ---
  if (scanQuery.timedOut) {
    return (
      <div className="flex flex-col items-center gap-6 py-12">
        <div className="rounded-full bg-warning/10 p-4">
          <svg
            className="h-10 w-10 text-warning"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
        </div>
        <h3 className="text-lg font-medium text-gray-800">Tardando más de lo esperado</h3>
        <p className="text-sm text-gray-600">
          El escaneo está tomando más tiempo del habitual. Puedes continuar y revisar los resultados más tarde.
        </p>
        <button
          type="button"
          onClick={handleFinish}
          className="rounded-md bg-primary-500 px-6 py-2 text-sm font-medium text-white hover:bg-primary-600"
        >
          Continuar de todos modos
        </button>
      </div>
    );
  }

  // --- RUNNING ---
  if (!isTerminal) {
    const total = scanData?.empresasTotal ?? 0;
    const completed = scanData?.empresasCompletadas ?? 0;

    return (
      <div className="flex flex-col items-center gap-6 py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-300 border-t-primary-600" />
        <h3 className="text-lg font-medium text-gray-800">Escaneando empresas</h3>
        {total > 0 && (
          <p className="text-sm text-gray-600">
            {completed} de {total} empresas revisadas
          </p>
        )}
      </div>
    );
  }

  // --- Terminal states ---
  if (status === "DONE") {
    return (
      <div className="flex flex-col items-center gap-6 py-12">
        <div className="rounded-full bg-success/10 p-4">
          <svg
            className="h-10 w-10 text-success"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        </div>
        <h3 className="text-lg font-medium text-gray-800">¡Escaneo completado!</h3>
        <p className="text-sm text-gray-600">
          Todas las empresas fueron revisadas correctamente.
        </p>
        <button
          type="button"
          onClick={handleFinish}
          className="rounded-md bg-primary-500 px-6 py-2 text-sm font-medium text-white hover:bg-primary-600"
        >
          Ver vacantes
        </button>
      </div>
    );
  }

  if (status === "PARCIAL") {
    return (
      <div className="flex flex-col items-center gap-6 py-12">
        <div className="rounded-full bg-warning/10 p-4">
          <svg
            className="h-10 w-10 text-warning"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        </div>
        <h3 className="text-lg font-medium text-gray-800">Escaneo parcial</h3>
        <p className="text-sm text-gray-600">
          Algunas empresas no pudieron ser revisadas completamente, pero ya tienes resultados disponibles.
        </p>
        <button
          type="button"
          onClick={handleFinish}
          className="rounded-md bg-primary-500 px-6 py-2 text-sm font-medium text-white hover:bg-primary-600"
        >
          Ver vacantes
        </button>
      </div>
    );
  }

  // FAILED
  return (
    <div className="flex flex-col items-center gap-6 py-12">
      <div className="rounded-full bg-error/10 p-4">
        <svg
          className="h-10 w-10 text-error"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="10" />
          <path d="m15 9-6 6" />
          <path d="m9 9 6 6" />
        </svg>
      </div>
      <h3 className="text-lg font-medium text-gray-800">Escaneo fallido</h3>
      <p className="text-sm text-gray-600">
        El escaneo no pudo completarse. Puedes continuar y reintentarlo más adelante desde Fuentes.
      </p>
      <button
        type="button"
        onClick={handleFinish}
        className="rounded-md bg-primary-500 px-6 py-2 text-sm font-medium text-white hover:bg-primary-600"
      >
        Continuar
      </button>
    </div>
  );
}
