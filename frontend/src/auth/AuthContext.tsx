import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { tokenStore } from "./tokenStore";
import { generateCodeVerifier, generateCodeChallenge } from "./pkce";
import { registerUnauthorizedHandler } from "../api/client";

interface AuthContextValue {
  isAuthenticated: boolean;
  login: () => Promise<void>;
  handleCallback: (code: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(
    () => tokenStore.getAccessToken() !== null
  );

  const cognitoDomain = import.meta.env.VITE_COGNITO_DOMAIN as string;
  const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID as string;
  const redirectUri = import.meta.env.VITE_COGNITO_REDIRECT_URI as string;

  const logout = useCallback(() => {
    tokenStore.clear();
    setIsAuthenticated(false);
    const logoutUrl =
      `${cognitoDomain}/logout?client_id=${clientId}` +
      `&logout_uri=${encodeURIComponent(redirectUri)}`;
    window.location.href = logoutUrl;
  }, [cognitoDomain, clientId, redirectUri]);

  // Register the 401 handler on mount to avoid circular imports with api/client.ts
  useEffect(() => {
    registerUnauthorizedHandler(() => logout());
  }, [logout]);

  const login = useCallback(async () => {
    // Save current route for post-login redirect
    const currentPath = window.location.pathname + window.location.search;
    sessionStorage.setItem("post_login_redirect", currentPath);

    // Generate PKCE pair
    const verifier = generateCodeVerifier();
    sessionStorage.setItem("pkce_code_verifier", verifier);
    const challenge = await generateCodeChallenge(verifier);

    // Redirect to Cognito Hosted UI
    const authorizeUrl =
      `${cognitoDomain}/oauth2/authorize?` +
      `response_type=code` +
      `&client_id=${clientId}` +
      `&redirect_uri=${encodeURIComponent(redirectUri)}` +
      `&code_challenge=${challenge}` +
      `&code_challenge_method=S256` +
      `&scope=openid+profile+email`;

    window.location.href = authorizeUrl;
  }, [cognitoDomain, clientId, redirectUri]);

  const handleCallback = useCallback(
    async (code: string) => {
      const codeVerifier = sessionStorage.getItem("pkce_code_verifier");
      if (!codeVerifier) {
        throw new Error("Missing PKCE code_verifier in session");
      }

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
        // Do NOT persist partial tokens on error
        throw new Error(`Token exchange failed: ${response.status}`);
      }

      const data = await response.json();
      const accessToken = data.access_token as string;
      const idToken = data.id_token as string;

      if (!accessToken || !idToken) {
        throw new Error("Token response missing required tokens");
      }

      // Only persist when we have both tokens
      tokenStore.setTokens(accessToken, idToken);
      setIsAuthenticated(true);

      // Navigate to saved route or default to /
      const savedRoute = sessionStorage.getItem("post_login_redirect") || "/";
      sessionStorage.removeItem("post_login_redirect");
      sessionStorage.removeItem("pkce_code_verifier");
      window.location.href = savedRoute;
    },
    [cognitoDomain, clientId, redirectUri]
  );

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, handleCallback, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
