/**
 * Scan Polling Exit Condition
 * Determines whether the polling loop for a scan job should continue or terminate.
 *
 * Property 2: For any status value, returns true (stop polling) if and only if
 * status is in {DONE, PARCIAL, FAILED}; returns false (continue polling) for
 * RUNNING or any unrecognized value.
 */

export function isScanTerminal(status: string | undefined): boolean {
  return status === "DONE" || status === "PARCIAL" || status === "FAILED";
}
