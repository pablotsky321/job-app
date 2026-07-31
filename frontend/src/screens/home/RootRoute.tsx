import { useAuth } from "@/auth/AuthContext";
import { LandingPage } from "./LandingPage";
import { Dashboard } from "./Dashboard";

/**
 * Root route handler (/) that renders either LandingPage or Dashboard
 * based on authentication status.
 *
 * Requirements: 1.1, 1.2, 1.4
 */
export function RootRoute() {
  const { isAuthenticated } = useAuth();

  return isAuthenticated ? <Dashboard /> : <LandingPage />;
}
