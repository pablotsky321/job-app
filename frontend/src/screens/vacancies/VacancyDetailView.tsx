import { useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useQueryClient } from "@tanstack/react-query";
import {
  useVacancyDetail,
  type VacancyDetailResponse,
} from "@/api/queries/useVacancyDetail";
import { vacancyKey } from "@/api/queryKeys";
import { useApplyVacancy } from "@/api/mutations/useApplyVacancy";
import { useGenerateCvAts } from "@/api/mutations/useGenerateCvAts";
import { PlainText } from "@/components/PlainText";
import { ErrorState } from "@/components/ErrorState";
import { ScoreBadge } from "@/components/ScoreBadge";
import { Toast, ToastContainer } from "@/components/ui/toast";
import { cn } from "@/lib/cn";

/* ──────────────────────────────────────────────────────────────
   VacancyDetailView — Requirement 9: full vacancy detail with
   score breakdown (two columns) and "Presentarse" flow.
   ────────────────────────────────────────────────────────────── */

interface ToastItem {
  id: string;
  title?: string;
  description?: string;
  variant: "success" | "error" | "default" | "warning";
}

export function VacancyDetailView() {
  const { companyId = "", vacancyId = "" } = useParams<{
    companyId: string;
    vacancyId: string;
  }>();
  const queryClient = useQueryClient();
  const { data, isNotFound, isError, isLoading, refetch } = useVacancyDetail(
    companyId,
    vacancyId,
  );

  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [showPresentarse, setShowPresentarse] = useState(false);
  const [cvRetryPending, setCvRetryPending] = useState(false);
  const [applyingAction, setApplyingAction] = useState<string | null>(null);

  const applyMutation = useApplyVacancy();
  const cvMutation = useGenerateCvAts();

  const addToast = useCallback(
    (toast: Omit<ToastItem, "id">) => {
      const id = crypto.randomUUID();
      setToasts((prev) => [...prev, { ...toast, id }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 5000);
    },
    [],
  );

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const invalidateDetail = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: vacancyKey(companyId, vacancyId) });
  }, [queryClient, companyId, vacancyId]);

  const handleApplyAndCv = useCallback(async () => {
    setApplyingAction("cv");
    try {
      await applyMutation.mutateAsync({ companyId, vacancyId });
    } catch {
      addToast({
        variant: "error",
        title: "Error al presentarse",
        description: "No se pudo registrar la aplicación. Intenta de nuevo.",
      });
      setApplyingAction(null);
      return;
    }

    try {
      await cvMutation.mutateAsync({ companyId, vacancyId });
      invalidateDetail();
      addToast({
        variant: "success",
        title: "CV-ATS generado",
        description: "Tu hoja de vida personalizada está lista.",
      });
    } catch {
      setCvRetryPending(true);
      addToast({
        variant: "error",
        title: "Error al generar CV-ATS",
        description:
          "La aplicación se registró pero no se pudo generar la hoja de vida. Puedes reintentar.",
      });
    }
    setApplyingAction(null);
  }, [applyMutation, cvMutation, companyId, vacancyId, addToast, invalidateDetail]);

  const handleRetryCv = useCallback(async () => {
    setApplyingAction("cv-retry");
    try {
      await cvMutation.mutateAsync({ companyId, vacancyId });
      setCvRetryPending(false);
      invalidateDetail();
      addToast({
        variant: "success",
        title: "CV-ATS generado",
        description: "Tu hoja de vida personalizada está lista.",
      });
    } catch {
      addToast({
        variant: "error",
        title: "Error al generar CV-ATS",
        description: "No se pudo generar la hoja de vida. Intenta de nuevo.",
      });
    }
    setApplyingAction(null);
  }, [cvMutation, companyId, vacancyId, addToast, invalidateDetail]);

  const handleApplyAndQuestions = useCallback(async () => {
    setApplyingAction("questions");
    try {
      await applyMutation.mutateAsync({ companyId, vacancyId });
      invalidateDetail();
      // TODO(task-10.3): abrir formulario de entradas aquí
      addToast({
        variant: "success",
        title: "Aplicación registrada",
        description: "Puedes agregar preguntas desde el detalle de postulación.",
      });
    } catch {
      addToast({
        variant: "error",
        title: "Error al presentarse",
        description: "No se pudo registrar la aplicación. Intenta de nuevo.",
      });
    }
    setApplyingAction(null);
  }, [applyMutation, companyId, vacancyId, addToast, invalidateDetail]);

  const handleApplyOnly = useCallback(async () => {
    setApplyingAction("save");
    try {
      await applyMutation.mutateAsync({ companyId, vacancyId });
      invalidateDetail();
      addToast({
        variant: "success",
        title: "Aplicación guardada",
        description: "La vacante se marcó como aplicada.",
      });
    } catch {
      addToast({
        variant: "error",
        title: "Error al presentarse",
        description: "No se pudo registrar la aplicación. Intenta de nuevo.",
      });
    }
    setApplyingAction(null);
  }, [applyMutation, companyId, vacancyId, addToast, invalidateDetail]);

  const handleCopyLink = useCallback(
    async (url: string) => {
      try {
        await navigator.clipboard.writeText(url);
        addToast({
          variant: "success",
          title: "Link copiado",
        });
      } catch {
        addToast({
          variant: "error",
          title: "No se pudo copiar",
          description: "Copia el link manualmente.",
        });
      }
    },
    [addToast],
  );

  // Loading
  if (isLoading) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-6">
        <p className="text-sm text-gray-500">Cargando vacante…</p>
      </div>
    );
  }

  // 404
  if (isNotFound) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-6">
        <ErrorState
          message="Vacante no encontrada"
          description="Esta vacante no existe o fue eliminada."
        />
      </div>
    );
  }

  // Other errors
  if (isError) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-6">
        <ErrorState
          message="Error al cargar la vacante"
          description="Ocurrió un problema. Intenta de nuevo."
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <VacancyHeader vacancy={data} />
      <ScoreSection vacancy={data} />

      {/* Description */}
      <section className="mt-6">
        <h2 className="text-sm font-semibold text-gray-700 mb-2">
          Descripción
        </h2>
        <PlainText as="div" className="text-sm text-gray-800">
          {data.descripcion}
        </PlainText>
      </section>

      {/* Resumen */}
      {data.resumen && (
        <section className="mt-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Resumen</h2>
          <PlainText as="div" className="text-sm text-gray-800">
            {data.resumen}
          </PlainText>
        </section>
      )}

      {/* Publication link */}
      <section className="mt-4">
        <a
          href={data.urlPublicacion}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-primary-600 underline hover:text-primary-800"
        >
          Ver publicación original
        </a>
      </section>

      {/* Existing CV-ATS (Req 9 AC 5) */}
      {data.cvAtsTexto && (
        <section className="mt-6 rounded-md border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">
            CV-ATS generado
          </h2>
          <pre className="whitespace-pre-wrap font-mono text-xs text-gray-800">
            {data.cvAtsTexto}
          </pre>
        </section>
      )}

      {/* CV retry button */}
      {cvRetryPending && !data.cvAtsTexto && (
        <div className="mt-4">
          <button
            type="button"
            onClick={handleRetryCv}
            disabled={applyingAction === "cv-retry"}
            className="rounded-md bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
          >
            {applyingAction === "cv-retry"
              ? "Generando…"
              : "Reintentar generación de CV-ATS"}
          </button>
        </div>
      )}

      {/* Presentarse flow */}
      <PresentarseSection
        vacancy={data}
        showPresentarse={showPresentarse}
        onReveal={() => setShowPresentarse(true)}
        onGenerateCv={handleApplyAndCv}
        onSaveQuestions={handleApplyAndQuestions}
        onSaveOnly={handleApplyOnly}
        onCopyLink={handleCopyLink}
        applyingAction={applyingAction}
      />

      {/* Toasts */}
      <ToastContainer>
        {toasts.map((t) => (
          <Toast
            key={t.id}
            id={t.id}
            title={t.title}
            description={t.description}
            variant={t.variant}
            onDismiss={dismissToast}
          />
        ))}
      </ToastContainer>
    </div>
  );
}

/* ── Header ── */

function VacancyHeader({ vacancy }: { vacancy: VacancyDetailResponse }) {
  return (
    <div>
      <h1 className="text-lg font-semibold text-gray-900">{vacancy.titulo}</h1>
      <p className="text-sm text-gray-600">
        {vacancy.empresa} · {vacancy.ubicacion} · {vacancy.modalidad}
      </p>
      {vacancy.estado === "cerrada" && (
        <span className="mt-1 inline-block rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600">
          Cerrada
        </span>
      )}
    </div>
  );
}

/* ── Score Section (Req 9 AC 2 / 3) ── */

function ScoreSection({ vacancy }: { vacancy: VacancyDetailResponse }) {
  if (vacancy.score === null) {
    return (
      <section className="mt-6 rounded-md border border-primary-100 p-4 text-center">
        <p className="text-sm text-gray-600">
          El score todavía se está calculando…
        </p>
      </section>
    );
  }

  return (
    <section className="mt-6 rounded-md border border-primary-100 p-4">
      {/* Big score number */}
      <div className="mb-4 text-center">
        <span className="text-4xl font-bold text-gray-900">
          {vacancy.score}
        </span>
        {vacancy.veredicto && (
          <div className="mt-1">
            <ScoreBadge veredicto={vacancy.veredicto} />
          </div>
        )}
      </div>

      {/* Two columns: coincidencias / faltantes */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <h3 className="text-xs font-semibold text-success-dark mb-2">
            Coincidencias
          </h3>
          <ul className="space-y-1">
            {vacancy.coincidencias.map((item, i) => (
              <li key={i} className="text-sm text-gray-700">
                • {item}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-xs font-semibold text-error-dark mb-2">
            Faltantes
          </h3>
          <ul className="space-y-1">
            {vacancy.faltantes.map((item, i) => (
              <li key={i} className="text-sm text-gray-700">
                • {item}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

/* ── Presentarse Section (Req 9 AC 6/7/8/9/10/15) ── */

function PresentarseSection({
  vacancy,
  showPresentarse,
  onReveal,
  onGenerateCv,
  onSaveQuestions,
  onSaveOnly,
  onCopyLink,
  applyingAction,
}: {
  vacancy: VacancyDetailResponse;
  showPresentarse: boolean;
  onReveal: () => void;
  onGenerateCv: () => void;
  onSaveQuestions: () => void;
  onSaveOnly: () => void;
  onCopyLink: (url: string) => void;
  applyingAction: string | null;
}) {
  const isCerrada = vacancy.estado === "cerrada";

  return (
    <section className="mt-6">
      {!showPresentarse && (
        <button
          type="button"
          onClick={onReveal}
          className="w-full rounded-md bg-primary-500 px-4 py-3 text-sm font-semibold text-white hover:bg-primary-600 transition-colors"
        >
          Presentarse
        </button>
      )}

      <AnimatePresence>
        {showPresentarse && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="mt-4 rounded-md border border-gray-200 p-4 space-y-4">
              {/* Publication link + copy */}
              <div className="flex items-center gap-2">
                <a
                  href={vacancy.urlPublicacion}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 truncate text-sm text-primary-600 underline"
                >
                  {vacancy.urlPublicacion}
                </a>
                <button
                  type="button"
                  onClick={() => onCopyLink(vacancy.urlPublicacion)}
                  className="shrink-0 rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                >
                  Copiar
                </button>
              </div>

              {/* Three actions */}
              <div className="flex flex-col gap-2">
                <button
                  type="button"
                  onClick={onGenerateCv}
                  disabled={isCerrada || applyingAction !== null}
                  className={cn(
                    "w-full rounded-md px-4 py-2.5 text-sm font-medium transition-colors",
                    isCerrada
                      ? "bg-gray-100 text-gray-400 cursor-not-allowed"
                      : "bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-50",
                  )}
                >
                  {applyingAction === "cv"
                    ? "Generando…"
                    : "Generar hoja de vida"}
                </button>
                {isCerrada && (
                  <p className="text-xs text-gray-500">
                    La vacante está cerrada — no es posible generar CV-ATS.
                  </p>
                )}

                <button
                  type="button"
                  onClick={onSaveQuestions}
                  disabled={applyingAction !== null}
                  className="w-full rounded-md border border-primary-500 px-4 py-2.5 text-sm font-medium text-primary-600 hover:bg-primary-50 disabled:opacity-50 transition-colors"
                >
                  {applyingAction === "questions"
                    ? "Guardando…"
                    : "Guardar preguntas"}
                </button>

                <button
                  type="button"
                  onClick={onSaveOnly}
                  disabled={applyingAction !== null}
                  className="w-full rounded-md border border-gray-200 px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
                >
                  {applyingAction === "save" ? "Guardando…" : "Guardar"}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
