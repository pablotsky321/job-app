/**
 * Convención de query keys: ["<recurso>", ...params]
 *
 * Cada hook de queries/ y mutations/ reutiliza estas funciones helper
 * en vez de escribir arrays de query key a mano. Esto centraliza la
 * convención y garantiza tipado de parámetros.
 */

export const vacanciesKey = (estado: string) => ["vacancies", estado] as const;

export const vacancyKey = (companyId: string, vacancyId: string) =>
  ["vacancy", companyId, vacancyId] as const;

export const scanKey = (jobId: string) => ["scan", jobId] as const;

export const entriesKey = (companyId: string, vacancyId: string) =>
  ["entries", companyId, vacancyId] as const;

export const companiesKey = () => ["companies"] as const;

export const subscriptionsKey = () => ["subscriptions"] as const;

export const profileKey = () => ["profile"] as const;
