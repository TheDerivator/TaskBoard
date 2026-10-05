/** Process-change periods (pure): a change's derived state and its wording. Same rules as the
 * server's domain/changes.py; both are tested against tests/fixtures/change_states.json. Dates are
 * ISO strings ("2026-10-03"), which compare correctly as text. */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * The first rule that matches wins: in effect, test running, planned, no periods, ended.
 * @param {{kind: "test"|"change", start: string, end: ?string}[]} periods
 * @param {string} today  "YYYY-MM-DD" (the server's date, from the bootstrap)
 * @returns {{state: string, date: ?string}}
 */
export function changeState(periods, today) {
  const inEffect = periods.filter((p) => p.kind === "change" && p.start <= today && (p.end == null || p.end >= today));
  if (inEffect.length) return { state: "in_effect", date: min(inEffect.map((p) => p.start)) };
  const running = periods.filter((p) => p.kind === "test" && p.end != null && p.start <= today && today <= p.end);
  if (running.length) return { state: "test_running", date: max(running.map((p) => p.end)) };
  const planned = periods.filter((p) => p.start > today);
  if (planned.length) return { state: "planned", date: min(planned.map((p) => p.start)) };
  if (periods.length === 0) return { state: "no_periods", date: null };
  // Everything is over: every period has an end date before today. The last one decides.
  const last = periods.reduce((a, b) => (later(b, a) ? b : a));
  return { state: last.kind === "change" ? "ended" : "tests_ended", date: last.end };
}

function later(a, b) {
  const ae = a.end ?? a.start;
  const be = b.end ?? b.start;
  if (ae !== be) return ae > be;
  return a.kind === "change" && b.kind !== "change";
}

const min = (dates) => dates.reduce((a, b) => (b < a ? b : a));
const max = (dates) => dates.reduce((a, b) => (b > a ? b : a));

/** "2026-04-14" → "14 Apr" (with the year: "14 Apr 2026"). */
export function formatDay(iso, { year = false } = {}) {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]}${year ? ` ${y}` : ""}`;
}

/** "14 Apr", "8–10 Jul", "25 Aug – 5 Sep" (the mockup's way of writing a period). */
export function formatRange(start, end) {
  if (end == null || start === end) return formatDay(start);
  if (start.slice(0, 7) === end.slice(0, 7)) return `${Number(start.slice(8))}–${formatDay(end)}`;
  return `${formatDay(start)} – ${formatDay(end)}`;
}

/** "14 Apr 2026", "8–10 Jul 2026", "28 Dec 2026 – 3 Jan 2027": a range with its year. */
export function formatRangeWithYear(start, end) {
  if (end == null || start === end) return formatDay(start, { year: true });
  if (start.slice(0, 4) !== end.slice(0, 4)) return `${formatDay(start, { year: true })} – ${formatDay(end, { year: true })}`;
  return `${formatRange(start, end)} ${start.slice(0, 4)}`;
}

/** Days in a period, both ends included; null while a process change has no end. */
export function periodDays(period) {
  if (period.end_date == null) return null;
  return (Date.parse(`${period.end_date}T00:00:00Z`) - Date.parse(`${period.start_date}T00:00:00Z`)) / 86_400_000 + 1;
}

/** "14 Apr 2026 · 1 day", "from 21 Apr 2026 · no end date", "21 Apr – 30 Sep 2026 · ended". */
export function periodDuration(period) {
  if (period.kind === "change") {
    if (period.end_date == null) return `from ${formatDay(period.start_date, { year: true })} · no end date`;
    return `${formatRangeWithYear(period.start_date, period.end_date)} · ended`;
  }
  const days = periodDays(period);
  return `${formatRangeWithYear(period.start_date, period.end_date)} · ${days} ${days === 1 ? "day" : "days"}`;
}

/**
 * A period as a chip in the change list (ChangesList mockup): its wording and its look.
 * Tones: test, change (in effect), planned-test, planned-change (dashed), ended (a process change
 * that was ended).
 */
export function periodChip(period, today) {
  const planned = period.start_date > today;
  if (period.kind === "change") {
    if (planned) return { label: `Planned change from ${formatDay(period.start_date)}`, tone: "planned-change" };
    if (period.end_date == null) return { label: `Change from ${formatDay(period.start_date)}`, tone: "change" };
    return { label: `Change ${formatRange(period.start_date, period.end_date)}`, tone: "ended" };
  }
  const range = formatRange(period.start_date, period.end_date);
  return planned ? { label: `Planned test ${range}`, tone: "planned-test" } : { label: `Test ${range}`, tone: "test" };
}

/** A change's shape under its name in the timeline: "2 tests → process change". */
export function periodShape(periods) {
  const tests = periods.filter((p) => p.kind === "test").length;
  const permanent = periods.some((p) => p.kind === "change");
  const parts = [];
  if (tests) parts.push(`${tests} ${tests === 1 ? "test" : "tests"}`);
  if (permanent) parts.push("process change");
  return parts.join(" → ") || "no periods yet";
}

/** The "At a glance" sentence: "2 tests, then a permanent process change from 21 Apr 2026." */
export function periodSummary(periods) {
  if (periods.length === 0) return "No periods posted yet.";
  const tests = periods.filter((p) => p.kind === "test");
  const permanent = periods.filter((p) => p.kind === "change");
  const testText = tests.length ? `${tests.length} ${tests.length === 1 ? "test" : "tests"}` : "";
  if (!permanent.length) return `${testText[0].toUpperCase()}${testText.slice(1)}.`;
  const last = permanent[permanent.length - 1];
  const change =
    last.end_date == null
      ? `a permanent process change from ${formatDay(last.start_date, { year: true })}`
      : `a process change from ${formatDay(last.start_date, { year: true })}, ended ${formatDay(last.end_date, { year: true })}`;
  const sentence = testText ? `${testText}, then ${change}` : change;
  return `${sentence[0].toUpperCase()}${sentence.slice(1)}.`;
}

/** The composer's live sentence: "Appears on the timeline as a test from 12 to 16 Oct". */
export function periodSentence(form) {
  if (!form.start_date) return "";
  if (form.kind === "change") {
    if (form.end_date) return `Appears on the timeline as a process change from ${formatDay(form.start_date)} to ${formatDay(form.end_date)}`;
    return `Appears on the timeline as a permanent process change from ${formatDay(form.start_date)}`;
  }
  if (!form.end_date || form.end_date === form.start_date) return `Appears on the timeline as a one-day test on ${formatDay(form.start_date)}`;
  const sameMonth = form.start_date.slice(0, 7) === form.end_date.slice(0, 7);
  const from = sameMonth ? String(Number(form.start_date.slice(8))) : formatDay(form.start_date);
  return `Appears on the timeline as a test from ${from} to ${formatDay(form.end_date)}`;
}

/** "In effect since 21 Apr", "Test running until 3 Oct", ... (the list's "Now" column). */
export function stateLabel({ state, date }) {
  switch (state) {
    case "in_effect":
      return `In effect since ${formatDay(date)}`;
    case "test_running":
      return `Test running until ${formatDay(date)}`;
    case "planned":
      return `Planned from ${formatDay(date)}`;
    case "tests_ended":
      return `Tests ended ${formatDay(date)}`;
    case "ended":
      return `Ended ${formatDay(date)}`;
    default:
      return "No periods yet";
  }
}
