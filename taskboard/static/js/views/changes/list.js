/** The list of a process's changes: what and why, periods as chips, the state now, owner, posts. */
import { Avatar } from "../../components/badges.js";
import { shortName } from "../../lib/format.js";
import { periodChip, stateLabel } from "../../lib/periods.js";
import { href } from "../../router.js";
import { html } from "../../ui.js";

const PostsIcon = () => html`
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true">
    <path d="M4 5h16v11H9l-5 4z" />
  </svg>
`;

/** "In effect since 21 Apr" as a pill, coloured by state (and worded, so colour is not the only cue). */
export function StatePill({ state }) {
  return html`<span class=${`state-pill state-pill--${state.state}`}>${stateLabel(state)}</span>`;
}

export function PeriodChip({ period, today }) {
  const chip = periodChip(period, today);
  return html`<span class=${`period-chip period-chip--${chip.tone}`}>${chip.label}</span>`;
}

/** Plain text of a Markdown field for one-line display (the list shows why, not formatted). */
function plain(markdown) {
  return markdown.replace(/[*_`#>]/g, "").replace(/\s+/g, " ").trim();
}

function Row({ change, today, lookup, pathOf }) {
  const owner = lookup.people.get(change.owner_person_id);
  return html`
    <li class="change-row">
      <span class="change-row__key">${change.key}</span>
      <div class="change-row__what">
        <a class="change-row__title" href=${href(pathOf(change))}>${change.title}</a>
        ${change.why_md && html`<span class="change-row__why">${plain(change.why_md)}</span>`}
      </div>
      <div class="change-row__periods" aria-label="Periods">
        ${change.periods.length === 0
          ? html`<span class="muted">No periods yet</span>`
          : change.periods.map((p) => html`<${PeriodChip} key=${p.id} period=${p} today=${today} />`)}
      </div>
      <span class="change-row__now"><${StatePill} state=${change.state} /></span>
      <span class="change-row__owner">
        <${Avatar} person=${owner} />
        <span>${owner ? shortName(owner.name) : "?"}</span>
      </span>
      <span class="change-row__posts" title="Conversation posts" aria-label=${`${change.post_count} posts`}>
        <${PostsIcon} />${change.post_count}
      </span>
    </li>
  `;
}

/**
 * @param {{changes: object[], today: string, lookup: object, pathOf: (change: object) => string}} props
 */
export function ChangeList({ changes, today, lookup, pathOf }) {
  return html`
    <div class="panel change-table">
      <div class="change-table__head" aria-hidden="true">
        <span>ID</span><span>What · why</span><span>Periods</span><span>Now</span><span>Owner</span><span>Posts</span>
      </div>
      <ol class="change-list" aria-label="Process changes, newest first">
        ${changes.map((c) => html`<${Row} key=${c.key} change=${c} today=${today} lookup=${lookup} pathOf=${pathOf} />`)}
      </ol>
    </div>
  `;
}
