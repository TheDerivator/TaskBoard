// Unit tests for static/js/lib/controlplan.js on the design's defects and Continuous casting map.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { causeDiagram, causesOf, defectGroups, DIAGRAM, inSentence, pathOf, planIndex } from "../../taskboard/static/js/lib/controlplan.js";

// The API's plan (GET /api/control-plan?department=STL), built from the design's sample data:
// every box and link is in it, which the derivations must tolerate.
const SAMPLE = JSON.parse(readFileSync(new URL("../../team-tasks-design/sample-data.json", import.meta.url), "utf-8"));
const GROUPS = { "d-sliver": "Surface", "d-blisters": "Surface", "d-incl": "Internal", "d-trans": "Cracks", "d-long": "Cracks", "d-corner": "Cracks", "d-edge": "Other" };
const CC = 3;
const LM = 2;
const positions = new Map();
const PLAN = {
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
      fields: GROUPS[b.id] ? { group: GROUPS[b.id] } : {},
    };
  }),
  links: SAMPLE.links.map((l) => ({ id: l.id, type: l.type_id, from_key: l.from_box, to_key: l.to_box, note_md: l.note_md })),
  controls: SAMPLE.controls.map((c, position) => ({ id: c.id, box_key: c.box_id, kind: c.type, text: c.text, position })),
  kinds: SAMPLE.box_kinds.map((k) => ({ key: k.id, name: k.name })),
  link_types: SAMPLE.link_types.map((t) => ({ key: t.id, role: t.id === "leads_to" ? "leads_to" : "plain" })),
};
const INDEX = planIndex(PLAN);
const ORDER = new Map([
  [LM, 0],
  [CC, 1],
]);
const causes = (defect, options = {}) => causesOf(INDEX, defect, { processOrder: ORDER, ...options });

test("the defects in their groups, with their number of known causes (the DefectView mockup)", () => {
  const groups = defectGroups(INDEX);
  assert.deepEqual(
    groups.map((g) => [g.name, g.defects.map((d) => `${d.name} ${d.count}`)]),
    [
      ["Surface", ["Sliver lines 4", "Blisters 1"]],
      ["Internal", ["Inclusions 1"]],
      ["Cracks", ["Transverse cracks 2", "Longitudinal cracks 1", "Corner cracks 1"]],
      ["Other", ["Edge defects 1"]],
    ],
  );
  assert.deepEqual(
    defectGroups(INDEX, { query: "CRACK" }).map((g) => g.defects.map((d) => d.key)),
    [["d-trans", "d-long", "d-corner"]],
  );
});

test("a defect without a group goes under Other, at the end", () => {
  const plan = { ...PLAN, boxes: PLAN.boxes.map((b) => (b.key === "d-sliver" ? { ...b, fields: {} } : b)) };
  const groups = defectGroups(planIndex(plan));
  assert.deepEqual(groups.at(-1), { name: "Other", defects: [{ key: "d-sliver", name: "Sliver lines", count: 4 }, { key: "d-edge", name: "Edge defects", count: 1 }] });
});

test("the causes of a defect in map order, with where they sit and how they lead to it", () => {
  const sliver = causes("d-sliver");
  assert.deepEqual(
    sliver.map((c) => [c.key, c.where, c.sub]),
    [
      ["fm-clog", "tun", "tun-flow"],
      ["fm-slag", "tun", "tun-slag"],
      ["fm-level", "mould", "m-level"],
      ["fm-powder", "mould", "m-powder"],
    ],
  );
  assert.equal(sliver[2].link.note_md, "Meniscus waves fold powder into the shell as it forms.");
  assert.deepEqual(pathOf(INDEX, "fm-level"), ["cc", "mould", "m-level"]);
  assert.deepEqual(causes("d-blisters").map((c) => c.key), ["fm-powder"]);
  assert.deepEqual(causes("d-trans").map((c) => [c.key, c.where]), [["fm-osc", "mould"], ["fm-duct", "bow"]]);
  // fm-clog leads to fm-level, which leads to longitudinal cracks: only direct causes count.
  assert.deepEqual(causes("d-long").map((c) => c.key), ["fm-level"]);
  assert.deepEqual(INDEX.controls.get("fm-level").map((c) => c.kind), ["prevent", "prevent", "detect"]);
});

test("one process's causes, and the defects it can cause", () => {
  assert.equal(causes("d-sliver", { process: CC }).length, 4);
  assert.equal(causes("d-sliver", { process: LM }).length, 0);
  assert.deepEqual(defectGroups(INDEX, { process: LM }), []);
  assert.deepEqual(defectGroups(INDEX, { process: LM, keep: "d-incl" }), [{ name: "Internal", defects: [{ key: "d-incl", name: "Inclusions", count: 0 }] }]);
  // Process order comes first: the same causes in another process would be listed before CC's.
  const plan = { ...PLAN, boxes: PLAN.boxes.map((b) => (b.key === "fm-powder" ? { ...b, process_id: LM, parent_key: null } : b)) };
  assert.deepEqual(causesOf(planIndex(plan), "d-sliver", { processOrder: ORDER }).map((c) => c.key), ["fm-powder", "fm-clog", "fm-slag", "fm-level"]);
});

test("the diagram: causes in rows, each where level with its causes, the defect with the wheres", () => {
  const diagram = causeDiagram(causes("d-sliver"));
  assert.deepEqual(diagram.causes.map((c) => c.y), [20, 94, 168, 242]);
  const centre = (node) => node.y + node.height / 2;
  const [tundish, mould] = diagram.wheres;
  assert.deepEqual([tundish.key, mould.key], ["tun", "mould"]);
  assert.equal(centre(tundish), (centre(diagram.causes[0]) + centre(diagram.causes[1])) / 2);
  assert.equal(centre(mould), (centre(diagram.causes[2]) + centre(diagram.causes[3])) / 2);
  assert.equal(centre(diagram.defect), (centre(tundish) + centre(mould)) / 2);
  for (const node of [diagram.defect, ...diagram.wheres, ...diagram.causes]) {
    assert.ok(node.y >= 0 && node.y + node.height <= diagram.height, "inside the diagram");
  }
  assert.equal(tundish.x + tundish.width < DIAGRAM.cause.x && DIAGRAM.defect.width < tundish.x, true);
  // Lines run from each column to the next: one into every where and every cause.
  const stubs = (x) => diagram.lines.filter((l) => l.x + l.width === x && l.height === 2).length;
  assert.equal(stubs(DIAGRAM.where.x), 2);
  assert.equal(stubs(DIAGRAM.cause.x), 4);
});

test("a defect without known causes stands alone", () => {
  const diagram = causeDiagram([]);
  assert.deepEqual(diagram.lines, []);
  assert.equal(diagram.defect.y, DIAGRAM.top);
});

test("names inside a sentence", () => {
  assert.equal(inSentence("Sliver lines"), "sliver lines");
  assert.equal(inSentence("CO2 blisters"), "CO2 blisters");
  assert.equal(inSentence("edge defects"), "edge defects");
});
