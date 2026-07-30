import type { VacancyListItem } from "./types";

/**
 * Rescoring_Freeze_Logic
 *
 * Two pure functions for managing UI state during rescoring:
 * 1. hasStaleItems: detects if the list contains at least one stale item
 * 2. reconcileFrozenOrder: preserves frozen order while updating data from fresh responses
 *
 * Property 3: hasStaleItems returns true iff at least one item has staleFlag === true.
 *            Empty list always returns false.
 *
 * Property 4: reconcileFrozenOrder preserves relative order of elements present in both
 *            frozenOrder and latest (using data from latest), and appends new items at the end
 *            in their relative order from latest.
 */

export function hasStaleItems(items: VacancyListItem[]): boolean {
  return items.some((item) => item.staleFlag === true);
}

function keyOf(item: VacancyListItem): string {
  return `${item.companyId}#${item.vacancyId}`;
}

export function reconcileFrozenOrder(
  frozenOrder: VacancyListItem[],
  latest: VacancyListItem[],
): VacancyListItem[] {
  // Map latest items by their identity key for O(1) lookup
  const latestByKey = new Map(latest.map((item) => [keyOf(item), item]));

  // Preserve order from frozenOrder, using fresh data from latest
  const stillPresent = frozenOrder
    .filter((item) => latestByKey.has(keyOf(item)))
    .map((item) => latestByKey.get(keyOf(item))!);

  // Find items present in latest but not in frozenOrder
  const presentKeys = new Set(stillPresent.map(keyOf));
  const newItems = latest.filter((item) => !presentKeys.has(keyOf(item)));

  // Return reconciled list: persistent items in frozen order, then new items
  return [...stillPresent, ...newItems];
}
