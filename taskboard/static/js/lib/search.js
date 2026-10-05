/** Search everything (pure): the dialog's type filters with counts, the hits it lists in order,
 * moving through them with the arrow keys, and each hit's context line (the GlobalSearch mockup). */
import { stateLabel } from "./periods.js";

export const SEARCH_TYPES = [
  { type: "knowledge", label: "Knowledge" },
  { type: "changes", label: "Process changes" },
  { type: "tasks", label: "Tasks" },
  { type: "defects", label: "Defects" },
];

const labelOf = (type) => SEARCH_TYPES.find((t) => t.type === type)?.label ?? type;

/** "All · 7", then each type with matches: "Knowledge · 3", ... (`type` null is "All"). */
export function filterChips(groups) {
  const total = groups.reduce((sum, g) => sum + g.total, 0);
  return [{ type: null, label: "All", count: total }, ...groups.filter((g) => g.total > 0).map((g) => ({ type: g.type, label: labelOf(g.type), count: g.total }))];
}

/** The groups shown under a filter, each with its heading, and every hit in reading order. */
export function shownGroups(groups, filter) {
  return groups.filter((g) => g.hits.length > 0 && (filter == null || g.type === filter)).map((g) => ({ ...g, label: labelOf(g.type) }));
}

export function shownHits(groups, filter) {
  return shownGroups(groups, filter).flatMap((g) => g.hits);
}

/** The arrow keys: down and up move one hit and stop at the ends; Home and End jump. */
export function moveActive(index, key, count) {
  if (count === 0) return -1;
  switch (key) {
    case "ArrowDown":
      return Math.min(index + 1, count - 1);
    case "ArrowUp":
      return Math.max(index - 1, 0);
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return index;
  }
}

/** A hit's line under its title: a change shows its process and state before the match. */
export function hitContext(hit) {
  if (hit.type !== "changes") return hit.context;
  const state = hit.state ? stateLabel({ state: hit.state, date: hit.state_date }) : null;
  return [hit.process, state && state.charAt(0).toLowerCase() + state.slice(1), hit.context].filter(Boolean).join(" · ");
}
