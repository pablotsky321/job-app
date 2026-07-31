import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { resolvePostLoginDestination } from "../postLoginRedirect";

describe("postLoginRedirect", () => {
  describe("resolvePostLoginDestination", () => {
    // Feature: frontend-navigation, Property 1: Post-login destination resolution
    it("returns '/onboarding/1' for 'not_found' regardless of savedRedirect, and uses savedRedirect for 'exists' when provided", () => {
      fc.assert(
        fc.property(
          fc.oneof(
            fc.constant(null),
            fc.constant(""),
            fc.webUrl(),
          ),
          (savedRedirect) => {
            // Case 1: "not_found" always returns "/onboarding/1"
            const notFoundResult = resolvePostLoginDestination("not_found", savedRedirect);
            expect(notFoundResult).toBe("/onboarding/1");

            // Case 2: "exists" with valid redirect returns the redirect
            const existsWithRedirect = resolvePostLoginDestination("exists", savedRedirect);
            if (savedRedirect && savedRedirect.trim()) {
              expect(existsWithRedirect).toBe(savedRedirect);
            } else {
              expect(existsWithRedirect).toBe("/");
            }
          },
        ),
        { numRuns: 100 },
      );
    });

    // Unit test examples: explicit cases for all branches
    it("returns '/onboarding/1' for 'not_found' when savedRedirect is null", () => {
      expect(resolvePostLoginDestination("not_found", null)).toBe("/onboarding/1");
    });

    it("returns '/onboarding/1' for 'not_found' when savedRedirect is empty string", () => {
      expect(resolvePostLoginDestination("not_found", "")).toBe("/onboarding/1");
    });

    it("returns '/onboarding/1' for 'not_found' even when savedRedirect is a valid path", () => {
      expect(resolvePostLoginDestination("not_found", "/vacancies")).toBe("/onboarding/1");
    });

    it("returns the savedRedirect for 'exists' when it is a non-empty string", () => {
      expect(resolvePostLoginDestination("exists", "/vacancies")).toBe("/vacancies");
      expect(resolvePostLoginDestination("exists", "/applications")).toBe("/applications");
      expect(resolvePostLoginDestination("exists", "/profile")).toBe("/profile");
    });

    it("returns '/' for 'exists' when savedRedirect is null", () => {
      expect(resolvePostLoginDestination("exists", null)).toBe("/");
    });

    it("returns '/' for 'exists' when savedRedirect is an empty string", () => {
      expect(resolvePostLoginDestination("exists", "")).toBe("/");
    });

    it("returns '/' for 'exists' when savedRedirect is whitespace-only", () => {
      expect(resolvePostLoginDestination("exists", "   ")).toBe("/");
    });
  });
});
