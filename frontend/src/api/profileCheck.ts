import type { UseQueryResult } from "@tanstack/react-query";
import type { MeProfile } from "./types";

/**
 * Represents the outcome of a profile-existence check.
 * Derived from useProfileData via mapProfileQueryToOutcome.
 * Never stored directly in the React Query cache — the cache stores MeProfile, not ProfileCheckOutcome.
 */
export type ProfileCheckOutcome =
  | { status: "loading" }
  | { status: "exists" }
  | { status: "not_found" }
  | { status: "error"; message: string };

/**
 * Maps a useQuery result (GET /me/profile) to a navigation outcome.
 * Checks isLoading FIRST, before evaluating data/error/isError at all.
 * Returns the first applicable outcome; branches are mutually exclusive by design.
 *
 * Requirements: 2.2, 2.5, 10.1
 */
export function mapProfileQueryToOutcome(
  result: Pick<UseQueryResult<MeProfile>, "data" | "error" | "isError" | "isLoading">,
): ProfileCheckOutcome {
  if (result.isLoading) {
    return { status: "loading" };
  }

  if (result.data) {
    return { status: "exists" };
  }

  if (result.isError && result.error) {
    // Check if this is a 404 error
    const isNotFound =
      result.error instanceof Error &&
      result.error.message &&
      result.error.message.includes("404");

    if (isNotFound) {
      return { status: "not_found" };
    }

    // Any other error (5xx, network)
    const errorMessage =
      result.error instanceof Error
        ? result.error.message
        : typeof result.error === "string"
          ? result.error
          : "Se produjo un error al verificar tu perfil";

    return { status: "error", message: errorMessage };
  }

  // Fallback: treat as error
  return { status: "error", message: "Estado desconocido en la verificación de perfil" };
}
