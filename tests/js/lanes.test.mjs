// Unit tests for static/js/lib/lanes.js: people lanes from the sample board's first tasks.
import assert from "node:assert/strict";
import { test } from "node:test";

import { buildLanes } from "../../taskboard/static/js/lib/lanes.js";

const AC = { id: 1, name: "Anna Claes" };
const CM = { id: 3, name: "Chloé Martens" };
const tasks = [
  { key: "104", rank: 1, lead_id: 1, helper_ids: [4] },
  { key: "117", rank: 2, lead_id: 3, helper_ids: [1, 6] },
  { key: "130", rank: 4, lead_id: 3, helper_ids: [6] },
  { key: "133", rank: 7, lead_id: 2, helper_ids: [1, 3, 4] },
];

const summary = (lanes) =>
  lanes.map((l) => [l.person.id, l.lead, l.helping, l.cards.map((c) => `${c.task.key}:${c.role}`)]);

test("lead and helping cards in rank order", () => {
  assert.deepEqual(summary(buildLanes([AC, CM], tasks)), [
    [1, 1, 2, ["104:lead", "117:helping", "133:helping"]],
    [3, 2, 1, ["117:lead", "130:lead", "133:helping"]],
  ]);
});

test("lead only hides helping cards but keeps the counts", () => {
  assert.deepEqual(summary(buildLanes([AC], tasks, { leadOnly: true })), [[1, 1, 2, ["104:lead"]]]);
});
