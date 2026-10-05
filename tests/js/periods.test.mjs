// Unit tests for static/js/lib/periods.js: the same table of states as the server's tests, and wording.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  changeState,
  formatDay,
  formatRange,
  periodChip,
  periodDuration,
  periodSentence,
  periodShape,
  periodSummary,
  stateLabel,
} from "../../taskboard/static/js/lib/periods.js";

const STATES = JSON.parse(readFileSync(new URL("../fixtures/change_states.json", import.meta.url), "utf-8"));

test("the state of a change: the table shared with tests/unit/test_changes.py", () => {
  for (const c of STATES.cases) {
    assert.deepEqual(changeState(c.periods, STATES.today), { state: c.state, date: c.date }, c.name);
    assert.deepEqual(changeState([...c.periods].reverse(), STATES.today), { state: c.state, date: c.date }, `${c.name} (reversed)`);
  }
});

test("dates and ranges are written as in the mockups", () => {
  assert.equal(formatDay("2026-04-14"), "14 Apr");
  assert.equal(formatDay("2026-04-14", { year: true }), "14 Apr 2026");
  assert.equal(formatRange("2026-04-14", "2026-04-14"), "14 Apr");
  assert.equal(formatRange("2026-07-08", "2026-07-10"), "8–10 Jul");
  assert.equal(formatRange("2026-08-25", "2026-09-05"), "25 Aug – 5 Sep");
});

test("the 'Now' wording", () => {
  assert.equal(stateLabel({ state: "in_effect", date: "2026-04-21" }), "In effect since 21 Apr");
  assert.equal(stateLabel({ state: "test_running", date: "2026-10-03" }), "Test running until 3 Oct");
  assert.equal(stateLabel({ state: "planned", date: "2026-10-13" }), "Planned from 13 Oct");
  assert.equal(stateLabel({ state: "tests_ended", date: "2026-06-13" }), "Tests ended 13 Jun");
  assert.equal(stateLabel({ state: "ended", date: "2026-09-30" }), "Ended 30 Sep");
  assert.equal(stateLabel({ state: "no_periods", date: null }), "No periods yet");
});

const oneDay = { kind: "test", start_date: "2026-04-14", end_date: "2026-04-14" };
const twelveDays = { kind: "test", start_date: "2026-08-25", end_date: "2026-09-05" };
const open = { kind: "change", start_date: "2026-04-21", end_date: null };
const ended = { kind: "change", start_date: "2026-04-21", end_date: "2026-09-30" };
const TODAY = "2026-10-03";

test("period chips as in the change list mockup", () => {
  assert.deepEqual(periodChip(open, TODAY), { label: "Change from 21 Apr", tone: "change" });
  assert.deepEqual(periodChip(oneDay, TODAY), { label: "Test 14 Apr", tone: "test" });
  assert.deepEqual(periodChip({ kind: "test", start_date: "2026-07-08", end_date: "2026-07-10" }, TODAY), {
    label: "Test 8–10 Jul",
    tone: "test",
  });
  assert.deepEqual(periodChip(twelveDays, TODAY), { label: "Test 25 Aug – 5 Sep", tone: "test" });
  assert.deepEqual(periodChip({ kind: "test", start_date: "2026-10-13", end_date: "2026-10-17" }, TODAY), {
    label: "Planned test 13–17 Oct",
    tone: "planned-test",
  });
  assert.equal(periodChip({ kind: "change", start_date: "2026-10-20", end_date: null }, TODAY).tone, "planned-change");
  assert.deepEqual(periodChip(ended, TODAY), { label: "Change 21 Apr – 30 Sep", tone: "ended" });
});

test("durations in the drawer and the conversation", () => {
  assert.equal(periodDuration(oneDay), "14 Apr 2026 · 1 day");
  assert.equal(periodDuration(twelveDays), "25 Aug – 5 Sep 2026 · 12 days");
  assert.equal(periodDuration(open), "from 21 Apr 2026 · no end date");
  assert.equal(periodDuration(ended), "21 Apr – 30 Sep 2026 · ended");
  assert.equal(periodDuration({ kind: "test", start_date: "2026-12-28", end_date: "2027-01-03" }), "28 Dec 2026 – 3 Jan 2027 · 7 days");
});

test("a change's shape and its summary", () => {
  assert.equal(periodShape([oneDay, oneDay, open]), "2 tests → process change");
  assert.equal(periodShape([twelveDays]), "1 test");
  assert.equal(periodShape([open]), "process change");
  assert.equal(periodShape([]), "no periods yet");
  assert.equal(periodSummary([oneDay, oneDay, open]), "2 tests, then a permanent process change from 21 Apr 2026.");
  assert.equal(periodSummary([ended]), "A process change from 21 Apr 2026, ended 30 Sep 2026.");
  assert.equal(periodSummary([twelveDays]), "1 test.");
  assert.equal(periodSummary([]), "No periods posted yet.");
});

test("the composer says how the period will show on the timeline", () => {
  const form = (kind, start_date, end_date) => ({ kind, start_date, end_date });
  assert.equal(periodSentence(form("test", "2026-10-12", "2026-10-16")), "Appears on the timeline as a test from 12 to 16 Oct");
  assert.equal(periodSentence(form("test", "2026-09-28", "2026-10-09")), "Appears on the timeline as a test from 28 Sep to 9 Oct");
  assert.equal(periodSentence(form("test", "2026-10-12", "2026-10-12")), "Appears on the timeline as a one-day test on 12 Oct");
  assert.equal(periodSentence(form("change", "2026-10-12", null)), "Appears on the timeline as a permanent process change from 12 Oct");
});
