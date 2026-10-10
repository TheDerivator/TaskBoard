// Unit tests for static/js/lib/format.js and lib/lookup.js.
import assert from "node:assert/strict";
import { test } from "node:test";

import { formatDate, initials, padRank, plural, shortName } from "../../taskboard/static/js/lib/format.js";
import { canIn, canSomewhere, indexBoot } from "../../taskboard/static/js/lib/lookup.js";

test("ranks are two digits", () => {
  assert.equal(padRank(1), "01");
  assert.equal(padRank(11), "11");
  assert.equal(padRank(120), "120");
});

test("names", () => {
  assert.equal(shortName("Anna Claes"), "Anna C.");
  assert.equal(shortName("Chloé  Martens"), "Chloé M.");
  assert.equal(shortName("admin"), "admin");
  assert.equal(initials("Anna Claes"), "AC");
  assert.equal(initials("jan.peeters"), "JP");
  assert.equal(initials("admin"), "AD");
  assert.equal(initials(""), "?");
});

test("dates", () => {
  const date = new Date(2026, 8, 19, 14, 2);
  assert.equal(formatDate(date), "19 Sep");
  assert.equal(formatDate(date, { withTime: true }), "19 Sep, 14:02");
  assert.equal(formatDate(date, { withTime: true, withYear: true }), "19 Sep 2026, 14:02");
  assert.equal(plural(1, "task"), "1 task");
  assert.equal(plural(3, "task"), "3 tasks");
});

const BOOT = {
  me: {
    person_id: 7,
    permissions: {
      "task.view": { everywhere: true, section_ids: [] },
      "task.edit": { everywhere: false, section_ids: [11, 12] },
      "users.manage": { everywhere: false, section_ids: [] },
    },
  },
  people: [{ id: 7, name: "Anna Claes" }],
  departments: [{ id: 1, sections: [{ id: 11 }, { id: 12 }] }],
  projects: [{ id: 3, key: "ASQ", nodes: [{ id: 30 }] }],
};

test("indexing the bootstrap document", () => {
  const lookup = indexBoot(BOOT);
  assert.equal(lookup.people.get(7).name, "Anna Claes");
  assert.equal(lookup.sections.size, 2);
  assert.equal(lookup.nodes.get(30).project_id, 3);
  assert.equal(lookup.projectByKey.get("ASQ").id, 3);
  assert.equal(lookup.personForUser.id, 7);
});

test("permission reach for showing controls", () => {
  assert.ok(canIn(BOOT.me, "task.view", 99));
  assert.ok(canIn(BOOT.me, "task.edit", 12));
  assert.ok(!canIn(BOOT.me, "task.edit", 13));
  assert.ok(canSomewhere(BOOT.me, "task.edit"));
  assert.ok(!canSomewhere(BOOT.me, "users.manage"));
  assert.ok(!canIn(BOOT.me, "task.delete"));
});
