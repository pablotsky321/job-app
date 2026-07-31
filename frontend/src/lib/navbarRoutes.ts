import { matchPath } from "react-router-dom";

/**
 * Determines whether a given pathname should render the Navbar.
 * Uses matchPath for pattern-based matching of dynamic routes.
 *
 * The Navbar is shown on all routes in Requirement 3.2's list.
 * It is NOT shown on public routes like /callback, /onboarding/:step, or 404.
 *
 * Requirements: 3.2, 3.3, 7.3
 */
const NAVBAR_ROUTES = [
  "/",
  "/vacancies",
  "/vacancies/:companyId/:vacancyId",
  "/applications",
  "/applications/:companyId/:vacancyId",
  "/sources",
  "/profile",
];

/**
 * Checks if a pathname should display the Navbar.
 * @param pathname the current location pathname
 * @returns true if the Navbar should be visible on this route
 */
export function isNavbarRoute(pathname: string): boolean {
  return NAVBAR_ROUTES.some((pattern) => matchPath(pattern, pathname));
}
