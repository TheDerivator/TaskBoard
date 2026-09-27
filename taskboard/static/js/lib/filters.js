/** Client-side task filtering for instant feedback; same rules as the server (GET /api/tasks). */

export const DEFAULT_STATUSES = Object.freeze(["idea", "started", "done"]);

export function emptyFilters() {
  return { q: "", statuses: [...DEFAULT_STATUSES], departmentId: null, sectionId: null, projectId: null };
}

/** Case-insensitive "contains" on title + description (DESIGN rule 3). */
export function matchesSearch(task, q) {
  const needle = (q ?? "").trim().toLocaleLowerCase();
  if (!needle) return true;
  return `${task.title}\n${task.description}`.toLocaleLowerCase().includes(needle);
}

/**
 * Tasks passing every active filter, in their original (rank) order. Filters never change ranks.
 * @param {Array<object>} tasks  TaskSummary objects from the API
 * @param {{q: string, statuses: string[], departmentId: ?number, sectionId: ?number, projectId: ?number}} f
 */
export function filterTasks(tasks, f) {
  const statuses = new Set(f.statuses ?? DEFAULT_STATUSES);
  return tasks.filter(
    (t) =>
      statuses.has(t.status) &&
      matchesSearch(t, f.q) &&
      (f.departmentId == null || t.department_id === f.departmentId) &&
      (f.sectionId == null || t.section_id === f.sectionId) &&
      (f.projectId == null || t.placements.some((p) => p.project_id === f.projectId)),
  );
}

/** Toggle one status in a filter's list, keeping the canonical lifecycle order. */
export function toggleStatus(statuses, status, order = ["idea", "started", "done", "archived"]) {
  const next = new Set(statuses);
  if (next.has(status)) next.delete(status);
  else next.add(status);
  return order.filter((s) => next.has(s));
}

/** True when any filter differs from the defaults (the view then says "Showing X of Y"). */
export function isFiltered(f) {
  const defaults = emptyFilters();
  return (
    f.q.trim() !== "" ||
    f.departmentId != null ||
    f.sectionId != null ||
    f.projectId != null ||
    f.statuses.join() !== defaults.statuses.join()
  );
}
