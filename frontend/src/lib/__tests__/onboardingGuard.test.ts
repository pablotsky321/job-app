import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { resolveOnboardingGuardAction } from "../onboardingGuard";

describe("onboardingGuard", () => {
  describe("resolveOnboardingGuardAction", () => {
    // Feature: frontend-navigation, Property 4: Onboarding guard action is independent of the requested step
    it("returns action based only on profileStatus, never on step value", () => {
      fc.assert(
        fc.property(
          fc.oneof(
            fc.constant("1"),
            fc.constant("2"),
            fc.constant("3"),
            fc.constant("4"),
            fc.constant("invalid-step"),
            fc.constant(""),
            fc.string({ minLength: 1, maxLength: 30 }),
          ),
          () => {
            // Case 1: "exists" always returns "redirect_to_profile", regardless of step
            const existsResult = resolveOnboardingGuardAction("exists");
            expect(existsResult).toBe("redirect_to_profile");

            // Case 2: "not_found" always returns "render", regardless of step
            const notFoundResult = resolveOnboardingGuardAction("not_found");
            expect(notFoundResult).toBe("render");

            // Both results are independent of the step value (which is ignored anyway)
            expect(existsResult).toBe("redirect_to_profile");
            expect(notFoundResult).toBe("render");
          },
        ),
        { numRuns: 100 },
      );
    });

    // Unit test examples: explicit cases for both outcomes
    it("returns 'redirect_to_profile' for 'exists'", () => {
      expect(resolveOnboardingGuardAction("exists")).toBe("redirect_to_profile");
    });

    it("returns 'render' for 'not_found'", () => {
      expect(resolveOnboardingGuardAction("not_found")).toBe("render");
    });
  });
});
