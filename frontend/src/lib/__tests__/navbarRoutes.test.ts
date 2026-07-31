import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { isNavbarRoute } from "../navbarRoutes";

describe("navbarRoutes", () => {
  describe("isNavbarRoute", () => {
    // Feature: frontend-navigation, Property 2: Navbar route matching is total and correct
    it("returns true for all Navbar routes and false for excluded routes", () => {
      fc.assert(
        fc.property(
          fc.tuple(
            fc.string({ minLength: 1, maxLength: 20 }).filter((s) => s.trim().length > 0),
            fc.string({ minLength: 1, maxLength: 20 }).filter((s) => s.trim().length > 0),
            fc.oneof(
              fc.constant("1"),
              fc.constant("2"),
              fc.constant("3"),
              fc.constant("random-step"),
            ),
          ),
          ([companyId, vacancyId, step]) => {
            // Ensure segment values are safe (no slashes)
            const safeCompanyId = companyId.replace(/\//g, "-");
            const safeVacancyId = vacancyId.replace(/\//g, "-");

            // Case 1: Dynamic routes in NAVBAR_ROUTES should match
            const vacancyPath = `/vacancies/${safeCompanyId}/${safeVacancyId}`;
            expect(isNavbarRoute(vacancyPath)).toBe(true);

            const applicationPath = `/applications/${safeCompanyId}/${safeVacancyId}`;
            expect(isNavbarRoute(applicationPath)).toBe(true);

            // Case 2: Routes NOT in NAVBAR_ROUTES should not match
            const onboardingPath = `/onboarding/${step}`;
            expect(isNavbarRoute(onboardingPath)).toBe(false);

            const callbackPath = "/callback";
            expect(isNavbarRoute(callbackPath)).toBe(false);
          },
        ),
        { numRuns: 100 },
      );
    });

    // Unit test examples: explicit cases for all static and dynamic routes
    it("returns true for static navbar routes", () => {
      expect(isNavbarRoute("/")).toBe(true);
      expect(isNavbarRoute("/vacancies")).toBe(true);
      expect(isNavbarRoute("/applications")).toBe(true);
      expect(isNavbarRoute("/sources")).toBe(true);
      expect(isNavbarRoute("/profile")).toBe(true);
    });

    it("returns true for dynamic navbar routes with arbitrary segment values", () => {
      expect(isNavbarRoute("/vacancies/company-123/vacancy-456")).toBe(true);
      expect(isNavbarRoute("/vacancies/aws/internship-2024")).toBe(true);
      expect(isNavbarRoute("/applications/netflix/senior-engineer")).toBe(true);
      expect(isNavbarRoute("/applications/google/xyz")).toBe(true);
    });

    it("returns false for excluded routes", () => {
      expect(isNavbarRoute("/callback")).toBe(false);
      expect(isNavbarRoute("/onboarding/1")).toBe(false);
      expect(isNavbarRoute("/onboarding/2")).toBe(false);
      expect(isNavbarRoute("/onboarding/3")).toBe(false);
      expect(isNavbarRoute("/onboarding/4")).toBe(false);
      expect(isNavbarRoute("/onboarding/random-step")).toBe(false);
    });

    it("returns false for unmapped routes", () => {
      expect(isNavbarRoute("/not-found")).toBe(false);
      expect(isNavbarRoute("/admin")).toBe(false);
      expect(isNavbarRoute("/settings")).toBe(false);
    });
  });
});
