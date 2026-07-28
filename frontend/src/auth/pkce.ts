// PKCE utilities — RFC 7636 code_verifier + code_challenge (S256)

function base64UrlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * Generates a cryptographically random code_verifier (43–128 chars, base64url).
 * Uses crypto.getRandomValues as the entropy source.
 */
export function generateCodeVerifier(): string {
  // 32 random bytes → 43 base64url chars (without padding)
  const buffer = new Uint8Array(32);
  crypto.getRandomValues(buffer);
  return base64UrlEncode(buffer.buffer);
}

/**
 * Derives the code_challenge from a verifier using SHA-256 + base64url (S256 method).
 */
export async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return base64UrlEncode(digest);
}
