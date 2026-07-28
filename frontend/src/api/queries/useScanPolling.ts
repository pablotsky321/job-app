import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { scanKey } from "@/api/queryKeys";
import { isScanTerminal } from "@/lib/scanPollingExit";

// TODO(dependencia-externa-pendiente): eliminar cuando openapi.json exponga el esquema real
interface ScanJobResponse {
  status: string;
  empresasTotal: number;
  empresasCompletadas: number;
}

export function useScanPolling(jobId: string | null) {
  const startedAtRef = useRef<number | null>(null);
  const [timedOut, setTimedOut] = useState(false);

  const query = useQuery({
    queryKey: scanKey(jobId ?? ""),
    queryFn: () => apiClient.get<ScanJobResponse>(`/scans/${jobId}`),
    enabled: jobId !== null && !timedOut,
    refetchInterval: (query) => {
      if (!startedAtRef.current) startedAtRef.current = Date.now();
      if (Date.now() - startedAtRef.current > 600_000) {
        setTimedOut(true);
        return false;
      }
      const status = query.state.data?.status;
      return isScanTerminal(status ?? "") ? false : 2_000;
    },
    retry: false,
  });

  return { ...query, timedOut };
}
