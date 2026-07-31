/**
 * Token exchange logic extracted from AuthContext.handleCallback.
 * Encapsulates the Cognito token-endpoint request and response parsing.
 *
 * Requirements: 8.1
 */

export interface ExchangedTokens {
  accessToken: string;
  idToken: string;
}

/**
 * Extracts and validates access_token and id_token from a Cognito token-endpoint response.
 * Throws if either token is missing or empty, matching today's handleCallback error behavior.
 *
 * @param body the parsed JSON response from the Cognito token endpoint
 * @returns the extracted tokens
 * @throws if either token is missing or empty
 */
export function extractTokensFromResponse(body: unknown): ExchangedTokens {
  if (!body || typeof body !== "object") {
    throw new Error("Invalid token response: body is not an object");
  }

  const bodyObj = body as Record<string, unknown>;
  const accessToken = bodyObj.access_token;
  const idToken = bodyObj.id_token;

  if (!accessToken || typeof accessToken !== "string" || !accessToken.trim()) {
    throw new Error("Token response missing required field: access_token");
  }

  if (!idToken || typeof idToken !== "string" || !idToken.trim()) {
    throw new Error("Token response missing required field: id_token");
  }

  return { accessToken, idToken };
}

/**
 * Exchanges an authorization code for tokens via the Cognito token endpoint.
 * Internally uses extractTokensFromResponse for parsing — this function encapsulates
 * the full request/response cycle and delegates validation to extractTokensFromResponse.
 *
 * @param cognitoDomain the Cognito domain (e.g., "https://...")
 * @param clientId the OAuth2 client ID
 * @param redirectUri the registered redirect URI
 * @param code the authorization code from Cognito
 * @param codeVerifier the PKCE code verifier (from sessionStorage)
 * @returns the exchanged tokens
 * @throws if the token endpoint responds with non-2xx, or if the response is missing tokens
 */
export async function exchangeCodeForTokens({
  cognitoDomain,
  clientId,
  redirectUri,
  code,
  codeVerifier,
}: {
  cognitoDomain: string;
  clientId: string;
  redirectUri: string;
  code: string;
  codeVerifier: string;
}): Promise<ExchangedTokens> {
  const tokenUrl = `${cognitoDomain}/oauth2/token`;
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: clientId,
    redirect_uri: redirectUri,
    code,
    code_verifier: codeVerifier,
  });

  const response = await fetch(tokenUrl, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  if (!response.ok) {
    throw new Error(`Token exchange failed: ${response.status}`);
  }

  const responseData = await response.json();
  return extractTokensFromResponse(responseData);
}
