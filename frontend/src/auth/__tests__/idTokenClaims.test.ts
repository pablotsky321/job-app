import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { decodeIdToken, getEmailFromIdToken } from "../idTokenClaims";

// Helper: base64url encode (matching pkce.ts convention)
function base64UrlEncode(str: string): string {
  const buffer = new TextEncoder().encode(str);
  let binary = "";
  for (let i = 0; i < buffer.byteLength; i++) {
    binary += String.fromCharCode(buffer[i]);
  }
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

// Helper: build a minimal JWT with email claim
function buildJwtWithEmail(email: string): string {
  const header = base64UrlEncode(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const payload = base64UrlEncode(JSON.stringify({ email, sub: "user123" }));
  const signature = base64UrlEncode("fake-signature");
  return `${header}.${payload}.${signature}`;
}

describe("idTokenClaims", () => {
  describe("decodeIdToken", () => {
    it("returns null for malformed input", () => {
      expect(decodeIdToken("")).toBeNull();
      expect(decodeIdToken("invalid-jwt")).toBeNull();
      expect(decodeIdToken("too.many.segments.here")).toBeNull();
      expect(decodeIdToken("invalid..payload")).toBeNull();
    });

    it("decodes valid JWT payloads", () => {
      const jwt = buildJwtWithEmail("test@example.com");
      const decoded = decodeIdToken(jwt);
      expect(decoded).toBeDefined();
      expect(decoded?.email).toBe("test@example.com");
      expect(decoded?.sub).toBe("user123");
    });
  });

  describe("getEmailFromIdToken", () => {
    // Feature: frontend-navigation, Property 3: ID token email round-trip
    it("round-trips arbitrary email strings through encode-decode", () => {
      fc.assert(
        fc.property(
          fc.emailAddress(),
          (email) => {
            const jwt = buildJwtWithEmail(email);
            const extracted = getEmailFromIdToken(jwt);
            expect(extracted).toBe(email);
          },
        ),
        { numRuns: 100 },
      );
    });

    // Unit test examples: explicit cases
    it("extracts email from valid id_token", () => {
      const jwt = buildJwtWithEmail("alice@company.com");
      expect(getEmailFromIdToken(jwt)).toBe("alice@company.com");
    });

    it("returns null for empty string", () => {
      expect(getEmailFromIdToken("")).toBeNull();
    });

    it("returns null for malformed token", () => {
      expect(getEmailFromIdToken("invalid-jwt-format")).toBeNull();
    });

    it("returns null when email claim is missing", () => {
      const header = base64UrlEncode(JSON.stringify({ alg: "RS256", typ: "JWT" }));
      const payload = base64UrlEncode(JSON.stringify({ sub: "user123" })); // no email
      const signature = base64UrlEncode("fake-signature");
      const jwt = `${header}.${payload}.${signature}`;
      expect(getEmailFromIdToken(jwt)).toBeNull();
    });

    it("returns null when email claim is empty string", () => {
      const jwt = buildJwtWithEmail("");
      expect(getEmailFromIdToken(jwt)).toBeNull();
    });

    it("returns null when email claim is not a string", () => {
      const header = base64UrlEncode(JSON.stringify({ alg: "RS256", typ: "JWT" }));
      const payload = base64UrlEncode(JSON.stringify({ email: 123 })); // number instead of string
      const signature = base64UrlEncode("fake-signature");
      const jwt = `${header}.${payload}.${signature}`;
      expect(getEmailFromIdToken(jwt)).toBeNull();
    });
  });
});
