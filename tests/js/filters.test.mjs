// Unit tests for static/js/lib/filters.js: the same rules as the server's task filters.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEFAULT_STATUSES,
  emptyFilters,
  filterTasks,
  isFiltered,
  matchesSearch,
  toggleStatus,
} from "../../taskboard/static/js/lib/filters.js";

const task = (key, over = {}) => ({
  key,
  title: `Task ${key}`,
  description: "",
  status: "idea",
  department_id: 1,
  section_id: 11,
  placements: [],
  ...over,
});

const TASKS = [
  task("104", { title: "Root-cause analysis", description: "Correlate with ROLL changes", status: "started" }),
  task("098", { title: "Tonnage-based work-roll regrinding", placements: [{ project_id: 1 }, { project_id: 2 }] }),
  task("130", { title: "Écran de contrôle", department_id: 2, section_id: 21, status: "started" }),
  task("062", { title: "Clean up records", status: "archived", placements: [{ project_id: 1 }] }),
];

const keys = (tasks) => tasks.map((t) => t.key);

test("defaults hide archived tasks only", () => {
  assert.deepEqual(DEFAULT_STATUSES, ["idea", "started", "done"]);
  assert.deepEqual(keys(filterTasks(TASKS, emptyFilters())), ["104", "098", "130"]);
});

test("search covers title and description, ignoring case (also beyond ASCII)", () => {
  assert.ok(matchesSearch(TASKS[0], "roll"));
  assert.ok(matchesSearch(TASKS[1], "  ROLL "));
  assert.ok(matchesSearch(TASKS[2], "écran"));
  assert.ok(matchesSearch(TASKS[2], "ÉCRAN"));
  assert.ok(!matchesSearch(TASKS[2], "roll"));
  assert.deepEqual(keys(filterTasks(TASKS, { ...emptyFilters(), q: "roll" })), ["104", "098"]);
});

test("filters keep rank order", () => {
  const f = { ...emptyFilters(), statuses: ["started"] };
  assert.deepEqual(keys(filterTasks(TASKS, f)), ["104", "130"]);
});

test("organization and project filters", () => {
  assert.deepEqual(keys(filterTasks(TASKS, { ...emptyFilters(), departmentId: 2 })), ["130"]);
  assert.deepEqual(keys(filterTasks(TASKS, { ...emptyFilters(), sectionId: 11 })), ["104", "098"]);
  const all = ["idea", "started", "done", "archived"];
  assert.deepEqual(keys(filterTasks(TASKS, { ...emptyFilters(), statuses: all, projectId: 1 })), ["098", "062"]);
});

test("toggling statuses keeps lifecycle order", () => {
  assert.deepEqual(toggleStatus(["idea", "done"], "started"), ["idea", "started", "done"]);
  assert.deepEqual(toggleStatus(["idea", "started"], "idea"), ["started"]);
});

test("isFiltered compares with the defaults", () => {
  assert.equal(isFiltered(emptyFilters()), false);
  assert.equal(isFiltered({ ...emptyFilters(), q: "x" }), true);
  assert.equal(isFiltered({ ...emptyFilters(), statuses: ["idea"] }), true);
});
