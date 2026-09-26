// Unit tests for static/js/lib/scopes.js: scope choices for role assignments.
import assert from "node:assert/strict";
import { test } from "node:test";

import { parseScope, scopeOptions } from "../../taskboard/static/js/lib/scopes.js";

test("everywhere, then each department followed by its sections", () => {
  const options = scopeOptions([
    { id: 1, code: "STL", sections: [{ id: 11, name: "Quality" }] },
    { id: 2, code: "R&D", sections: [] },
  ]);
  assert.deepEqual(
    options.map((o) => [o.value, o.label]),
    [
      ["global", "Everywhere"],
      ["department:1", "STL (whole department)"],
      ["section:11", "STL · Quality"],
      ["department:2", "R&D (whole department)"],
    ],
  );
});

test("parsing a choice back", () => {
  assert.deepEqual(parseScope("global"), { scope: "global", scope_id: null });
  assert.deepEqual(parseScope("section:11"), { scope: "section", scope_id: 11 });
  assert.deepEqual(parseScope("department:2"), { scope: "department", scope_id: 2 });
});
