import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { buildCvAtsFileName, buildCvAtsBlob } from "../cvAtsBlobBuilder";

describe("cvAtsBlobBuilder", () => {
  describe("buildCvAtsFileName", () => {
    // Feature: frontend-spa, Property 5 & 6 (filename part): round-trip and non-collision
    it("generates unique filenames for different (companyId, vacancyId) pairs", () => {
      fc.assert(
        fc.property(
          fc
            .tuple(
              fc.record({
                companyId1: fc.string({ minLength: 1 }),
                vacancyId1: fc.string({ minLength: 1 }),
              }),
              fc.record({
                companyId2: fc.string({ minLength: 1 }),
                vacancyId2: fc.string({ minLength: 1 }),
              }),
            )
            .filter(
              ([pair1, pair2]) =>
                pair1.companyId1 !== pair2.companyId2 || pair1.vacancyId1 !== pair2.vacancyId2,
            ),
          ([pair1, pair2]) => {
            const fileName1 = buildCvAtsFileName(pair1.companyId1, pair1.vacancyId1);
            const fileName2 = buildCvAtsFileName(pair2.companyId2, pair2.vacancyId2);

            expect(fileName1).not.toBe(fileName2);
          },
        ),
        { numRuns: 100 },
      );
    });

    // Unit test example: verify filename structure
    it("produces filenames that encode both identifiers and end with .txt", () => {
      const fileName = buildCvAtsFileName("company-acme", "job-123");
      expect(fileName).toContain("cv-ats");
      expect(fileName).toContain("company-acme");
      expect(fileName).toContain("job-123");
      expect(fileName.endsWith(".txt")).toBe(true);
    });

    it("sanitizes special characters in identifiers", () => {
      const fileName = buildCvAtsFileName("company@#$", "job*&^");
      expect(fileName).toMatch(/^cv-ats_[a-zA-Z0-9_-]*_[a-zA-Z0-9_-]*\.txt$/);
    });
  });

  describe("buildCvAtsBlob", () => {
    // Feature: frontend-spa, Property 5: Round-trip integrity
    it("returns a Blob whose text content is identical to input (round-trip)", async () => {
      await fc.assert(
        fc.asyncProperty(fc.string(), async (cvAtsTexto) => {
          const blob = buildCvAtsBlob(cvAtsTexto);
          const readText = await blob.text();
          expect(readText).toBe(cvAtsTexto);
        }),
        { numRuns: 100 },
      );
    });

    // Unit test example: multi-paragraph CV with line breaks
    it("preserves multi-line CV text exactly", async () => {
      const multiLineCV = `John Doe
123 Main St, NY, NY 10001
john.doe@example.com

EXPERIENCE
Senior Engineer at TechCorp (2020-2025)
- Led team of 5 developers
- Shipped 3 major features
- Improved performance by 40%

Junior Engineer at StartupXYZ (2018-2020)
- Built REST APIs
- Managed database migrations

SKILLS
JavaScript, TypeScript, React, Node.js, SQL`;

      const blob = buildCvAtsBlob(multiLineCV);
      const readText = await blob.text();
      expect(readText).toBe(multiLineCV);
    });

    it("handles empty string", async () => {
      const blob = buildCvAtsBlob("");
      const readText = await blob.text();
      expect(readText).toBe("");
    });

    it("handles Unicode characters", async () => {
      const unicodeCV = `José García García
Teléfono: +34 912 345 678
Email: josé@example.com

EXPERIENCIA
Senior Software Engineer @ Empresa Española (2020-2025)
- Dirigí un equipo de 5 desarrolladores
- Implementé 3 características principales

HABILIDADES
JavaScript, TypeScript, React, Python, SQL`;

      const blob = buildCvAtsBlob(unicodeCV);
      const readText = await blob.text();
      expect(readText).toBe(unicodeCV);
    });

    it("creates a Blob with text/plain MIME type", () => {
      const blob = buildCvAtsBlob("Test content");
      expect(blob.type).toBe("text/plain;charset=utf-8");
    });
  });
});
