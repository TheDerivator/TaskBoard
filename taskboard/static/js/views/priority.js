/** Priority view: every visible task in one team-wide ranked list, with search and filters. */
import { api } from "../api.js";
import { Avatar, ProjectChip, StatusPill, statusLabel } from "../components/badges.js";
import { GripIcon, PlusIcon, SearchIcon } from "../components/icons.js";
import { showError } from "../components/toasts.js";
import { useSortable } from "../drag.js";
import { useApi, useTitle } from "../hooks.js";
import { reorder } from "../lib/dnd.js";
import { emptyFilters, filterTasks, isFiltered, toggleStatus } from "../lib/filters.js";
import { padRank, shortName } from "../lib/format.js";
import { canIn, canSomewhere } from "../lib/lookup.js";
import { taskPath } from "../lib/routes.js";
import { href } from "../router.js";
import { dataChanged } from "../store.js";
import { html, useEffect, useMemo, useRef, useState } from "../ui.js";
import { NewTaskDrawer } from "./task.js";

const LIFECYCLE = ["idea", "started", "done", "archived"];

// Filters survive switching views during a visit, but not a reload.
let rememberedFilters = emptyFilters();

function parseId(value) {
  return value === "" ? null : Number(value);
}

function Filters({ filters, setFilters, boot, lookup }) {
  const sections =
    filters.departmentId == null
      ? boot.departments.flatMap((d) => d.sections)
      : lookup.departments.get(filters.departmentId)?.sections ?? [];

  const setDepartment = (departmentId) => {
    const keepSection =
      filters.sectionId != null &&
      (departmentId == null || lookup.sections.get(filters.sectionId)?.department_id === departmentId);
    setFilters({ ...filters, departmentId, sectionId: keepSection ? filters.sectionId : null });
  };

  return html`
    <div class="filters">
      <label class="search-box">
        <${SearchIcon} />
        <span class="visually-hidden">Search title or description</span>
        <input
          type="search"
          placeholder="Search title or description…"
          value=${filters.q}
          onInput=${(e) => setFilters({ ...filters, q: e.currentTarget.value })}
        />
      </label>
      <div class="chip-group" role="group" aria-label="Lifecycle">
        ${LIFECYCLE.map(
          (status) => html`
            <button
              key=${status}
              type="button"
              class="toggle-chip"
              aria-pressed=${filters.statuses.includes(status) ? "true" : "false"}
              onClick=${() => setFilters({ ...filters, statuses: toggleStatus(filters.statuses, status) })}
            >
              ${statusLabel(status)}
            </button>
          `,
        )}
      </div>
      <div class="filters__selects">
        <label class="field field--compact">
          <span class="field__label">Department</span>
          <select class="select select--compact" onChange=${(e) => setDepartment(parseId(e.currentTarget.value))}>
            <option value="" selected=${filters.departmentId == null}>All</option>
            ${boot.departments.map(
              (d) => html`<option key=${d.id} value=${d.id} selected=${filters.departmentId === d.id}>${d.code}</option>`,
            )}
          </select>
        </label>
        <label class="field field--compact">
          <span class="field__label">Section</span>
          <select
            class="select select--compact"
            onChange=${(e) => setFilters({ ...filters, sectionId: parseId(e.currentTarget.value) })}
          >
            <option value="" selected=${filters.sectionId == null}>All</option>
            ${sections.map(
              (s) => html`<option key=${s.id} value=${s.id} selected=${filters.sectionId === s.id}>${s.name}</option>`,
            )}
          </select>
        </label>
        <label class="field field--compact">
          <span class="field__label">Project</span>
          <select
            class="select select--compact"
            onChange=${(e) => setFilters({ ...filters, projectId: parseId(e.currentTarget.value) })}
          >
            <option value="" selected=${filters.projectId == null}>All</option>
            ${boot.projects.map(
              (p) => html`<option key=${p.id} value=${p.id} selected=${filters.projectId === p.id}>${p.name}</option>`,
            )}
          </select>
        </label>
      </div>
    </div>
  `;
}

export function TaskRow({ task, lookup, draggable = false }) {
  const lead = lookup.people.get(task.lead_id);
  const section = lookup.sections.get(task.section_id);
  const department = lookup.departments.get(task.department_id);
  return html`
    <li class="task-row" data-key=${task.key} data-draggable=${draggable ? "true" : "false"}>
      <span class=${`rank${task.rank <= 3 ? " rank--top" : ""}`} aria-label=${`Rank ${task.rank}`}>${padRank(task.rank)}</span>
      ${draggable
        ? html`<button type="button" class="grip" aria-label=${`Move ${task.ref}, rank ${task.rank}`} aria-describedby="reorder-help" title="Drag, or use the arrow keys, to reorder"><${GripIcon} /></button>`
        : html`<span class="grip"></span>`}
      <div class="task-main">
        <div class="task-main__line">
          <a class="task-title" href=${href(taskPath(task.key))}>${task.title}</a>
          <span class="task-key">${task.ref}</span>
        </div>
        ${task.description && html`<div class="task-desc">${task.description}</div>`}
      </div>
      <div class="task-projects">
        ${task.placements.map(
          (p) => html`<${ProjectChip} key=${p.project_id} project=${lookup.projects.get(p.project_id)} placement=${p} />`,
        )}
      </div>
      <div class="task-people">
        <${Avatar} person=${lead} title=${lead ? `Lead: ${lead.name}` : "Lead"} />
        <span class="task-people__name">${lead ? shortName(lead.name) : "?"}</span>
        <span class="avatar-stack">
          ${task.helper_ids.map((id) => {
            const helper = lookup.people.get(id);
            return html`<${Avatar} key=${id} person=${helper} size="small" ring title=${`Also working on this: ${helper?.name ?? "?"}`} />`;
          })}
        </span>
      </div>
      <div class="task-org">
        <span class="task-org__dept">${department?.code}</span>
        <span class="task-org__section">${section?.name}</span>
      </div>
      <${StatusPill} status=${task.status} />
    </li>
  `;
}

export function PriorityView({ boot, lookup }) {
  useTitle("Priority");
  const [filters, setFiltersState] = useState(rememberedFilters);
  const setFilters = (next) => {
    rememberedFilters = next;
    setFiltersState(next);
  };
  const { data, error, loading } = useApi("/tasks");
  const [optimistic, setOptimistic] = useState(null); // the order shown while a move is saved
  const [creating, setCreating] = useState(false);
  useEffect(() => setOptimistic(null), [data]);
  const tasks = optimistic ?? data?.tasks ?? [];
  const shown = useMemo(() => filterTasks(tasks, filters), [tasks, filters]);
  const canCreate = canSomewhere(boot.me, "task.edit");
  const canDrag = (task) => canIn(boot.me, "task.edit", task.section_id);

  // Moves are saved one at a time, in order, so quick key presses cannot overtake each other;
  // the board reloads once they are all saved (or one failed: then it shows the server's order).
  const saving = useRef({ queue: Promise.resolve(), pending: 0 });
  const sortableRef = useSortable({
    enabled: canCreate,
    onDrop: (dragged, target, where) => {
      setOptimistic((current) => reorder(current ?? data.tasks, dragged, target, where));
      const s = saving.current;
      s.pending += 1;
      s.queue = s.queue
        .then(() => api.post(`/tasks/${dragged}/move`, { target, where }))
        .catch(showError)
        .finally(() => {
          s.pending -= 1;
          if (s.pending === 0) dataChanged();
        });
    },
  });

  return html`
    <section class="page" aria-labelledby="priority-title">
      <header class="view-head">
        <div class="view-head__text">
          <h1 id="priority-title">Priority</h1>
          <p>Every task the team owns, ranked.${canCreate ? " Drag a row to change its priority." : ""}</p>
          <p id="reorder-help" class="visually-hidden">Arrow Up and Arrow Down move the task one place, Home and End to the top or bottom of the list.</p>
        </div>
        ${canCreate && html`<button type="button" class="btn btn--primary" onClick=${() => setCreating(true)}><${PlusIcon} />New task</button>`}
      </header>

      <${Filters} filters=${filters} setFilters=${setFilters} boot=${boot} lookup=${lookup} />

      <div class="panel task-table">
        <div class="task-table__head" aria-hidden="true">
          <span>Rank</span><span></span><span>Task</span><span>Projects</span><span>Lead · team</span>
          <span>Dept · section</span><span>Lifecycle</span>
        </div>
        ${error && html`<div class="empty-state" role="alert">${error.message}</div>`}
        ${!error && loading && !data && html`<div class="empty-state">Loading tasks…</div>`}
        ${!error &&
        data &&
        (shown.length === 0
          ? html`<div class="empty-state">No tasks match this search and lifecycle filter.</div>`
          : html`
              <ol ref=${sortableRef} class=${`task-list${canCreate ? " task-list--sortable" : ""}`} aria-label="Tasks by team priority">
                ${shown.map((task) => html`<${TaskRow} key=${task.key} task=${task} lookup=${lookup} draggable=${canDrag(task)} />`)}
              </ol>
            `)}
      </div>
      ${data &&
      html`<div class="row count-note">
        <p aria-live="polite">Showing ${shown.length} of ${data.total} tasks · rank is team-wide, filters never change it</p>
        ${isFiltered(filters) &&
        html`<button type="button" class="link-button" onClick=${() => setFilters(emptyFilters())}>Reset filters</button>`}
      </div>`}
      ${creating && html`<${NewTaskDrawer} onClose=${() => setCreating(false)} />`}
    </section>
  `;
}
