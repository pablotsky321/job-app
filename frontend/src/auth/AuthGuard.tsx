import { useEffect, type ReactNode } from "react";
import { useAuth } from "./AuthContext";

interface AuthGuardProps {
  children: ReactNode;
}

/**
 * Wraps protected routes. If not authenticated, triggers login() immediately
 * and does not render children.
 */
export function AuthGuard({ children }: AuthGuardProps) {
  const { isAuthenticated, login } = useAuth();

  useEffect(() => {
    if (!isAuthenticated) {
      login();
    }
  }, [isAuthenticated, login]);

  if (!isAuthenticated) {
    return null;
  }

  return <>{children}</>;
}
