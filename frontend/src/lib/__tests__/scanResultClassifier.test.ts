import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { classifyScanResult } from "../scanResultClassifier";

describe("scanResultClassifier", () => {
  // Feature: frontend-spa, Property 7: Scan result classification by status and count boundaries
  it("returns 'sin_novedades' for DONE with count=0, and 'fallido' for FAILED regardless of count", () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.integer({ min: 0, max: 999 }),
          fc.integer({ min: 0, max: 999 }),
        ),
        ([doneCount, failedCount]) => {
          const doneResult = classifyScanResult("DONE", doneCount);
          if (doneCount === 0) {
            expect(doneResult).toBe("sin_novedades");
          } else {
            expect(doneResult).toBe("nuevas_encontradas");
          }

          const failedResult = classifyScanResult("FAILED", failedCount);
          expect(failedResult).toBe("fallido");
        },
      ),
      { numRuns: 100 },
    );
  });

  // Unit test examples: explicit cases for all branches
  it("returns 'sin_novedades' for DONE with count=0", () => {
    expect(classifyScanResult("DONE", 0)).toBe("sin_novedades");
  });

  it("returns 'nuevas_encontradas' for DONE with count>0", () => {
    expect(classifyScanResult("DONE", 5)).toBe("nuevas_encontradas");
    expect(classifyScanResult("DONE", 100)).toBe("nuevas_encontradas");
  });

  it("returns 'fallido' for FAILED regardless of count", () => {
    expect(classifyScanResult("FAILED", 0)).toBe("fallido");
    expect(classifyScanResult("FAILED", 5)).toBe("fallido");
    expect(classifyScanResult("FAILED", 999)).toBe("fallido");
  });

  it("returns 'fallido' for PARCIAL with count=0", () => {
    expect(classifyScanResult("PARCIAL", 0)).toBe("fallido");
  });

  it("returns 'nuevas_encontradas' for PARCIAL with count>0", () => {
    expect(classifyScanResult("PARCIAL", 5)).toBe("nuevas_encontradas");
    expect(classifyScanResult("PARCIAL", 100)).toBe("nuevas_encontradas");
  });
});
