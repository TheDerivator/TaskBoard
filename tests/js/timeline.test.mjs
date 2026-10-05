// Unit tests for static/js/lib/timeline.js: the window, which changes it shows, and bar geometry.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  changesInWindow,
  dayNumber,
  monthTicks,
  periodBar,
  timelineSummary,
  timelineWindow,
  todayX,
  trackSpan,
} from "../../taskboard/static/js/lib/timeline.js";

const TODAY = "2026-10-03";
const change = (key, ...periods) => ({
  key,
  periods: periods.map(([kind, start_date, end_date]) => ({ kind, start_date, end_date })),
});
// The ChangesGantt mockup: Ladle metallurgy.
const LM = [
  change("LM-07", ["test", "2026-04-14", "2026-04-14"], ["test", "2026-04-16", "2026-04-16"], ["change", "2026-04-21", null]),
  change("LM-08", ["test", "2026-05-05", "2026-05-16"], ["test", "2026-06-02", "2026-06-13"]),
  change("LM-09", ["change", "2026-05-12", null]),
  change("LM-10", ["test", "2026-07-08", "2026-07-10"], ["change", "2026-08-01", null]),
  change("LM-11", ["test", "2026-08-25", "2026-09-05"], ["test", "2026-09-22", "2026-10-03"]),
  change("LM-12", ["test", "2026-10-13", "2026-10-17"]),
];

test("the window: the last months plus the coming weeks (the mockup: 1 Apr to 1 Nov)", () => {
  assert.deepEqual(timelineWindow(TODAY, 6, LM), { start: "2026-04-01", end: "2026-11-01" });
  assert.deepEqual(timelineWindow(TODAY, 3, LM), { start: "2026-07-01", end: "2026-11-01" });
  assert.deepEqual(timelineWindow("2026-01-15", 12), { start: "2025-01-01", end: "2026-02-01" });
  // A planned period beyond the coming weeks stretches the window to show it in full.
  const far = [change("X-1", ["test", "2026-12-01", "2026-12-04"])];
  assert.deepEqual(timelineWindow(TODAY, 6, far), { start: "2026-04-01", end: "2027-01-01" });
});

test("DESIGN rule 7: changes with a period starting in the window, and planned ones", () => {
  const recent = timelineWindow(TODAY, 3, LM);
  assert.deepEqual(changesInWindow(LM, recent, TODAY).map((c) => c.key), ["LM-10", "LM-11", "LM-12"]);
  const all = timelineWindow(TODAY, 6, LM);
  const keys = changesInWindow([...LM].reverse(), all, TODAY).map((c) => c.key);
  assert.deepEqual(keys, ["LM-07", "LM-08", "LM-09", "LM-10", "LM-11", "LM-12"]);
  const old = change("LM-01", ["change", "2025-01-10", null]);
  assert.deepEqual(changesInWindow([old], all, TODAY), []);
});

test("months and today on an 800 px track", () => {
  const frame = timelineWindow(TODAY, 6, LM);
  const ticks = monthTicks(frame, 800);
  assert.deepEqual(ticks.map((t) => t.label), ["Apr 2026", "May", "Jun", "Jul", "Aug", "Sep", "Oct"]);
  assert.equal(ticks[0].x, 0);
  assert.ok(ticks[6].x > ticks[5].x && ticks[6].x < 800);
  const days = dayNumber("2026-11-01") - dayNumber("2026-04-01"); // 214
  assert.equal(todayX(frame, TODAY, 800), Math.round(((dayNumber(TODAY) - dayNumber("2026-04-01")) * 800) / days));
});

test("bars: tests include their last day, open changes run to the edge, planned ones are dashed", () => {
  const frame = { start: "2026-04-01", end: "2026-11-01" }; // 214 days
  const perDay = 800 / 214;
  const oneDay = periodBar({ kind: "test", start_date: "2026-04-14", end_date: "2026-04-14" }, frame, TODAY, 800);
  assert.equal(oneDay.width, 6); // at least 6 px, so a one-day test stays visible
  const twelve = periodBar({ kind: "test", start_date: "2026-08-25", end_date: "2026-09-05" }, frame, TODAY, 800);
  assert.ok(Math.abs(twelve.width - 12 * perDay) < 1e-9);
  const open = periodBar({ kind: "change", start_date: "2026-04-21", end_date: null }, frame, TODAY, 800);
  assert.ok(open.open && Math.abs(open.x + open.width - 790) < 1e-9);
  const planned = periodBar({ kind: "test", start_date: "2026-10-13", end_date: "2026-10-17" }, frame, TODAY, 800);
  assert.ok(planned.planned && !planned.open);
  const early = periodBar({ kind: "change", start_date: "2026-01-10", end_date: "2026-04-30" }, frame, TODAY, 800);
  assert.ok(early.clipped && early.x === 0);
});

test("the faint line joins the first and the last bar", () => {
  const frame = { start: "2026-04-01", end: "2026-11-01" };
  const span = trackSpan(LM[0].periods, frame, TODAY, 800);
  assert.ok(span.x > 0 && Math.abs(span.x + span.width - 800) < 1e-9);
  assert.equal(trackSpan([], frame, TODAY, 800), null);
});

test("the legend's summary", () => {
  assert.equal(timelineSummary(LM), "6 changes · 8 test periods · 3 process changes");
  assert.equal(timelineSummary([LM[2]]), "1 change · 0 test periods · 1 process change");
});
