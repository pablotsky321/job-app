import { describe, it, expect } from "vitest";
import { mapProfileQueryToOutcome } from "../profileCheck";
import type { MeProfile } from "../types";

describe("profileCheck", () => {
  describe("mapProfileQueryToOutcome", () => {
    // Unit tests: explicit examples for all branches
    it("returns 'loading' when isLoading is true, regardless of data/error state", () => {
      const result = mapProfileQueryToOutcome({
        isLoading: true,
        data: undefined,
        error: null,
        isError: false,
      });
      expect(result).toEqual({ status: "loading" });

      // Even with data present, loading takes precedence
      const resultWithData = mapProfileQueryToOutcome({
        isLoading: true,
        data: {} as MeProfile,
        error: null,
        isError: false,
      });
      expect(resultWithData).toEqual({ status: "loading" });
    });

    it("returns 'exists' when data is present", () => {
      const mockProfile = {} as MeProfile;

      const result = mapProfileQueryToOutcome({
        isLoading: false,
        data: mockProfile,
        error: null,
        isError: false,
      });
      expect(result).toEqual({ status: "exists" });
    });

    it("returns 'not_found' when error contains 404", () => {
      const error404 = new Error("HTTP 404: Not Found");
      const result = mapProfileQueryToOutcome({
        isLoading: false,
        data: undefined,
        error: error404,
        isError: true,
      });
      expect(result).toEqual({ status: "not_found" });
    });

    it("returns 'error' for 5xx or network errors", () => {
      const error5xx = new Error("HTTP 500: Internal Server Error");
      const result = mapProfileQueryToOutcome({
        isLoading: false,
        data: undefined,
        error: error5xx,
        isError: true,
      });
      expect(result.status).toBe("error");
      expect(result).toHaveProperty("message");
    });

    it("handles non-Error objects in error field", () => {
      const result = mapProfileQueryToOutcome({
        isLoading: false,
        data: undefined,
        error: new Error("String error"),
        isError: true,
      });
      expect(result.status).toBe("error");
      expect(result).toHaveProperty("message");
    });

    it("returns error fallback for completely unknown state", () => {
      const result = mapProfileQueryToOutcome({
        isLoading: false,
        data: undefined,
        error: null,
        isError: false,
      });
      expect(result.status).toBe("error");
      expect(result).toHaveProperty("message");
    });
  });
});
