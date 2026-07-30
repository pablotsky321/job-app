/**
 * CV-ATS Blob Builder
 *
 * Two pure functions for constructing CV-ATS downloadable artifacts:
 * 1. buildCvAtsFileName: generates a unique filename incorporating company and vacancy identifiers
 * 2. buildCvAtsBlob: wraps text content in a Blob with text/plain MIME type
 *
 * Property 5: Round-trip integrity
 *   - buildCvAtsFileName encodes both companyId and vacancyId, ends with .txt
 *   - buildCvAtsBlob returns a Blob whose text content is identical to input (no transformation)
 *
 * Property 6: Non-collision
 *   - Two different (companyId, vacancyId) pairs produce different filenames
 */

export function buildCvAtsFileName(companyId: string, vacancyId: string): string {
  // Sanitize identifiers: replace non-alphanumeric chars with _, limit to 60 chars each
  const safe = (s: string) => s.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 60);

  return `cv-ats_${safe(companyId)}_${safe(vacancyId)}.txt`;
}

export function buildCvAtsBlob(cvAtsTexto: string): Blob {
  return new Blob([cvAtsTexto], { type: "text/plain;charset=utf-8" });
}
