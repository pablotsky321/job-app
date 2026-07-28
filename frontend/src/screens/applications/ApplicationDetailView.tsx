import { useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useVacancyDetail } from "@/api/queries/useVacancyDetail";
import { useEntries, type EntryResponse } from "@/api/queries/useEntries";
import { useCreateEntry } from "@/api/mutations/useCreateEntry";
import { useAnswerEntry } from "@/api/mutations/useAnswerEntry";
import { ApiError } from "@/api/client";
import { CVAtsPanel } from "@/components/CVAtsPanel";
import { PlainText } from "@/components/PlainText";
import { ErrorState } from "@/components/ErrorState";
import { Toast, ToastContainer } from "@/components/ui/toast";
import { cn } from "@/lib/cn";

/* ──────────────────────────────────────────────────────────────
   ApplicationDetailView — Requirement 10 (subtasks 10.2–10.4):
   vacancy info + vertical timeline of entries + CV_ATS_Panel +
   entry creation form + AI answer action.
   ────────────────────────────────────────────────────────────── */

interface ToastItem {
  id: string;
  title?: string;
  description?: string;
  variant: "success" | "error" | "default" | "warning";
}

export function ApplicationDetailView() {
  const { companyId = "", vacancyId = "" } = useParams<{
    companyId: string;
    vacancyId: string;
  }>();

  const {
    data: vacancy,
    isNotFound: vacancyNotFound,
    isError: vacancyError,
    isLoading: vacancyLoading,
    refetch: refetchVacancy,
  } = useVacancyDetail(companyId, vacancyId);

  const {
    data: entries,
    isNotFound: entriesNotFound,
    isError: entriesError,
    isLoading: entriesLoading,
    refetch: refetchEntries,
  } = useEntries(companyId, vacancyId);

  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [formContent, setFormContent] = useState("");
  const [formTipo, setFormTipo] = useState<EntryResponse["tipo"]>("nota_entrevista");
  const [formError, setFormError] = useState<string | null>(null);
  const [answeringEntryId, setAnsweringEntryId] = useState<string | null>(null);

  const createEntryMutation = useCreateEntry();
  const answerEntryMutation = useAnswerEntry();

  const addToast = useCallback((toast: Omit<ToastItem, "id">) => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { ...toast, id }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Count existing nota_entrevista entries for round numbering in "Continuar proceso"
  const notaEntrevistaCount = entries
    ? entries.filter((e) => e.tipo === "nota_entrevista").length
    : 0;

  const handleOpenContinuarProceso = useCallback(() => {
    const nextRound = notaEntrevistaCount + 1;
    setFormTipo("nota_entrevista");
    setFormContent(`Ronda ${nextRound}: `);
    setFormError(null);
    setShowForm(true);
  }, [notaEntrevistaCount]);

  const handleOpenAddEntry = useCallback(() => {
    setFormTipo("nota_entrevista");
    setFormContent("");
    setFormError(null);
    setShowForm(true);
  }, []);

  const handleSubmitEntry = useCallback(async () => {
    setFormError(null);
    try {
      await createEntryMutation.mutateAsync({
        companyId,
        vacancyId,
        tipo: formTipo,
        contenido: formContent,
      });
      // Success: close form, clear field
      setShowForm(false);
      setFormContent("");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 400) {
          // Show error without closing or discarding content
          const detail =
            typeof err.body === "object" && err.body !== null && "detail" in err.body
              ? String((err.body as { detail?: string }).detail)
              : "Error de validación";
          setFormError(detail);
        } else if (err.status === 404) {
          // Close form with message
          setShowForm(false);
          setFormContent("");
          addToast({
            variant: "error",
            title: "La postulación ya no existe",
          });
        } else {
          setFormError("Ocurrió un error inesperado. Intenta de nuevo.");
        }
      } else {
        setFormError("Error de conexión. Intenta de nuevo.");
      }
    }
  }, [createEntryMutation, companyId, vacancyId, formTipo, formContent, addToast]);

  const handleAnswerEntry = useCallback(
    async (entryId: string) => {
      setAnsweringEntryId(entryId);
      try {
        await answerEntryMutation.mutateAsync({
          companyId,
          vacancyId,
          entryId,
        });
      } catch {
        addToast({
          variant: "error",
          title: "Error al obtener respuesta de IA",
          description: "No se pudo generar la respuesta. Intenta de nuevo.",
        });
      }
      setAnsweringEntryId(null);
    },
    [answerEntryMutation, companyId, vacancyId, addToast],
  );

  // Loading
  if (vacancyLoading || entriesLoading) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-6">
        <p className="text-sm text-gray-500">Cargando postulación…</p>
      </div>
    );
  }

  // 404
  if (vacancyNotFound || entriesNotFound) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-6">
        <ErrorState
          message="Postulación no encontrada"
          description="Esta postulación no existe o fue eliminada."
        />
      </div>
    );
  }

  // Other errors
  if (vacancyError || entriesError) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-6">
        <ErrorState
          message="Error al cargar la postulación"
          description="Ocurrió un problema. Intenta de nuevo."
          onRetry={() => {
            refetchVacancy();
            refetchEntries();
          }}
        />
      </div>
    );
  }

  if (!vacancy) return null;

  const isFormValid = formContent.trim().length >= 1 && formContent.length <= 5000;

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      {/* Vacancy header info */}
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-gray-900">{vacancy.titulo}</h1>
        <p className="text-sm text-gray-600">
          {vacancy.empresa} · {vacancy.ubicacion} · {vacancy.modalidad}
        </p>
        {vacancy.descripcion && (
          <div className="mt-3">
            <PlainText as="p" className="text-sm text-gray-700">
              {vacancy.descripcion}
            </PlainText>
          </div>
        )}
        <a
          href={vacancy.urlPublicacion}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-block text-sm text-primary-600 underline hover:text-primary-800"
        >
          Ver publicación original
        </a>
      </div>

      {/* CV-ATS Panel (10.5) */}
      <CVAtsPanel
        cvAtsTexto={vacancy.cvAtsTexto}
        companyId={companyId}
        vacancyId={vacancyId}
        className="mb-6"
      />

      {/* Actions: Add entry + Continuar proceso */}
      <div className="flex items-center gap-2 mb-6">
        <button
          type="button"
          onClick={handleOpenAddEntry}
          className="rounded-md border border-primary-500 px-3 py-1.5 text-xs font-medium text-primary-600 hover:bg-primary-50 transition-colors"
        >
          Agregar entrada
        </button>
        <button
          type="button"
          onClick={handleOpenContinuarProceso}
          className="rounded-md bg-primary-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-600 transition-colors"
        >
          Continuar proceso
        </button>
      </div>

      {/* Entry creation form (10.3) */}
      {showForm && (
        <div className="mb-6 rounded-md border border-primary-100 p-4">
          <div className="mb-3">
            <label htmlFor="entry-tipo" className="block text-xs font-medium text-gray-700 mb-1">
              Tipo
            </label>
            <select
              id="entry-tipo"
              value={formTipo}
              onChange={(e) => setFormTipo(e.target.value as EntryResponse["tipo"])}
              className="w-full rounded-md border border-gray-200 px-3 py-1.5 text-sm text-gray-800"
            >
              <option value="nota_entrevista">Nota de entrevista</option>
              <option value="preguntas">Preguntas</option>
              <option value="observacion">Observación</option>
            </select>
          </div>

          <div className="mb-3">
            <label htmlFor="entry-contenido" className="block text-xs font-medium text-gray-700 mb-1">
              Contenido
            </label>
            <textarea
              id="entry-contenido"
              value={formContent}
              onChange={(e) => setFormContent(e.target.value)}
              rows={4}
              maxLength={5000}
              className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-800 resize-y"
              placeholder="Escribe el contenido de la entrada…"
            />
            <p className="mt-1 text-xs text-gray-400">
              {formContent.length}/5000 caracteres
            </p>
          </div>

          {formError && (
            <p className="mb-3 text-xs text-error">{formError}</p>
          )}

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleSubmitEntry}
              disabled={!isFormValid || createEntryMutation.isPending}
              className="rounded-md bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50 transition-colors"
            >
              {createEntryMutation.isPending ? "Guardando…" : "Guardar entrada"}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-md border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* Timeline (10.2) */}
      <section>
        <h2 className="text-sm font-semibold text-gray-700 mb-4">
          Historial de entradas
        </h2>
        {entries && entries.length > 0 ? (
          <EntryTimeline
            entries={entries}
            answeringEntryId={answeringEntryId}
            onAnswer={handleAnswerEntry}
          />
        ) : (
          <p className="text-sm text-gray-500">
            No hay entradas todavía. Agrega una nota o continúa el proceso.
          </p>
        )}
      </section>

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

/* ── Entry Timeline ── */

function EntryTimeline({
  entries,
  answeringEntryId,
  onAnswer,
}: {
  entries: EntryResponse[];
  answeringEntryId: string | null;
  onAnswer: (entryId: string) => void;
}) {
  // Compute round numbers for nota_entrevista entries
  let notaRoundCounter = 0;
  const entriesWithRound = entries.map((entry) => {
    if (entry.tipo === "nota_entrevista") {
      notaRoundCounter++;
      return { ...entry, roundNumber: notaRoundCounter };
    }
    return { ...entry, roundNumber: null };
  });

  return (
    <div className="relative">
      {/* Vertical line */}
      <div className="absolute left-3 top-0 bottom-0 w-px bg-gray-200" />

      <div className="flex flex-col gap-4">
        {entriesWithRound.map((entry) => (
          <EntryTimelineItem
            key={entry.entryId}
            entry={entry}
            roundNumber={entry.roundNumber}
            isAnswering={answeringEntryId === entry.entryId}
            onAnswer={onAnswer}
          />
        ))}
      </div>
    </div>
  );
}

/* ── Single Timeline Item ── */

const tipoLabels: Record<EntryResponse["tipo"], string> = {
  nota_entrevista: "Nota de entrevista",
  preguntas: "Preguntas",
  respuesta_ia: "Respuesta IA",
  observacion: "Observación",
};

const tipoMarkerColors: Record<EntryResponse["tipo"], string> = {
  nota_entrevista: "bg-primary-500",
  preguntas: "bg-warning",
  respuesta_ia: "bg-success",
  observacion: "bg-gray-400",
};

function EntryTimelineItem({
  entry,
  roundNumber,
  isAnswering,
  onAnswer,
}: {
  entry: EntryResponse;
  roundNumber: number | null;
  isAnswering: boolean;
  onAnswer: (entryId: string) => void;
}) {
  const formattedDate = formatEntryDate(entry.creadoAt);

  return (
    <div className="relative flex gap-3 pl-7">
      {/* Marker dot */}
      <div
        className={cn(
          "absolute left-1.5 top-1 h-3 w-3 rounded-full border-2 border-white",
          tipoMarkerColors[entry.tipo],
        )}
      />

      <div className="flex-1 min-w-0">
        {/* Header: type label + round number + date */}
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="font-medium text-gray-700">
            {tipoLabels[entry.tipo]}
            {roundNumber !== null && (
              <span className="ml-1 text-primary-600">
                — Ronda {roundNumber}
              </span>
            )}
          </span>
          <time dateTime={entry.creadoAt}>{formattedDate}</time>
        </div>

        {/* Content */}
        <PlainText as="p" className="mt-1 text-sm text-gray-800">
          {entry.contenido}
        </PlainText>

        {/* AI Answer button for preguntas entries (10.4) */}
        {entry.tipo === "preguntas" && (
          <button
            type="button"
            onClick={() => onAnswer(entry.entryId)}
            disabled={isAnswering}
            className="mt-2 rounded-md border border-primary-500 px-2.5 py-1 text-xs font-medium text-primary-600 hover:bg-primary-50 disabled:opacity-50 transition-colors"
          >
            {isAnswering ? "Generando respuesta…" : "Responder con IA"}
          </button>
        )}
      </div>
    </div>
  );
}

function formatEntryDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("es", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}
