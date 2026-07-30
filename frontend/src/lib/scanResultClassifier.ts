import type { ScanJobStatus, ScanOutcome } from "./types";

/**
 * Scan Result Classifier
 *
 * Classifies the outcome of a scan job based on its terminal status and the number of new vacancies found.
 * Used primarily by SourcesView to determine the visual representation of a scan result.
 *
 * Note: This function covers two of the three distinctions required by Requirement 12.12:
 * - "fallido" for FAILED
 * - "sin_novedades" for DONE with count=0
 * - "nuevas_encontradas" for any terminal status with count>0
 *
 * The third distinction (PARCIAL as visually separate from FAILED) is handled explicitly
 * in SourcesView before calling this function, to preserve a three-way decision tree.
 *
 * Property 7: For all count ∈ [0, 999]:
 * - classifyScanResult("DONE", count) returns "sin_novedades" when count === 0
 * - classifyScanResult("FAILED", count) returns "fallido" for all count
 */

export function classifyScanResult(
  status: ScanJobStatus | string,
  newVacancyCount: number,
): ScanOutcome {
  if (status === "FAILED") {
    return "fallido";
  }

  if (status === "PARCIAL" && newVacancyCount === 0) {
    return "fallido";
  }

  if (newVacancyCount > 0) {
    return "nuevas_encontradas";
  }

  return "sin_novedades";
}
