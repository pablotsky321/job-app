import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { hasStaleItems, reconcileFrozenOrder } from "../rescoringFreeze";
import type { VacancyListItem } from "../types";

const arbitraryVacancyListItem = (): fc.Arbitrary<VacancyListItem> =>
  fc.record({
    companyId: fc.string(),
    vacancyId: fc.string(),
    titulo: fc.string(),
    empresa: fc.string(),
    ubicacion: fc.string(),
    modalidad: fc.string(),
    score: fc.oneof(fc.constant(null), fc.integer({ min: 0, max: 100 })),
    veredicto: fc.oneof(
      fc.constantFrom("excelente", "buen_encaje", "parcial", "bajo"),
      fc.constant(null),
    ),
    staleFlag: fc.boolean(),
    estadoAplicacion: fc.constantFrom("nueva", "vista", "aplicada", "filtered_out"),
    firstSeenAt: fc.date().map((d) => d.toISOString()),
    lastSeenAt: fc.date().map((d) => d.toISOString()),
    appliedAt: fc.oneof(fc.constant(null), fc.date().map((d) => d.toISOString())),
  });

describe("rescoringFreeze", () => {
  describe("hasStaleItems", () => {
    // Feature: frontend-spa, Property 3: Stale item detection
    it("returns true iff at least one item has staleFlag === true", () => {
      fc.assert(
        fc.property(fc.array(arbitraryVacancyListItem()), (items) => {
          const result = hasStaleItems(items);
          const hasAnyStale = items.some((item) => item.staleFlag === true);
          expect(result).toBe(hasAnyStale);
        }),
        { numRuns: 100 },
      );
    });

    // Unit test example: empty list always returns false
    it("returns false for an empty list", () => {
      expect(hasStaleItems([])).toBe(false);
    });

    it("returns true when at least one item is stale", () => {
      const items: VacancyListItem[] = [
        {
          companyId: "c1",
          vacancyId: "v1",
          titulo: "Job 1",
          empresa: "Company 1",
          ubicacion: "NYC",
          modalidad: "remoto",
          score: 75,
          veredicto: "buen_encaje",
          staleFlag: false,
          estadoAplicacion: "nueva",
          firstSeenAt: "2025-01-01T00:00:00Z",
          lastSeenAt: "2025-01-02T00:00:00Z",
          appliedAt: null,
        },
        {
          companyId: "c2",
          vacancyId: "v2",
          titulo: "Job 2",
          empresa: "Company 2",
          ubicacion: "SF",
          modalidad: "hibrido",
          score: 80,
          veredicto: "excelente",
          staleFlag: true,
          estadoAplicacion: "vista",
          firstSeenAt: "2025-01-01T00:00:00Z",
          lastSeenAt: "2025-01-02T00:00:00Z",
          appliedAt: null,
        },
      ];

      expect(hasStaleItems(items)).toBe(true);
    });
  });

  describe("reconcileFrozenOrder", () => {
    // Feature: frontend-spa, Property 4: Order reconciliation preserves frozen positions
    it("preserves relative order of persistent items and appends new items at the end", () => {
      fc.assert(
        fc.property(
          fc
            .tuple(
              fc.array(arbitraryVacancyListItem(), { minLength: 0, maxLength: 5 }),
              fc.array(arbitraryVacancyListItem(), { minLength: 0, maxLength: 3 }),
            )
            .chain(([baseItems, newItems]) => {
              const frozenOrder = baseItems;
              // Create latest: keep some from frozen, update some, add new
              const persistent = frozenOrder.slice(0, Math.ceil(frozenOrder.length / 2));
              const updatedPersistent = persistent.map((item) => ({
                ...item,
                score: Math.floor(Math.random() * 100),
              }));
              const latest = [...updatedPersistent, ...newItems];
              return fc.tuple(
                fc.constant(frozenOrder),
                fc.constant(latest),
                fc.constant(updatedPersistent),
                fc.constant(newItems),
              );
            }),
          ([frozenOrder, latest, expectedPersistent, expectedNew]) => {
            const result = reconcileFrozenOrder(frozenOrder, latest);

            // Verify length
            expect(result.length).toBe(expectedPersistent.length + expectedNew.length);

            // Verify persistent items appear first, in frozen order, with fresh data
            const resultPersistentCount = expectedPersistent.length;
            for (let i = 0; i < resultPersistentCount; i++) {
              const resultItem = result[i];
              const expectedItem = expectedPersistent[i];
              expect(resultItem.companyId).toBe(expectedItem.companyId);
              expect(resultItem.vacancyId).toBe(expectedItem.vacancyId);
              expect(resultItem.score).toBe(expectedItem.score);
            }

            // Verify new items appear at the end
            const resultNewItems = result.slice(resultPersistentCount);
            for (let i = 0; i < resultNewItems.length; i++) {
              const resultItem = resultNewItems[i];
              const expectedItem = expectedNew[i];
              expect(resultItem.companyId).toBe(expectedItem.companyId);
              expect(resultItem.vacancyId).toBe(expectedItem.vacancyId);
            }
          },
        ),
        { numRuns: 50 }, // Reduced due to complex tuple generation
      );
    });

    // Unit test example: basic reconciliation
    it("reconciles order correctly with a simple example", () => {
      const item1: VacancyListItem = {
        companyId: "c1",
        vacancyId: "v1",
        titulo: "Job 1",
        empresa: "Company 1",
        ubicacion: "NYC",
        modalidad: "remoto",
        score: 75,
        veredicto: "buen_encaje",
        staleFlag: false,
        estadoAplicacion: "nueva",
        firstSeenAt: "2025-01-01T00:00:00Z",
        lastSeenAt: "2025-01-02T00:00:00Z",
        appliedAt: null,
      };

      const item2: VacancyListItem = {
        companyId: "c2",
        vacancyId: "v2",
        titulo: "Job 2",
        empresa: "Company 2",
        ubicacion: "SF",
        modalidad: "hibrido",
        score: 80,
        veredicto: "excelente",
        staleFlag: true,
        estadoAplicacion: "vista",
        firstSeenAt: "2025-01-01T00:00:00Z",
        lastSeenAt: "2025-01-02T00:00:00Z",
        appliedAt: null,
      };

      const item3: VacancyListItem = {
        companyId: "c3",
        vacancyId: "v3",
        titulo: "Job 3",
        empresa: "Company 3",
        ubicacion: "LA",
        modalidad: "onsite",
        score: 65,
        veredicto: "parcial",
        staleFlag: false,
        estadoAplicacion: "aplicada",
        firstSeenAt: "2025-01-01T00:00:00Z",
        lastSeenAt: "2025-01-02T00:00:00Z",
        appliedAt: "2025-01-03T00:00:00Z",
      };

      const frozenOrder = [item1, item2];
      const latest = [
        { ...item1, score: 85 }, // updated score
        item3, // new item
      ];

      const result = reconcileFrozenOrder(frozenOrder, latest);

      // item1 should appear first with updated score, item3 should appear last
      expect(result.length).toBe(2);
      expect(result[0].companyId).toBe("c1");
      expect(result[0].score).toBe(85);
      expect(result[1].companyId).toBe("c3");
    });
  });
});
