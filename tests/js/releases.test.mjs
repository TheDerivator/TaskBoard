// Unit tests for static/js/lib/releases.js: versions in links and the release bar's wording.
import assert from "node:assert/strict";
import { test } from "node:test";

import { documentsText, draftText, parseRelease, releasedText, releaseLabel, versionOptions } from "../../taskboard/static/js/lib/releases.js";

const V3 = { number: 3, label: "v3", note: "", released_by: { display_name: "Anna Claes" }, released_at: "2026-09-12T14:00:00Z", items: 40 };
const V2 = { ...V3, number: 2, label: "v2", released_at: "2026-03-03T14:00:00Z" };
const entries = (n) => Array.from({ length: n }, (_, i) => ({ box_key: `b${i}` }));

test("versions in links", () => {
  assert.equal(parseRelease("v3"), 3);
  assert.equal(parseRelease("V12"), 12);
  assert.equal(parseRelease("3"), 3);
  assert.equal(parseRelease("latest"), null);
  assert.equal(parseRelease(null), null);
  assert.equal(releaseLabel(4), "v4");
});

test("the release bar's wording (the FmeaMap mockup)", () => {
  assert.equal(draftText({ base: 3, entries: entries(4) }), "Draft: 4 changes since v3");
  assert.equal(draftText({ base: 3, entries: entries(1) }), "Draft: 1 change since v3");
  assert.equal(draftText({ base: 3, entries: [] }), "No changes since v3");
  assert.equal(draftText({ base: null, entries: entries(7) }), "Not released yet · 7 changes");
  assert.equal(releasedText(V3), "Released 12 Sep 2026 · Anna Claes");
  assert.equal(documentsText({ fmea: 4, cpl: 3 }), "4 affect FMEA, 3 affect CPL");
});

test("the version picker: the current draft, then the releases newest first", () => {
  assert.deepEqual(versionOptions([V3, V2]), [
    { value: "", label: "Current draft" },
    { value: "v3", label: "v3 · 12 Sep 2026" },
    { value: "v2", label: "v2 · 3 Mar 2026" },
  ]);
});
