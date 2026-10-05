/** The timeline (Gantt) of a process's changes: tests as blue bars, process changes as orange bars
 * with an arrow, planned periods dashed, a line for today; hover or focus shows dates and scope. */
import { formatDay, formatRange, periodDays, periodShape } from "../../lib/periods.js";
import {
  changesInWindow,
  monthTicks,
  periodBar,
  timelineSummary,
  timelineWindow,
  todayX,
  trackSpan,
} from "../../lib/timeline.js";
import { href } from "../../router.js";
import { html, useEffect, useRef, useState } from "../../ui.js";

const LABEL_WIDTH = 300; // the change column
const MIN_TRACK = 560; // narrower screens scroll sideways

/** The track's width in pixels, following the panel's size. */
function useTrackWidth(ref) {
  const [width, setWidth] = useState(800);
  useEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    const measure = () => setWidth(Math.max(MIN_TRACK, Math.floor(element.clientWidth - LABEL_WIDTH)));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return width;
}

/** "in effect since 21 Apr", "14 Apr · 1 day", "25 Aug – 5 Sep · 12 days". */
function duration(period) {
  if (period.end_date == null) return `in effect since ${formatDay(period.start_date)}`;
  const n = periodDays(period);
  return `${formatRange(period.start_date, period.end_date)} · ${n} ${n === 1 ? "day" : "days"}`;
}

function kindLabel(period, today) {
  const planned = period.start_date > today;
  const base = period.kind === "change" ? (planned ? "Planned process change" : "Process change") : planned ? "Planned test" : "Test";
  const own = period.label && period.label !== "Test" && period.label !== "Process change" ? ` · ${period.label}` : "";
  return base + own;
}

function Bar({ change, period, today, frame, width, pathOf }) {
  const [shown, setShown] = useState(false);
  const bar = periodBar(period, frame, today, width);
  const classes = [
    "gantt-bar",
    `gantt-bar--${bar.kind}`,
    bar.planned && "gantt-bar--planned",
    bar.clipped && "gantt-bar--clipped",
  ]
    .filter(Boolean)
    .join(" ");
  const label = `${change.title}, ${kindLabel(period, today)}, ${duration(period)}`;
  const tipLeft = Math.min(Math.max(0, bar.x - 8), width - 260);
  return html`
    <a
      class="gantt-bar__hit"
      href=${href(pathOf(change, "conversation"))}
      aria-label=${label}
      style=${{ left: `${bar.x}px` }}
      onMouseEnter=${() => setShown(true)}
      onMouseLeave=${() => setShown(false)}
      onFocus=${() => setShown(true)}
      onBlur=${() => setShown(false)}
    >
      <span class=${classes} style=${{ width: `${bar.width}px` }}></span>
      ${bar.open && html`<svg class="gantt-bar__arrow" width="10" height="16" viewBox="0 0 10 16" aria-hidden="true"><path d="M0 0L10 8L0 16z" /></svg>`}
    </a>
    ${shown &&
    html`<div class="gantt-tip" role="tooltip" style=${{ left: `${tipLeft}px` }}>
      <span class="gantt-tip__title">${change.key} · ${change.title}</span>
      <span class="gantt-tip__kind">${kindLabel(period, today)}</span>
      <span class="gantt-tip__dates">${duration(period)}</span>
      ${period.scope_tags.length > 0 && html`<span class="gantt-tip__scope">Scope: ${period.scope_tags.join(" · ")}</span>`}
    </div>`}
  `;
}

/**
 * @param {{changes: object[], today: string, months: number, pathOf: Function}} props
 *   `changes` already filtered by search and map box; `pathOf(change, tab)` is a change's path.
 */
export function ChangeTimeline({ changes, today, months, pathOf }) {
  const panel = useRef(null);
  const width = useTrackWidth(panel);
  const frame = timelineWindow(today, months, changes);
  const rows = changesInWindow(changes, frame, today);
  const ticks = monthTicks(frame, width);
  const now = todayX(frame, today, width);
  const first = ticks[0]?.label ?? "";
  const last = ticks[ticks.length - 1]?.label ?? "";
  return html`
    <div class="gantt-legend">
      <span class="gantt-legend__item"><span class="gantt-swatch gantt-swatch--test"></span>Test (has an end date)</span>
      <span class="gantt-legend__item"><span class="gantt-swatch gantt-swatch--change"></span>Process change (no end date)</span>
      <span class="gantt-legend__item"><span class="gantt-swatch gantt-swatch--planned"></span>Planned</span>
      <span class="gantt-legend__item"><span class="gantt-swatch gantt-swatch--today"></span>Today</span>
      <span class="gantt-legend__summary">${timelineSummary(rows)}</span>
    </div>
    <div class="panel gantt" ref=${panel} role="figure" aria-label=${`Timeline of tests and process changes, ${first} to ${last}`}>
      <div class="gantt__scroll">
        <div class="gantt__inner" style=${{ width: `${LABEL_WIDTH + width}px` }}>
          <div class="gantt__head">
            <span class="gantt__label-head">Change</span>
            <div class="gantt__axis" style=${{ width: `${width}px` }}>
              ${ticks.map((t) => html`<span key=${t.iso} class="gantt__month" style=${{ left: `${t.x + 8}px` }}>${t.label}</span>`)}
            </div>
          </div>
          <div class="gantt__body">
            <div class="gantt__grid" aria-hidden="true" style=${{ left: `${LABEL_WIDTH}px`, width: `${width}px` }}>
              ${ticks.map((t) => html`<span key=${t.iso} class="gantt__gridline" style=${{ left: `${t.x}px` }}></span>`)}
              <span class="gantt__today" style=${{ left: `${now}px` }}></span>
              <span class="gantt__today-label" style=${{ left: `${now + 6}px` }}>Today ${formatDay(today)}</span>
            </div>
            ${rows.length === 0 && html`<p class="empty-state">No tests or process changes in this period.</p>`}
            ${rows.map((change) => {
              const span = trackSpan(change.periods, frame, today, width);
              return html`
                <div key=${change.key} class="gantt__row">
                  <a class="gantt__label" href=${href(pathOf(change))}>
                    <span class="gantt__title"><span class="gantt__key">${change.key}</span><span class="gantt__name">${change.title}</span></span>
                    <span class="gantt__shape">${periodShape(change.periods)}</span>
                  </a>
                  <div class="gantt__track" style=${{ width: `${width}px` }}>
                    ${span && html`<span class="gantt__line" style=${{ left: `${span.x}px`, width: `${span.width}px` }}></span>`}
                    ${change.periods.map(
                      (p) => html`<${Bar} key=${p.id} change=${change} period=${p} today=${today} frame=${frame} width=${width} pathOf=${pathOf} />`,
                    )}
                  </div>
                </div>
              `;
            })}
          </div>
        </div>
      </div>
    </div>
  `;
}
