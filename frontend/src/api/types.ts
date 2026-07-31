/**
 * Domain type re-exports derived from the generated OpenAPI schema.
 * Never redefine fields manually — use Pick/Omit/Partial over generated types.
 */
import type { components } from "./generated/schema";

// --- Profile ---
export type ProfileResponse = components["schemas"]["ProfileResponse"];
export type MeProfile = ProfileResponse;
export type PerfilEstructurado = components["schemas"]["PerfilEstructurado"];
export type ExperienciaLaboral = components["schemas"]["ExperienciaLaboral"];
export type Educacion = components["schemas"]["Educacion"];
export type Proyecto = components["schemas"]["Proyecto"];
export type Certificacion = components["schemas"]["Certificacion"];
export type ParseCVRequest = components["schemas"]["ParseCVRequest"];
export type SaveProfileRequest = components["schemas"]["SaveProfileRequest"];
export type SetRolesRequest = components["schemas"]["SetRolesRequest"];

// --- Companies ---
export type CompanyListItem = components["schemas"]["CompanyListItem"];
export type CompaniesListResponse = components["schemas"]["CompaniesListResponse"];
export type AddCompanyRequest = components["schemas"]["AddCompanyRequest"];
export type CompanyCreateResponse = components["schemas"]["CompanyCreateResponse"];

// --- Subscriptions ---
export type SubscriptionItem = components["schemas"]["SubscriptionItem"];
export type SubscriptionListResponse = components["schemas"]["SubscriptionListResponse"];
export type ToggleSubscriptionRequest = components["schemas"]["ToggleSubscriptionRequest"];
export type SubscriptionUpdateResponse = components["schemas"]["SubscriptionUpdateResponse"];

// --- Health ---
export type HealthResponse = components["schemas"]["HealthResponse"];

// --- Errors ---
export type HTTPValidationError = components["schemas"]["HTTPValidationError"];
export type ValidationError = components["schemas"]["ValidationError"];
