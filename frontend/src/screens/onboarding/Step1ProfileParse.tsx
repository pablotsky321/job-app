import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { motion, AnimatePresence } from "framer-motion";
import { apiClient, ApiError } from "@/api/client";
import { PlainText } from "@/components/PlainText";
import type { PerfilEstructurado } from "@/api/types";

// --- Zod schema for profile editing ---
const experienciaSchema = z.object({
  puesto: z.string().min(1, "Requerido"),
  empresa: z.string().min(1, "Requerido"),
  duracion: z.string().min(1, "Requerido"),
  descripcion: z.string().min(1, "Requerido"),
  tecnologias: z.array(z.string()).optional(),
});

const educacionSchema = z.object({
  titulo: z.string().min(1, "Requerido"),
  institucion: z.string().min(1, "Requerido"),
  ano: z.string().min(1, "Requerido"),
  especializacion: z.string().nullable().optional(),
});

const proyectoSchema = z.object({
  nombre: z.string().min(1, "Requerido"),
  descripcion: z.string().min(1, "Requerido"),
  tecnologias: z.array(z.string()).optional(),
  url: z.string().nullable().optional(),
});

const certificacionSchema = z.object({
  nombre: z.string().min(1, "Requerido"),
  emisor: z.string().min(1, "Requerido"),
  ano: z.string().min(1, "Requerido"),
});

const profileSchema = z.object({
  experiencia: z.array(experienciaSchema).optional(),
  educacion: z.array(educacionSchema).optional(),
  proyectos: z.array(proyectoSchema).optional(),
  certificaciones: z.array(certificacionSchema).optional(),
  skills: z.array(z.string().min(1)).min(1, "Al menos un skill requerido"),
  lenguajes: z.array(z.string()).optional(),
});

type ProfileFormValues = z.infer<typeof profileSchema>;

// --- Sections to reveal sequentially ---
type SectionKey = keyof PerfilEstructurado;
const SECTION_LABELS: Record<SectionKey, string> = {
  experiencia: "Experiencia Laboral",
  educacion: "Educación",
  proyectos: "Proyectos",
  certificaciones: "Certificaciones",
  skills: "Skills",
  lenguajes: "Idiomas",
};

const SECTION_ORDER: SectionKey[] = [
  "experiencia",
  "educacion",
  "proyectos",
  "certificaciones",
  "skills",
  "lenguajes",
];

function isNonEmpty(value: unknown): boolean {
  if (value == null) return false;
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

interface Step1ProfileParseProps {
  initialProfile?: PerfilEstructurado;
  onSaveSuccess?: () => void;
}

export function Step1ProfileParse({ initialProfile, onSaveSuccess }: Step1ProfileParseProps = {}) {
  const navigate = useNavigate();
  const [cvText, setCvText] = useState("");
  const [parsedProfile, setParsedProfile] = useState<PerfilEstructurado | null>(initialProfile ?? null);
  const [revealedCount, setRevealedCount] = useState(0);
  // When initialProfile is provided, skip "input"/"split" phases and go directly to "edit"
  const [phase, setPhase] = useState<"input" | "split" | "edit">(
    initialProfile ? "edit" : "input"
  );
  const [parseError, setParseError] = useState<{ type: "size" | "other"; message: string } | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Parse CV mutation
  const parseMutation = useMutation({
    mutationFn: (text: string) =>
      apiClient.post<PerfilEstructurado>("/me/profile/parse", { cvText: text }),
    onSuccess: (data) => {
      setParseError(null);
      setParsedProfile(data);
      setPhase("split");
      // Start sequential reveal
      const nonEmptySections = SECTION_ORDER.filter((key) => isNonEmpty(data[key]));
      let count = 0;
      const revealNext = () => {
        if (count < nonEmptySections.length) {
          count++;
          setRevealedCount(count);
          setTimeout(revealNext, 400);
        } else {
          // All sections revealed — switch to edit mode
          setTimeout(() => setPhase("edit"), 300);
        }
      };
      revealNext();
    },
    onError: (error: Error) => {
      if (error instanceof ApiError) {
        if (error.status === 413) {
          setParseError({ type: "size", message: "El CV excede el tamaño máximo permitido (50 KB)." });
          setPhase("input");
        } else {
          setParseError({ type: "other", message: "Error al procesar el CV. Intenta de nuevo." });
        }
      } else {
        setParseError({ type: "other", message: "Error de conexión. Intenta de nuevo." });
      }
    },
  });

  // Save profile mutation
  const saveMutation = useMutation({
    mutationFn: (profile: PerfilEstructurado) =>
      apiClient.put<{ profileVersion: number; updatedAt: string }>("/me/profile", {
        perfilEstructurado: profile,
      }),
    onSuccess: () => {
      onSaveSuccess?.() ?? navigate("/onboarding/2");
    },
    onError: () => {
      setSaveError("No se pudo guardar el perfil. Intenta de nuevo.");
    },
  });

  // RHF form — initialized when parsedProfile is set
  const form = useForm<ProfileFormValues>({
    values: parsedProfile ?? undefined,
    mode: "onChange",
  });

  const handleParse = () => {
    if (!cvText.trim()) return;
    setParseError(null);
    parseMutation.mutate(cvText);
  };

  const handleSave = form.handleSubmit((data) => {
    setSaveError(null);
    const validated = profileSchema.safeParse(data);
    if (!validated.success) return;
    saveMutation.mutate(validated.data as PerfilEstructurado);
  });

  const nonEmptySections = parsedProfile
    ? SECTION_ORDER.filter((key) => isNonEmpty(parsedProfile[key]))
    : [];

  // --- INPUT PHASE ---
  if (phase === "input") {
    return (
      <div className="flex flex-col items-center gap-6">
        <h2 className="text-xl font-semibold text-gray-800">Paso 1: Tu perfil</h2>
        <p className="text-sm text-gray-600">Pega el texto de tu CV y lo estructuraremos automáticamente.</p>

        {parseError?.type === "size" && (
          <div className="w-full max-w-2xl rounded-md border border-error/30 bg-error/5 px-4 py-3 text-sm text-error-dark">
            {parseError.message}
          </div>
        )}

        <textarea
          value={cvText}
          onChange={(e) => setCvText(e.target.value)}
          placeholder="Pega aquí el texto de tu CV..."
          className="h-64 w-full max-w-2xl resize-y rounded-md border border-gray-200 px-4 py-3 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        />

        <button
          type="button"
          onClick={handleParse}
          disabled={!cvText.trim() || parseMutation.isPending}
          className="rounded-md bg-primary-500 px-6 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {parseMutation.isPending ? "Procesando..." : "Analizar CV"}
        </button>
      </div>
    );
  }

  // --- SPLIT PHASE (reveal) ---
  if (phase === "split") {
    return (
      <div className="flex gap-6">
        {/* Left: raw text */}
        <div className="flex-1 overflow-y-auto rounded-md border border-gray-200 p-4">
          <h3 className="mb-2 text-xs font-medium uppercase text-gray-400">Texto original</h3>
          <PlainText as="div" className="text-sm text-gray-700">
            {cvText}
          </PlainText>
        </div>

        {/* Right: revealed sections */}
        <div className="flex-1 space-y-4">
          <AnimatePresence>
            {nonEmptySections.slice(0, revealedCount).map((key) => (
              <motion.div
                key={key}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className="rounded-md border border-primary-100 bg-primary-50/30 p-4"
              >
                <h4 className="mb-1 text-sm font-semibold text-primary-700">
                  {SECTION_LABELS[key]}
                </h4>
                <SectionPreview sectionKey={key} data={parsedProfile!} />
              </motion.div>
            ))}
          </AnimatePresence>
          {revealedCount < nonEmptySections.length && (
            <div className="flex items-center justify-center py-4">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary-300 border-t-primary-600" />
            </div>
          )}
        </div>
      </div>
    );
  }

  // --- EDIT PHASE ---
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-gray-800">Revisa y edita tu perfil</h2>

      {parseError?.type === "other" && (
        <div className="rounded-md border border-error/30 bg-error/5 px-4 py-3 text-sm text-error-dark">
          {parseError.message}
          <button
            type="button"
            onClick={handleParse}
            className="ml-3 text-sm font-medium text-primary-600 underline"
          >
            Reintentar
          </button>
        </div>
      )}

      {saveError && (
        <div className="rounded-md border border-error/30 bg-error/5 px-4 py-3 text-sm text-error-dark">
          {saveError}
          <button
            type="button"
            onClick={handleSave}
            className="ml-3 text-sm font-medium text-primary-600 underline"
          >
            Reintentar
          </button>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        {/* Skills */}
        <fieldset className="rounded-md border border-gray-200 p-4">
          <legend className="px-2 text-sm font-medium text-gray-700">Skills</legend>
          <input
            {...form.register("skills.0")}
            className="w-full rounded border border-gray-200 px-3 py-2 text-sm"
            placeholder="Skill principal"
          />
          {form.formState.errors.skills && (
            <p className="mt-1 text-xs text-error">{form.formState.errors.skills.message}</p>
          )}
          <p className="mt-2 text-xs text-gray-400">
            Skills detectados: {parsedProfile?.skills?.join(", ")}
          </p>
        </fieldset>

        {/* Experiencia */}
        {parsedProfile?.experiencia && parsedProfile.experiencia.length > 0 && (
          <fieldset className="rounded-md border border-gray-200 p-4">
            <legend className="px-2 text-sm font-medium text-gray-700">Experiencia Laboral</legend>
            {parsedProfile.experiencia.map((_, idx) => (
              <div key={idx} className="mb-3 space-y-2 border-b border-gray-100 pb-3 last:border-0">
                <input
                  {...form.register(`experiencia.${idx}.puesto`)}
                  placeholder="Puesto"
                  className="w-full rounded border border-gray-200 px-3 py-1.5 text-sm"
                />
                <input
                  {...form.register(`experiencia.${idx}.empresa`)}
                  placeholder="Empresa"
                  className="w-full rounded border border-gray-200 px-3 py-1.5 text-sm"
                />
                <input
                  {...form.register(`experiencia.${idx}.duracion`)}
                  placeholder="Duración"
                  className="w-full rounded border border-gray-200 px-3 py-1.5 text-sm"
                />
                <textarea
                  {...form.register(`experiencia.${idx}.descripcion`)}
                  placeholder="Descripción"
                  rows={2}
                  className="w-full rounded border border-gray-200 px-3 py-1.5 text-sm"
                />
              </div>
            ))}
          </fieldset>
        )}

        {/* Educación */}
        {parsedProfile?.educacion && parsedProfile.educacion.length > 0 && (
          <fieldset className="rounded-md border border-gray-200 p-4">
            <legend className="px-2 text-sm font-medium text-gray-700">Educación</legend>
            {parsedProfile.educacion.map((_, idx) => (
              <div key={idx} className="mb-3 space-y-2 border-b border-gray-100 pb-3 last:border-0">
                <input
                  {...form.register(`educacion.${idx}.titulo`)}
                  placeholder="Título"
                  className="w-full rounded border border-gray-200 px-3 py-1.5 text-sm"
                />
                <input
                  {...form.register(`educacion.${idx}.institucion`)}
                  placeholder="Institución"
                  className="w-full rounded border border-gray-200 px-3 py-1.5 text-sm"
                />
                <input
                  {...form.register(`educacion.${idx}.ano`)}
                  placeholder="Año"
                  className="w-full rounded border border-gray-200 px-3 py-1.5 text-sm"
                />
              </div>
            ))}
          </fieldset>
        )}

        {/* Lenguajes */}
        {parsedProfile?.lenguajes && parsedProfile.lenguajes.length > 0 && (
          <fieldset className="rounded-md border border-gray-200 p-4">
            <legend className="px-2 text-sm font-medium text-gray-700">Idiomas</legend>
            {parsedProfile.lenguajes.map((_, idx) => (
              <input
                key={idx}
                {...form.register(`lenguajes.${idx}`)}
                placeholder="Idioma"
                className="mb-2 w-full rounded border border-gray-200 px-3 py-1.5 text-sm"
              />
            ))}
          </fieldset>
        )}

        <button
          type="submit"
          disabled={!form.formState.isValid || saveMutation.isPending}
          className="rounded-md bg-primary-500 px-6 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saveMutation.isPending ? "Guardando..." : "Confirmar perfil"}
        </button>
      </form>
    </div>
  );
}

// --- Helper component for section preview during reveal ---
function SectionPreview({ sectionKey, data }: { sectionKey: SectionKey; data: PerfilEstructurado }) {
  const value = data[sectionKey];
  if (!value) return null;

  if (sectionKey === "skills" || sectionKey === "lenguajes") {
    return (
      <div className="flex flex-wrap gap-1">
        {(value as string[]).map((item, i) => (
          <span key={i} className="rounded-full bg-primary-100 px-2 py-0.5 text-xs text-primary-700">
            {item}
          </span>
        ))}
      </div>
    );
  }

  if (sectionKey === "experiencia") {
    const items = value as PerfilEstructurado["experiencia"];
    return (
      <ul className="space-y-1 text-xs text-gray-600">
        {items?.map((exp, i) => (
          <li key={i}>
            <span className="font-medium">{exp.puesto}</span> en {exp.empresa} ({exp.duracion})
          </li>
        ))}
      </ul>
    );
  }

  if (sectionKey === "educacion") {
    const items = value as PerfilEstructurado["educacion"];
    return (
      <ul className="space-y-1 text-xs text-gray-600">
        {items?.map((edu, i) => (
          <li key={i}>
            <span className="font-medium">{edu.titulo}</span> — {edu.institucion} ({edu.ano})
          </li>
        ))}
      </ul>
    );
  }

  if (sectionKey === "proyectos") {
    const items = value as PerfilEstructurado["proyectos"];
    return (
      <ul className="space-y-1 text-xs text-gray-600">
        {items?.map((p, i) => (
          <li key={i}>
            <span className="font-medium">{p.nombre}</span>: {p.descripcion.slice(0, 80)}…
          </li>
        ))}
      </ul>
    );
  }

  if (sectionKey === "certificaciones") {
    const items = value as PerfilEstructurado["certificaciones"];
    return (
      <ul className="space-y-1 text-xs text-gray-600">
        {items?.map((c, i) => (
          <li key={i}>
            {c.nombre} — {c.emisor} ({c.ano})
          </li>
        ))}
      </ul>
    );
  }

  return null;
}
