import { Outlet } from "react-router-dom";
import { Navbar } from "./Navbar";

/**
 * Layout wrapper component used for authenticated routes.
 * Renders Navbar at the top, followed by the outlet for nested routes.
 *
 * Used as the element of the parent route wrapping:
 * - /
 * - /vacancies
 * - /vacancies/:companyId/:vacancyId
 * - /applications
 * - /applications/:companyId/:vacancyId
 * - /sources
 * - /profile
 *
 * Requirements: 3.5, 3.6
 */
export function Layout() {
  return (
    <>
      <Navbar />
      <Outlet />
    </>
  );
}
