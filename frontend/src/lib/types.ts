/**
 * Local UI-derived types (not API resources)
 * These types represent state derived from API responses but not persisted as
 * first-class backend entities. They are defined here to avoid circular dependencies
 * between lib/ (pure functions) and api/ (generated types).
 */

export type ScanJobStatus = "RUNNING" | "DONE" | "PARCIAL" | "FAILED";

export interface VacancyListItem {
  companyId: string;
  vacancyId: string;
  titulo: string;
  empresa: string;
  ubicacion: string;
  modalidad: string;
  score: number | null;
  veredicto: "excelente" | "buen_encaje" | "parcial" | "bajo" | null;
  staleFlag: boolean;
  estadoAplicacion: "nueva" | "vista" | "aplicada" | "filtered_out";
  firstSeenAt: string; // ISO 8601
  lastSeenAt: string; // ISO 8601
  appliedAt: string | null;
}

export type BadgeColor = "success" | "primary" | "warning" | "gray";

export type ScanOutcome = "sin_novedades" | "nuevas_encontradas" | "fallido";

export interface StoredTokens {
  accessToken: string;
  idToken: string;
}
