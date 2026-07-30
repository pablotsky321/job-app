import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { isScanTerminal } from "../scanPollingExit";

describe("scanPollingExit", () => {
  // Feature: frontend-spa, Property 2: Scan polling exit condition
  it("returns true (stop) for terminal statuses, false (continue) for others", () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constantFrom("DONE", "PARCIAL", "FAILED"),
          fc.constantFrom("RUNNING"),
          fc.string(),
        ),
        (status) => {
          const result = isScanTerminal(status);
          const isTerminal = status === "DONE" || status === "PARCIAL" || status === "FAILED";
          expect(result).toBe(isTerminal);
        },
      ),
      { numRuns: 100 },
    );
  });

  // Unit test examples: explicit terminal and non-terminal cases
  it("returns true for DONE, PARCIAL, FAILED", () => {
    expect(isScanTerminal("DONE")).toBe(true);
    expect(isScanTerminal("PARCIAL")).toBe(true);
    expect(isScanTerminal("FAILED")).toBe(true);
  });

  it("returns false for RUNNING and unrecognized values", () => {
    expect(isScanTerminal("RUNNING")).toBe(false);
    expect(isScanTerminal("UNKNOWN")).toBe(false);
    expect(isScanTerminal("")).toBe(false);
    expect(isScanTerminal(undefined)).toBe(false);
  });
});
