/** People view: one lane per person of a team (everyone, a department or a section), cards in team priority order. */
import { api } from "../api.js";
import { Avatar, StatusPill } from "../components/badges.js";
import { CopyLinkButton } from "../components/copy-link.js";
import { SearchIcon } from "../components/icons.js";
import { showError } from "../components/toasts.js";
import { useSortable } from "../drag.js";
import { useApi, useTitle } from "../hooks.js";
import { reorder } from "../lib/dnd.js";
import { emptyFilters, filterTasks } from "../lib/filters.js";
import { padRank } from "../lib/format.js";
import { buildLanes } from "../lib/lanes.js";
import { canIn } from "../lib/lookup.js";
import { peoplePath, routePath, taskPath } from "../lib/routes.js";
import { findTeam, teamLabel, teamMembers, teamPath } from "../lib/teams.js";
import { href, navigate } from "../router.js";
import { dataChanged } from "../store.js";
import { html, useEffect, useMemo, useState } from "../ui.js";

let remembered = { q: "", showArchived: false, leadOnly: false };

/** Every team has its own URL, so choosing one changes the address: that is the bookmark. */
function TeamPicker({ departments, team, requested }) {
  const current = team ? teamPath(team) : requested;
  const option = (path, label) => html`<option key=${path} value=${path} selected=${current === path}>${label}</option>`;
  return html`
    <label class="field field--compact">
      <span class="field__label">Team</span>
      <select class="select select--compact" onChange=${(e) => navigate(e.currentTarget.value)}>
        ${!team && html`<option value=${requested} selected disabled>Unknown team</option>`}
        ${option(peoplePath(), "Everyone")}
        ${departments.map(
          (d) => html`
            <optgroup key=${d.id} label=${d.code}>
              ${option(peoplePath(d.code), `${d.code} (whole department)`)}
              ${d.sections.map((s) => option(peoplePath(d.code, s.name), `${d.code} · ${s.name}`))}
            </optgroup>
          `,
        )}
      </select>
    </label>
  `;
}

function Card({ task, role, lookup, draggable }) {
  const top = task.rank <= 3;
  return html`
    <li data-key=${task.key} data-draggable=${draggable ? "true" : "false"}>
      <a class=${`card card--${role}`} href=${href(taskPath(task.key))} draggable="false" data-drag-surface>
        <span class="card__top">
          <span class=${`card__rank${top ? " card__rank--top" : ""}`}>#${padRank(task.rank)}</span>
          <${StatusPill} status=${task.status} small />
        </span>
        <span class="card__title">${task.title}</span>
        <span class="card__bottom">
          <span class="card__dots">
            ${task.placements.map((p) => {
              const project = lookup.projects.get(p.project_id);
              return html`<span key=${p.project_id} class="project-dot" title=${project?.name} style=${{ "--project-color": project?.color }}></span>`;
            })}
          </span>
          <span class="card__role">${role === "lead" ? "Lead" : "Helping"}</span>
        </span>
      </a>
    </li>
  `;
}

function Lane({ lane, lookup, me, allTasks, setOptimistic, reload }) {
  const editable = (task) => canIn(me, "task.edit", task.section_id);
  const sortableRef = useSortable({
    enabled: lane.cards.some((c) => editable(c.task)),
    onDrop: async (dragged, target, where) => {
      setOptimistic(reorder(allTasks, dragged, target, where));
      try {
        await api.post(`/tasks/${dragged}/move`, { target, where });
        dataChanged();
      } catch (err) {
        showError(err);
        setOptimistic(null);
        reload();
      }
    },
  });
  const { person } = lane;
  return html`
    <section class="lane" aria-label=${person.name}>
      <header class="lane__head">
        <${Avatar} person=${person} />
        <div class="lane__who">
          <span class="lane__name">${person.name}</span>
          <span class="lane__counts">${lane.lead} lead · ${lane.helping} helping</span>
        </div>
      </header>
      ${lane.cards.length === 0
        ? html`<p class="lane__empty">Nothing here.</p>`
        : html`
            <ol ref=${sortableRef} class="lane__cards lane__cards--sortable">
              ${lane.cards.map(
                (c) => html`<${Card} key=${c.task.key} task=${c.task} role=${c.role} lookup=${lookup} draggable=${editable(c.task)} />`,
              )}
            </ol>
          `}
    </section>
  `;
}

export function PeopleView({ boot, lookup, route }) {
  const { department, section } = route.params;
  const team = useMemo(() => findTeam(boot.departments, { department, section }), [boot.departments, department, section]);
  const label = team && teamLabel(team);
  useTitle(team?.department ? `People · ${label}` : "People");

  // Links are forgiving about case (/people/stl/quality); the address then shows the real spelling.
  const canonical = team && teamPath(team);
  useEffect(() => {
    if (canonical && canonical !== routePath(route)) navigate(canonical, { replace: true });
  }, [canonical, route]);

  const [options, setOptionsState] = useState(remembered);
  const setOptions = (next) => {
    remembered = next;
    setOptionsState(next);
  };
  const { data, error, reload } = useApi("/tasks");
  const [optimistic, setOptimistic] = useState(null);
  useEffect(() => setOptimistic(null), [data]);
  const allTasks = optimistic ?? data?.tasks ?? [];

  // A lane shows all of the person's tasks, also those of other sections: the team filters people only.
  const lanes = useMemo(() => {
    if (!team) return [];
    const statuses = options.showArchived ? ["idea", "started", "done", "archived"] : emptyFilters().statuses;
    const shown = filterTasks(allTasks, { ...emptyFilters(), q: options.q, statuses });
    const people = teamMembers(boot.people.filter((p) => p.active), team);
    return buildLanes(people, shown, { leadOnly: options.leadOnly });
  }, [allTasks, options, boot.people, team]);

  return html`
    <section class="page" aria-labelledby="people-title">
      <header class="view-head">
        <div class="view-head__text">
          <h1 id="people-title">People</h1>
          <p>One lane per person, in team priority order. Solid cards are tasks they lead; outlined cards are tasks they help on.</p>
        </div>
        <div class="segmented" role="group" aria-label="Show">
          <button type="button" aria-pressed=${options.leadOnly ? "false" : "true"} onClick=${() => setOptions({ ...options, leadOnly: false })}>
            Lead + helping
          </button>
          <button type="button" aria-pressed=${options.leadOnly ? "true" : "false"} onClick=${() => setOptions({ ...options, leadOnly: true })}>
            Lead only
          </button>
        </div>
      </header>
      <div class="people-filters">
        <div class="people-filters__team">
          <${TeamPicker} departments=${boot.departments} team=${team} requested=${routePath(route)} />
          ${team?.department && html`<${CopyLinkButton} path=${teamPath(team)} label=${`Copy link to ${label}`} />`}
        </div>
        <label class="search-box">
          <${SearchIcon} />
          <input
            type="search"
            aria-label="Search title or description"
            placeholder="Search title or description…"
            value=${options.q}
            onInput=${(e) => setOptions({ ...options, q: e.currentTarget.value })}
          />
        </label>
        <button
          type="button"
          class="toggle-chip"
          aria-pressed=${options.showArchived ? "true" : "false"}
          onClick=${() => setOptions({ ...options, showArchived: !options.showArchived })}
        >
          Show archived
        </button>
      </div>
      ${!team &&
      html`<div class="panel empty-state" role="alert">
        There is no team “${[department, section].filter(Boolean).join(" · ")}”; it may have been renamed. Choose one from the Team list.
      </div>`}
      ${team && error && html`<div class="panel empty-state" role="alert">${error.message}</div>`}
      ${team && !error && !data && html`<div class="panel empty-state">Loading…</div>`}
      ${team && data && lanes.length === 0 && html`<div class="panel empty-state">No one in ${label} yet.</div>`}
      ${data &&
      lanes.length > 0 &&
      html`<div class="lanes">
        ${lanes.map(
          (lane) =>
            html`<${Lane}
              key=${lane.person.id}
              lane=${lane}
              lookup=${lookup}
              me=${boot.me}
              allTasks=${allTasks}
              setOptimistic=${setOptimistic}
              reload=${reload}
            />`,
        )}
      </div>`}
    </section>
  `;
}
