// Token_Store — thin wrapper over sessionStorage (never localStorage or cookies)
export const tokenStore = {
  getAccessToken: (): string | null => sessionStorage.getItem("access_token"),
  getIdToken: (): string | null => sessionStorage.getItem("id_token"),
  setTokens: (accessToken: string, idToken: string): void => {
    sessionStorage.setItem("access_token", accessToken);
    sessionStorage.setItem("id_token", idToken);
  },
  clear: (): void => {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("id_token");
    sessionStorage.removeItem("pkce_code_verifier");
    sessionStorage.removeItem("post_login_redirect");
  },
};
