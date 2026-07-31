import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { extractTokensFromResponse } from "../tokenExchange";

describe("tokenExchange", () => {
  describe("extractTokensFromResponse", () => {
    // Feature: frontend-navigation, Property 5: Token extraction round-trip and failure contract
    it("extracts tokens round-trip and throws on missing/empty tokens", () => {
      fc.assert(
        fc.property(
          fc.tuple(
            fc.string({ minLength: 1, maxLength: 100 }).filter((s) => s.trim().length > 0),
            fc.string({ minLength: 1, maxLength: 100 }).filter((s) => s.trim().length > 0),
          ),
          ([accessToken, idToken]) => {
            // Success case: both tokens present and non-empty
            const result = extractTokensFromResponse({
              access_token: accessToken,
              id_token: idToken,
            });
            expect(result.accessToken).toBe(accessToken);
            expect(result.idToken).toBe(idToken);
          },
        ),
        { numRuns: 100 },
      );
    });

    it("throws when access_token is missing", () => {
      expect(() =>
        extractTokensFromResponse({
          id_token: "test-id-token",
        }),
      ).toThrow();
    });

    it("throws when id_token is missing", () => {
      expect(() =>
        extractTokensFromResponse({
          access_token: "test-access-token",
        }),
      ).toThrow();
    });

    it("throws when access_token is empty string", () => {
      expect(() =>
        extractTokensFromResponse({
          access_token: "",
          id_token: "test-id-token",
        }),
      ).toThrow();
    });

    it("throws when id_token is empty string", () => {
      expect(() =>
        extractTokensFromResponse({
          access_token: "test-access-token",
          id_token: "",
        }),
      ).toThrow();
    });

    it("throws when both tokens are empty", () => {
      expect(() =>
        extractTokensFromResponse({
          access_token: "",
          id_token: "",
        }),
      ).toThrow();
    });

    it("throws when body is not an object", () => {
      expect(() => extractTokensFromResponse(null)).toThrow();
      expect(() => extractTokensFromResponse("string")).toThrow();
      expect(() => extractTokensFromResponse(123)).toThrow();
    });

    it("throws when access_token or id_token is not a string", () => {
      expect(() =>
        extractTokensFromResponse({
          access_token: 123,
          id_token: "test-id-token",
        }),
      ).toThrow();

      expect(() =>
        extractTokensFromResponse({
          access_token: "test-access-token",
          id_token: { nested: "object" },
        }),
      ).toThrow();
    });

    it("returns extracted tokens for valid response", () => {
      const response = {
        access_token: "eyJhbGc...",
        id_token: "eyJzdWI...",
        token_type: "Bearer",
        expires_in: 3600,
      };
      const result = extractTokensFromResponse(response);
      expect(result).toEqual({
        accessToken: "eyJhbGc...",
        idToken: "eyJzdWI...",
      });
    });
  });
});
