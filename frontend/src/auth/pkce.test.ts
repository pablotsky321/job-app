import { describe, it, expect } from "vitest";
import { generateCodeVerifier, generateCodeChallenge } from "./pkce";

describe("PKCE", () => {
  describe("generateCodeVerifier", () => {
    it("produces a verifier with length between 43 and 128 characters", () => {
      const verifier = generateCodeVerifier();
      expect(verifier.length).toBeGreaterThanOrEqual(43);
      expect(verifier.length).toBeLessThanOrEqual(128);
    });

    it("produces different verifiers on successive invocations", () => {
      const v1 = generateCodeVerifier();
      const v2 = generateCodeVerifier();
      expect(v1).not.toBe(v2);
    });

    it("uses only base64url characters (no +, /, or =)", () => {
      const verifier = generateCodeVerifier();
      expect(verifier).toMatch(/^[A-Za-z0-9_-]+$/);
    });
  });

  describe("generateCodeChallenge", () => {
    it("is deterministic: same verifier produces same challenge", async () => {
      const verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
      const challenge1 = await generateCodeChallenge(verifier);
      const challenge2 = await generateCodeChallenge(verifier);
      expect(challenge1).toBe(challenge2);
    });

    it("produces a base64url-encoded string", async () => {
      const verifier = "test-verifier-value";
      const challenge = await generateCodeChallenge(verifier);
      expect(challenge).toMatch(/^[A-Za-z0-9_-]+$/);
    });
  });
});
