// Unit tests for static/js/lib/search.js: filters with counts, hit order, keys, context lines.
import assert from "node:assert/strict";
import { test } from "node:test";

import { filterChips, hitContext, moveActive, shownGroups, shownHits } from "../../taskboard/static/js/lib/search.js";

// The GlobalSearch mockup's results for "mould powder".
const hit = (type, title, extra = {}) => ({ type, title, key: title, ref: "", context: "", url: `/${title}`, ...extra });
const GROUPS = [
  { type: "knowledge", total: 3, hits: [hit("knowledge", "Mould powder"), hit("knowledge", "Powder entrapment"), hit("knowledge", "Powder datasheets")] },
  { type: "changes", total: 1, hits: [hit("changes", "Mould powder type B", { ref: "CC-31", process: "Continuous casting", state: "in_effect", state_date: "2026-05-18" })] },
  { type: "tasks", total: 2, hits: [hit("tasks", "Root-cause analysis"), hit("tasks", "Inspection criteria")] },
  { type: "defects", total: 1, hits: [hit("defects", "Sliver lines")] },
];

test("the type filters with their counts", () => {
  assert.deepEqual(
    filterChips(GROUPS).map((c) => `${c.label} · ${c.count}`),
    ["All · 7", "Knowledge · 3", "Process changes · 1", "Tasks · 2", "Defects · 1"],
  );
  assert.deepEqual(filterChips([{ type: "tasks", total: 0, hits: [] }]).map((c) => c.label), ["All"]);
});

test("the hits shown, in group order, under a filter", () => {
  assert.deepEqual(shownGroups(GROUPS, null).map((g) => g.label), ["Knowledge", "Process changes", "Tasks", "Defects"]);
  assert.equal(shownHits(GROUPS, null).length, 7);
  assert.deepEqual(shownHits(GROUPS, "tasks").map((h) => h.title), ["Root-cause analysis", "Inspection criteria"]);
});

test("moving through the hits with the keyboard", () => {
  assert.equal(moveActive(0, "ArrowDown", 7), 1);
  assert.equal(moveActive(6, "ArrowDown", 7), 6);
  assert.equal(moveActive(0, "ArrowUp", 7), 0);
  assert.equal(moveActive(3, "End", 7), 6);
  assert.equal(moveActive(3, "Home", 7), 0);
  assert.equal(moveActive(0, "ArrowDown", 0), -1);
});

test("a change's context line: process, state, then where the match is", () => {
  assert.equal(hitContext(GROUPS[1].hits[0]), "Continuous casting · in effect since 18 May");
  assert.equal(hitContext({ ...GROUPS[1].hits[0], context: "Period: Test · LF2" }), "Continuous casting · in effect since 18 May · Period: Test · LF2");
  assert.equal(hitContext(hit("tasks", "x", { context: "Started · Lead Anna Claes" })), "Started · Lead Anna Claes");
});
