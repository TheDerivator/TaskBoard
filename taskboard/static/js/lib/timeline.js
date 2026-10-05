/** The process-change timeline (Gantt), pure: the window shown, which changes, and the bars.
 * Dates are ISO strings ("2026-10-03"); positions are pixels in a track `width` wide. */

const DAY_MS = 86_400_000;

/** Days since 1970-01-01 (UTC), so date arithmetic ignores time zones and summer time. */
export function dayNumber(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, m - 1, d) / DAY_MS;
}

export function isoOfDay(day) {
  return new Date(day * DAY_MS).toISOString().slice(0, 10);
}

function firstOfMonth(iso, monthsLater = 0) {
  const [y, m] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1 + monthsLater, 1));
  return date.toISOString().slice(0, 10);
}

/**
 * The window: from the first day of the month `months` back, to the start of the month after
 * next (the coming weeks), stretched to show the last planned period in full.
 * @returns {{start: string, end: string}} `end` is exclusive
 */
export function timelineWindow(today, months, changes = []) {
  const start = firstOfMonth(today, -months);
  let end = firstOfMonth(today, 1);
  for (const change of changes) {
    for (const p of change.periods) {
      const last = p.end_date ?? p.start_date;
      if (p.start_date > today && last >= end) end = firstOfMonth(last, 1);
    }
  }
  return { start, end };
}

/**
 * DESIGN rule 7: the changes with a period starting in the window, plus those with a planned one.
 * Earliest first period first (then by key), as the mockup lists them.
 */
export function changesInWindow(changes, window, today) {
  const shown = changes.filter((c) =>
    c.periods.some((p) => (p.start_date >= window.start && p.start_date < window.end) || p.start_date > today),
  );
  const first = (c) => c.periods.reduce((min, p) => (p.start_date < min ? p.start_date : min), "9999-12-31");
  return shown.sort((a, b) => first(a).localeCompare(first(b)) || a.key.localeCompare(b.key));
}

/** Month boundaries inside the window: `{iso, label, x}`; the first label carries the year. */
export function monthTicks(window, width) {
  const scale = pixelsPerDay(window, width);
  const ticks = [];
  for (let iso = window.start; iso < window.end; iso = firstOfMonth(iso, 1)) {
    const date = new Date(`${iso}T00:00:00Z`);
    const month = date.toLocaleString("en", { month: "short", timeZone: "UTC" });
    const label = ticks.length === 0 || iso.endsWith("-01-01") ? `${month} ${date.getUTCFullYear()}` : month;
    ticks.push({ iso, label, x: Math.round((dayNumber(iso) - dayNumber(window.start)) * scale) });
  }
  return ticks;
}

export function pixelsPerDay(window, width) {
  return width / (dayNumber(window.end) - dayNumber(window.start));
}

/** Where "today" is on the track. */
export function todayX(window, today, width) {
  return Math.round((dayNumber(today) - dayNumber(window.start)) * pixelsPerDay(window, width));
}

/**
 * A period's bar. Tests run to the end of their last day (inclusive). A process change without
 * an end date runs to the right edge and gets an arrow (`open`); an ended one stops at its end.
 * Bars starting before the window are cut at its left edge (`clipped`); planned ones are dashed.
 * @returns {{x: number, width: number, open: boolean, planned: boolean, clipped: boolean, kind: string}}
 */
export function periodBar(period, window, today, width, { arrow = 10, minimum = 6 } = {}) {
  const scale = pixelsPerDay(window, width);
  const origin = dayNumber(window.start);
  const startDay = Math.max(dayNumber(period.start_date), origin);
  const x = (startDay - origin) * scale;
  const open = period.kind === "change" && period.end_date == null;
  let barWidth;
  if (open) {
    barWidth = width - x - arrow;
  } else {
    const endDay = Math.min(dayNumber(period.end_date) + 1, dayNumber(window.end));
    barWidth = (endDay - startDay) * scale;
  }
  return {
    x,
    width: Math.max(minimum, barWidth),
    open,
    planned: period.start_date > today,
    clipped: dayNumber(period.start_date) < origin,
    kind: period.kind,
  };
}

/** The faint line joining a change's first and last bar. */
export function trackSpan(periods, window, today, width) {
  if (periods.length === 0) return null;
  const bars = periods.map((p) => periodBar(p, window, today, width));
  const left = Math.min(...bars.map((b) => b.x));
  const right = Math.max(...bars.map((b) => b.x + b.width + (b.open ? 10 : 0)));
  return { x: left, width: Math.max(0, right - left) };
}

/** Counts for the legend line: "6 changes · 9 test periods · 3 process changes". */
export function timelineSummary(changes) {
  let tests = 0;
  let permanent = 0;
  for (const change of changes) {
    for (const p of change.periods) {
      if (p.kind === "test") tests += 1;
      else permanent += 1;
    }
  }
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  return [
    plural(changes.length, "change", "changes"),
    plural(tests, "test period", "test periods"),
    plural(permanent, "process change", "process changes"),
  ].join(" · ");
}
