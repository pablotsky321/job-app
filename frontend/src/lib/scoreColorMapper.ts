import type { BadgeColor } from "./types";

/**
 * Score_Color_Mapper: deterministic table that maps a scoring verdict to a badge color.
 * This function is a pure table lookup with no side effects.
 *
 * Mapping:
 * - excelente  → success
 * - buen_encaje → primary
 * - parcial    → warning
 * - bajo       → gray
 */
export function scoreColorMapper(
  veredicto: "excelente" | "buen_encaje" | "parcial" | "bajo",
): BadgeColor {
  const colorMap: Record<string, BadgeColor> = {
    excelente: "success",
    buen_encaje: "primary",
    parcial: "warning",
    bajo: "gray",
  };

  return colorMap[veredicto];
}
