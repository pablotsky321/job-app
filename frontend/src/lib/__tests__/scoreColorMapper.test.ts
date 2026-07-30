import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { scoreColorMapper } from "../scoreColorMapper";

describe("scoreColorMapper", () => {
  // Feature: frontend-spa, Property 1: Score_Color_Mapper is a deterministic table
  it("maps each verdict deterministically to the correct color", () => {
    fc.assert(
      fc.property(
        fc.constantFrom("excelente", "buen_encaje", "parcial", "bajo"),
        (veredicto) => {
          const expected = {
            excelente: "success",
            buen_encaje: "primary",
            parcial: "warning",
            bajo: "gray",
          } as const;

          const result = scoreColorMapper(veredicto);
          expect(result).toBe(expected[veredicto]);
        },
      ),
      { numRuns: 100 },
    );
  });

  // Unit test example: document the full table
  it("shows the complete color mapping table", () => {
    const testCases = [
      { veredicto: "excelente", expectedColor: "success" },
      { veredicto: "buen_encaje", expectedColor: "primary" },
      { veredicto: "parcial", expectedColor: "warning" },
      { veredicto: "bajo", expectedColor: "gray" },
    ] as const;

    testCases.forEach(({ veredicto, expectedColor }) => {
      expect(
        scoreColorMapper(veredicto as "excelente" | "buen_encaje" | "parcial" | "bajo"),
      ).toBe(expectedColor);
    });
  });
});
