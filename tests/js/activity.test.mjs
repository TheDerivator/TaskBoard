// Unit tests for static/js/lib/activity.js: day headings, grouping by day, and post times.
import assert from "node:assert/strict";
import { test } from "node:test";

import { dayGroups, dayLabel, postTime } from "../../taskboard/static/js/lib/activity.js";

const NOW = new Date(2026, 9, 3, 10, 30); // Saturday 3 Oct 2026, 10:30 local time

test("day headings: today, yesterday, then the date (with the year only when it differs)", () => {
  assert.equal(dayLabel(new Date(2026, 9, 3, 0, 1), NOW), "Today");
  assert.equal(dayLabel(new Date(2026, 9, 3, 11, 0), NOW), "Today"); // a clock a little behind
  assert.equal(dayLabel(new Date(2026, 9, 2, 23, 59), NOW), "Yesterday");
  assert.equal(dayLabel(new Date(2026, 9, 1, 12, 0), NOW), "1 Oct");
  assert.equal(dayLabel(new Date(2025, 11, 31, 12, 0), NOW), "31 Dec 2025");
  assert.equal(dayLabel(new Date(2026, 9, 2, 9, 10).toISOString(), NOW), "Yesterday"); // ISO text
});

test("a day crossing a daylight-saving change is still one day", () => {
  const afterChange = new Date(2026, 9, 26, 9, 0); // Europe: clocks went back on 25 Oct
  assert.equal(dayLabel(new Date(2026, 9, 25, 9, 0), afterChange), "Yesterday");
  assert.equal(dayLabel(new Date(2026, 9, 24, 9, 0), afterChange), "24 Oct");
});

test("items are grouped by day in the order given", () => {
  const item = (key, at) => ({ key, last_post: { created_at: at.toISOString() } });
  const items = [
    item("a", new Date(2026, 9, 3, 9, 0)),
    item("b", new Date(2026, 9, 3, 8, 0)),
    item("c", new Date(2026, 9, 2, 17, 0)),
    item("d", new Date(2026, 8, 19, 14, 2)),
    item("e", new Date(2026, 8, 19, 9, 0)),
  ];
  const groups = dayGroups(items, NOW);
  assert.deepEqual(
    groups.map((g) => [g.label, g.items.map((i) => i.key)]),
    [
      ["Today", ["a", "b"]],
      ["Yesterday", ["c"]],
      ["19 Sep", ["d", "e"]],
    ],
  );
  assert.deepEqual(dayGroups([], NOW), []);
});

test("post times: just now, minutes ago, else the time of day under the day's heading", () => {
  assert.equal(postTime(new Date(2026, 9, 3, 10, 29, 31), NOW), "just now");
  assert.equal(postTime(new Date(2026, 9, 3, 10, 31), NOW), "just now"); // a clock a little behind
  assert.equal(postTime(new Date(2026, 9, 3, 10, 18), NOW), "12 min ago");
  assert.equal(postTime(new Date(2026, 9, 3, 9, 31), NOW), "59 min ago");
  assert.equal(postTime(new Date(2026, 9, 3, 9, 30), NOW), "09:30");
  assert.equal(postTime(new Date(2026, 8, 19, 14, 2), NOW), "14:02");
});
