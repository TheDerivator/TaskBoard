/** People view: one lane per person, cards in team priority order (solid = lead, dashed = helping). */
import { api } from "../api.js";
import { Avatar, StatusPill } from "../components/badges.js";
import { SearchIcon } from "../components/icons.js";
import { showError } from "../components/toasts.js";
import { useSortable } from "../drag.js";
import { useApi, useTitle } from "../hooks.js";
import { reorder } from "../lib/dnd.js";
import { emptyFilters, filterTasks } from "../lib/filters.js";
import { padRank } from "../lib/format.js";
import { buildLanes } from "../lib/lanes.js";
import { canIn } from "../lib/lookup.js";
import { taskPath } from "../lib/routes.js";
import { href } from "../router.js";
import { dataChanged } from "../store.js";
import { html, useEffect, useMemo, useState } from "../ui.js";

let remembered = { q: "", showArchived: false, leadOnly: false };

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

export function PeopleView({ boot, lookup }) {
  useTitle("People");
  const [options, setOptionsState] = useState(remembered);
  const setOptions = (next) => {
    remembered = next;
    setOptionsState(next);
  };
  const { data, error, reload } = useApi("/tasks");
  const [optimistic, setOptimistic] = useState(null);
  useEffect(() => setOptimistic(null), [data]);
  const allTasks = optimistic ?? data?.tasks ?? [];

  const lanes = useMemo(() => {
    const statuses = options.showArchived ? ["idea", "started", "done", "archived"] : emptyFilters().statuses;
    const shown = filterTasks(allTasks, { ...emptyFilters(), q: options.q, statuses });
    const people = boot.people.filter((p) => p.active);
    return buildLanes(people, shown, { leadOnly: options.leadOnly });
  }, [allTasks, options, boot.people]);

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
      ${error && html`<div class="panel empty-state" role="alert">${error.message}</div>`}
      ${!error && !data && html`<div class="panel empty-state">Loading…</div>`}
      ${data &&
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
