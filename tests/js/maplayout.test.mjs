// Unit tests for static/js/lib/maplayout.js on the design's Continuous casting map.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  allCollapsed,
  ancestors,
  changeBadges,
  effectsOf,
  fmeaBoxes,
  keyboardMove,
  layoutMap,
  linkIndex,
  mapTree,
  overviewCollapsed,
  readingOrder,
  roleOf,
  searchMap,
  typedLinks,
} from "../../taskboard/static/js/lib/maplayout.js";

// The API's graph (GET /api/processes/CC/map), built from the design's sample data.
const SAMPLE = JSON.parse(readFileSync(new URL("../../team-tasks-design/sample-data.json", import.meta.url), "utf-8"));
const ROLES = { step: "step", know: "knowledge", ref: "reference", rule: "rule", fm: "failure_mode", defect: "defect" };
const CC = 3;
const positions = new Map();
const GRAPH = {
  process: { id: CC, code: "CC", name: "Continuous casting" },
  root_key: "cc",
  boxes: SAMPLE.boxes.map((b) => {
    const siblings = b.parent_id ?? `catalogue:${b.process_id}`;
    positions.set(siblings, (positions.get(siblings) ?? 0) + 1024);
    return {
      key: b.id,
      process_id: b.process_id ? CC : null,
      parent_key: b.parent_id,
      position: positions.get(siblings),
      kind: b.kind_id,
      name: b.name,
      body_md: b.body_md ?? "",
      facts: Object.entries(b.facts ?? {}),
      step_no: b.step_no,
    };
  }),
  links: SAMPLE.links.map((l) => ({ id: l.id, type: l.type_id, from_key: l.from_box, to_key: l.to_box, note_md: l.note_md })),
  kinds: SAMPLE.box_kinds.map((k, position) => ({ key: k.id, name: k.name, role: ROLES[k.id], position })),
  link_types: SAMPLE.link_types.map((t, position) => ({
    key: t.id,
    forward_name: t.forward_name,
    backward_name: t.backward_name,
    role: t.id === "leads_to" ? "leads_to" : "plain",
    position,
  })),
};
const TREE = mapTree(GRAPH);
const INDEX = linkIndex(GRAPH);
const effects = (key) => effectsOf(TREE, INDEX, key);

const centre = (node) => node.y + node.height / 2;

test("the tree of the ProcessMap mockup", () => {
  assert.equal(TREE.root, "cc");
  assert.deepEqual(TREE.children.get("cc"), ["overview", "speeds", "plan", "tun", "mould", "sec", "bow", "cut"]);
  assert.deepEqual(TREE.children.get("mould"), ["m-level", "m-powder", "m-osc"]);
  assert.deepEqual(ancestors(TREE, "fm-level"), ["cc", "mould", "m-level"]);
  assert.ok(!TREE.own.has("d-sliver") && TREE.byKey.has("d-sliver")); // defects are outside the tree
});

test("the layout: columns by depth, no overlaps, parents level with the middle of their children", () => {
  const layout = layoutMap(TREE, { effects });
  assert.equal(layout.nodes.length, TREE.own.size);
  assert.deepEqual(layout.nodes.slice(0, 3).map((n) => n.key), ["cc", "overview", "speeds"]); // reading order
  const byKey = new Map(layout.nodes.map((n) => [n.key, n]));
  assert.deepEqual([0, 1, 2, 3].map((d) => layout.nodes.find((n) => n.depth === d).x), [0, 196, 382, 588]);
  for (const depth of [1, 2, 3]) {
    const column = layout.nodes.filter((n) => n.depth === depth).sort((a, b) => a.y - b.y);
    for (let i = 1; i < column.length; i += 1) {
      assert.ok(column[i].y >= column[i - 1].y + column[i - 1].height, `${column[i].key} overlaps ${column[i - 1].key}`);
    }
  }
  for (const node of layout.nodes.filter((n) => n.expanded)) {
    const kids = TREE.children.get(node.key).map((k) => byKey.get(k));
    assert.equal(centre(node), (centre(kids[0]) + centre(kids[kids.length - 1])) / 2, node.key);
  }
  assert.ok(layout.width >= 588 + 200 && layout.height > 0);
});

test("a failure mode's box makes room for its defect chips", () => {
  assert.deepEqual(effects("fm-level"), ["Sliver lines", "Longitudinal cracks"]);
  assert.deepEqual(effects("fm-clog"), ["Sliver lines"]); // its link to another failure mode is no chip
  const layout = layoutMap(TREE, { effects });
  // "Mould level fluctuation" takes two lines, and its two chips a second row (the mockup's sums).
  assert.equal(layout.nodes.find((n) => n.key === "fm-level").height, 18 + 86);
  assert.equal(layout.nodes.find((n) => n.key === "fm-clog").height, 62);
});

test("the FMEA: failure modes and the boxes on the way to them (the FmeaMap mockup)", () => {
  const kept = fmeaBoxes(TREE);
  const keep = (key) => kept.has(key);
  const layout = layoutMap(TREE, { keep, effects });
  const shown = layout.nodes.map((n) => n.key);
  assert.deepEqual(
    layout.nodes.filter((n) => n.depth === 1).map((n) => n.key),
    ["tun", "mould", "sec", "bow", "cut"], // not the overview, the speeds or the planning rules
  );
  assert.ok(shown.includes("fm-powder") && !shown.includes("ref-powder") && !shown.includes("k-osc"));
  assert.equal(shown.filter((k) => roleOf(TREE, k) === "failure_mode").length, 8);
  const column = layout.nodes.filter((n) => n.depth === 3).sort((a, b) => a.y - b.y);
  for (let i = 1; i < column.length; i += 1) assert.ok(column[i].y >= column[i - 1].y + column[i - 1].height);
  const failureModes = readingOrder(TREE).filter((k) => roleOf(TREE, k) === "failure_mode");
  assert.deepEqual(failureModes, ["fm-clog", "fm-slag", "fm-level", "fm-powder", "fm-osc", "fm-spray", "fm-duct", "fm-burr"]);
});

test("collapsed and hidden branches take no room", () => {
  const all = layoutMap(TREE, { effects });
  const collapsed = layoutMap(TREE, { collapsed: new Set(["mould"]), effects });
  assert.ok(!collapsed.nodes.some((n) => ["m-level", "fm-level", "k-osc"].includes(n.key)));
  assert.equal(collapsed.nodes.find((n) => n.key === "mould").expanded, false);
  assert.equal(collapsed.nodes.find((n) => n.key === "mould").shownCount, 3);
  assert.ok(collapsed.height < all.height);
  // Hiding the Rule kind hides "Planning restrictions" and the rules under it.
  const noRules = layoutMap(TREE, { hidden: new Set(["rule"]), effects });
  assert.ok(!noRules.nodes.some((n) => n.key === "plan" || n.key === "r-peri"));
  const everything = layoutMap(TREE, { collapsed: allCollapsed(TREE), effects });
  assert.deepEqual(everything.nodes.map((n) => n.depth).filter((d) => d > 1), []);
});

test("an overview opens only the branch of the selected box", () => {
  assert.deepEqual([...overviewCollapsed(TREE, "fm-level")].sort(), ["bow", "cut", "plan", "sec", "tun"]);
  assert.equal(overviewCollapsed(TREE).size, 6);
});

test("typed links read both ways, in the link types' order", () => {
  const groups = typedLinks(INDEX, "fm-level").map((g) => [g.label, g.items.map((i) => i.key)]);
  assert.deepEqual(groups, [
    ["Leads to", ["d-sliver", "d-long"]],
    ["Caused by", ["fm-clog"]],
    ["Prevented by", ["r-peri"]],
  ]);
  assert.deepEqual(typedLinks(INDEX, "speeds").map((g) => g.label), ["Documents", "See also"]);
});

test("process changes roll up into the boxes above them while those are closed", () => {
  const counts = { "m-powder": 1, "m-level": 1, "sec-spray": 1, "tun-flow": 1 };
  const badges = changeBadges(TREE, counts, new Set(["tun", "sec"]));
  assert.deepEqual(Object.fromEntries(badges), { tun: 1, sec: 1, "m-level": 1, "m-powder": 1 });
  assert.equal(changeBadges(TREE, counts, new Set(["cc"])).get("cc"), 4);
});

test("find in the map: names, descriptions, key facts, step numbers", () => {
  assert.deepEqual([...searchMap(TREE, "POWDER")].sort(), ["fm-level", "fm-powder", "m-powder", "ref-powder"]);
  assert.deepEqual([...searchMap(TREE, "op20")], ["mould"]);
  assert.deepEqual([...searchMap(TREE, "strands")], ["overview"]); // a key fact
  assert.equal(searchMap(TREE, " ").size, 0);
});

test("arrow keys move through the map", () => {
  const layout = layoutMap(TREE, { collapsed: new Set(["tun"]), effects });
  assert.deepEqual(keyboardMove(layout, TREE, "cc", "ArrowDown"), { select: "overview" });
  assert.deepEqual(keyboardMove(layout, TREE, "overview", "ArrowUp"), { select: "cc" });
  assert.deepEqual(keyboardMove(layout, TREE, "tun", "ArrowRight"), { expand: "tun" });
  assert.deepEqual(keyboardMove(layout, TREE, "mould", "ArrowRight"), { select: "m-level" });
  assert.deepEqual(keyboardMove(layout, TREE, "mould", "ArrowLeft"), { collapse: "mould" });
  assert.deepEqual(keyboardMove(layout, TREE, "fm-level", "ArrowLeft"), { select: "m-level" });
  assert.deepEqual(keyboardMove(layout, TREE, "cc", "ArrowLeft"), { collapse: "cc" });
  const closed = layoutMap(TREE, { collapsed: new Set(["cc"]), effects });
  assert.deepEqual(keyboardMove(closed, TREE, "cc", "ArrowLeft"), null);
  assert.deepEqual(keyboardMove(layout, TREE, "fm-level", "Home"), { select: "cc" });
});
