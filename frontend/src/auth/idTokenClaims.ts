/**
 * Decodes and extracts claims from a Cognito id_token (JWT).
 * No signature verification — the id_token is read client-side for UI display only,
 * not for authorization (the access_token authorizes API calls).
 *
 * Requirements: 4.6
 */

/**
 * Base64url-decodes a JWT payload segment.
 * Returns null instead of throwing on malformed input, allowing graceful fallback in UI display.
 *
 * @param token a JWT string
 * @returns decoded payload as a Record, or null if decoding fails
 */
export function decodeIdToken(token: string): Record<string, unknown> | null {
  try {
    // Split JWT into segments
    const segments = token.split(".");
    if (segments.length !== 3) {
      return null;
    }

    // Base64url-decode the payload (second segment)
    const payload = segments[1];
    // Replace URL-safe characters and add padding if needed
    const decoded = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(decoded) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * Extracts the email claim from a JWT id_token.
 * Returns null if the token is malformed or the email claim is missing/empty.
 *
 * @param idToken a Cognito id_token
 * @returns the email string, or null if not found or decoding fails
 */
export function getEmailFromIdToken(idToken: string): string | null {
  if (!idToken) {
    return null;
  }

  const payload = decodeIdToken(idToken);
  if (!payload) {
    return null;
  }

  const email = payload.email;
  if (typeof email === "string" && email.trim()) {
    return email;
  }

  return null;
}
