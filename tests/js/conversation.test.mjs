// Unit tests for static/js/lib/events.js (event wording) and lib/editor.js (composer edits).
import assert from "node:assert/strict";
import { test } from "node:test";

import { insertBlock, lineEnd, prefixLines, removeFragment, wrap } from "../../taskboard/static/js/lib/editor.js";
import { describeEvent } from "../../taskboard/static/js/lib/events.js";

const lookup = {
  people: new Map([
    [1, { name: "Anna Claes" }],
    [4, { name: "Dries Wouters" }],
  ]),
  projects: new Map([[2, { name: "Projects 2026" }]]),
  nodes: new Map([[11, { number: "2", name: "Process" }]]),
  sections: new Map([[13, { name: "Maintenance", department_id: 1 }]]),
  departments: new Map([[1, { code: "STL" }]]),
};
const anna = { display_name: "Anna Claes" };

test("event wording", () => {
  const say = (kind, data, actor = anna) => {
    const { actor: who, text } = describeEvent({ kind, data, actor }, lookup);
    return `${who} ${text}`;
  };
  assert.equal(say("status_changed", { from: "idea", to: "started" }), "Anna Claes moved this from Idea to Started");
  assert.equal(say("created", {}), "Anna Claes created this task");
  assert.equal(say("helper_added", { person: 4 }), "Anna Claes added Dries Wouters");
  assert.equal(say("helper_removed", { person: 99 }), "Anna Claes removed someone");
  assert.equal(say("lead_changed", { from: 1, to: 4 }), "Anna Claes made Dries Wouters the lead (was Anna Claes)");
  assert.equal(say("section_changed", { from: 1, to: 13 }), "Anna Claes moved this to STL · Maintenance");
  assert.equal(say("placement_added", { project: 2, node: 11 }), "Anna Claes added this to Projects 2026 › 2 Process");
  assert.equal(say("placement_moved", { project: 2, from: 11, to: null }), "Anna Claes moved this within Projects 2026 to the top level");
  assert.equal(say("placement_removed", { project: 9, node: null }), "Anna Claes removed this from a deleted project");
  assert.equal(say("created", {}, null), "Someone created this task");
});

test("wrapping the selection", () => {
  assert.deepEqual(wrap("make this bold", 5, 9, "**"), { text: "make **this** bold", start: 7, end: 11 });
  assert.deepEqual(wrap("x", 1, 1, "`", "`", "code"), { text: "x`code`", start: 2, end: 6 });
  assert.deepEqual(wrap("site", 0, 4, "[", "](https://)"), { text: "[site](https://)", start: 1, end: 5 });
});

test("prefixing lines for a list", () => {
  const value = "intro\none\ntwo";
  const result = prefixLines(value, 6, value.length, "- ");
  assert.equal(result.text, "intro\n- one\n- two");
});

test("a new block goes after the caret's line", () => {
  const value = "**bold text**\nnext line";
  assert.equal(lineEnd(value, 2), 13);
  assert.equal(insertBlock(value, lineEnd(value, 2), "![a](u)").text, "**bold text**\n![a](u)\nnext line");
  assert.equal(lineEnd("no newline", 3), 10);
});

test("images go on their own line", () => {
  assert.equal(insertBlock("See:", 4, "![a](u)").text, "See:\n![a](u)");
  assert.equal(insertBlock("ab", 1, "![a](u)").text, "a\n![a](u)\nb");
  assert.equal(insertBlock("", 0, "![a](u)").text, "![a](u)");
});

test("removing an attached image from the text", () => {
  assert.equal(removeFragment("See:\n![a](u)\nmore", "![a](u)"), "See:\nmore");
  assert.equal(removeFragment("x ![a](u)", "![a](u)"), "x ");
});
