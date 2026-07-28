import { useState, useCallback } from "react";
import { buildCvAtsFileName, buildCvAtsBlob } from "@/lib/cvAtsBlobBuilder";
import { cn } from "@/lib/cn";

/* ──────────────────────────────────────────────────────────────
   CV_ATS_Panel — Requirement 11: renders cvAtsTexto in font-mono,
   exposes "copiar" (Clipboard API) and "descargar" (Blob + <a>).
   Shows "aún no se ha generado" if cvAtsTexto is empty/null.
   ────────────────────────────────────────────────────────────── */

export interface CVAtsPanelProps {
  cvAtsTexto: string | null;
  companyId: string;
  vacancyId: string;
  className?: string;
}

export function CVAtsPanel({
  cvAtsTexto,
  companyId,
  vacancyId,
  className,
}: CVAtsPanelProps) {
  const [copyFeedback, setCopyFeedback] = useState<"idle" | "success" | "error">("idle");

  const handleCopy = useCallback(async () => {
    if (!cvAtsTexto) return;
    try {
      await navigator.clipboard.writeText(cvAtsTexto);
      setCopyFeedback("success");
      setTimeout(() => setCopyFeedback("idle"), 2000);
    } catch {
      setCopyFeedback("error");
      setTimeout(() => setCopyFeedback("idle"), 3000);
    }
  }, [cvAtsTexto]);

  const handleDownload = useCallback(() => {
    if (!cvAtsTexto) return;
    const blob = buildCvAtsBlob(cvAtsTexto);
    const fileName = buildCvAtsFileName(companyId, vacancyId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [cvAtsTexto, companyId, vacancyId]);

  // Empty state
  if (!cvAtsTexto) {
    return (
      <section className={cn("rounded-md border border-gray-200 p-4", className)}>
        <h2 className="text-sm font-semibold text-gray-700 mb-2">CV-ATS</h2>
        <p className="text-sm text-gray-500">Aún no se ha generado</p>
      </section>
    );
  }

  return (
    <section className={cn("rounded-md border border-gray-200 p-4", className)}>
      <h2 className="text-sm font-semibold text-gray-700 mb-2">CV-ATS</h2>

      {/* Content in font-mono, no extra colors/icons/cards */}
      <pre className="whitespace-pre-wrap font-mono text-xs text-gray-800 mb-4">
        {cvAtsTexto}
      </pre>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleCopy}
          className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors"
        >
          {copyFeedback === "success"
            ? "¡Copiado!"
            : copyFeedback === "error"
              ? "Error al copiar"
              : "Copiar"}
        </button>
        <button
          type="button"
          onClick={handleDownload}
          className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors"
        >
          Descargar
        </button>
      </div>

      {/* Error message for clipboard failure */}
      {copyFeedback === "error" && (
        <p className="mt-2 text-xs text-error">
          No se pudo copiar al portapapeles. Selecciona el texto manualmente.
        </p>
      )}
    </section>
  );
}
