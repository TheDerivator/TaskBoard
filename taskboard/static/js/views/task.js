/** The task: a drawer over the list, or its own page at /t/{key}; plus the "New task" drawer. */
import { api, ApiError } from "../api.js";
import { BoxLinksField } from "../components/box-links-field.js";
import { Drawer } from "../components/drawer.js";
import { ConversationPanel } from "../components/conversation.js";
import { CopyLinkButton } from "../components/copy-link.js";
import { CloseIcon } from "../components/icons.js";
import { PlacementDialog } from "../components/placement-dialog.js";
import {
  FieldLabel,
  HelpersField,
  LeadField,
  LifecyclePicker,
  OrgFields,
  PlacementsField,
} from "../components/task-fields.js";
import { showError, showToast } from "../components/toasts.js";
import { useApi, useTitle } from "../hooks.js";
import { padRank } from "../lib/format.js";
import { canIn, canSomewhere } from "../lib/lookup.js";
import { taskPath } from "../lib/routes.js";
import { href, navigate } from "../router.js";
import { dataChanged, refreshBoot, useAppState } from "../store.js";
import { html, useEffect, useRef, useState } from "../ui.js";

function draftOf(task) {
  return {
    title: task.title,
    description: task.description,
    status: task.status,
    section_id: task.section_id,
    lead_id: task.lead_id,
    helper_ids: [...task.helper_ids],
  };
}

function changedFields(draft, task) {
  const changes = {};
  for (const [field, value] of Object.entries(draft)) {
    const before = task[field];
    const same = Array.isArray(value) ? value.join() === before.join() : value === before;
    if (!same) changes[field] = value;
  }
  return changes;
}

/** The fields shared by the edit and create forms. */
function TaskFields({ draft, setDraft, boot, lookup, readOnly }) {
  const set = (patch) => setDraft({ ...draft, ...patch });
  return html`
    ${readOnly
      ? html`
          <div class="field"><${FieldLabel}>Title<//><h2 class="read-title">${draft.title}</h2></div>
          <div class="field">
            <${FieldLabel}>Description<//>
            <p class="read-text">${draft.description || html`<span class="muted">No description.</span>`}</p>
          </div>
        `
      : html`
          <label class="field">
            <${FieldLabel}>Title<//>
            <input class="input input--title" required maxlength="300" value=${draft.title} onInput=${(e) => set({ title: e.currentTarget.value })} />
          </label>
          <label class="field">
            <${FieldLabel}>Description<//>
            <textarea class="textarea" rows="4" value=${draft.description} onInput=${(e) => set({ description: e.currentTarget.value })}></textarea>
          </label>
        `}
    <${LifecyclePicker} value=${draft.status} readOnly=${readOnly} onChange=${(status) => set({ status })} />
    <${OrgFields} sectionId=${draft.section_id} boot=${boot} lookup=${lookup} readOnly=${readOnly} onChange=${(id) => set({ section_id: id })} />
    <${LeadField}
      leadId=${draft.lead_id}
      boot=${boot}
      lookup=${lookup}
      readOnly=${readOnly}
      onChange=${(id) => set({ lead_id: id, helper_ids: draft.helper_ids.filter((h) => h !== id) })}
    />
    <${HelpersField}
      helperIds=${draft.helper_ids}
      leadId=${draft.lead_id}
      boot=${boot}
      lookup=${lookup}
      readOnly=${readOnly}
      onChange=${(ids) => set({ helper_ids: ids })}
    />
  `;
}

/** An existing task: header, tabs, details form (or read-only view), footer. */
export function TaskPanel({ taskKey, tab, onClose, layout, dirtyRef }) {
  const { boot, lookup } = useAppState();
  const { data, error, reload } = useApi(`/tasks/${encodeURIComponent(taskKey)}`);
  const [task, setTask] = useState(null);
  const [draft, setDraft] = useState(null);
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const [placementDialog, setPlacementDialog] = useState(null); // null | {moveProjectId}
  const [updatesOnly, setUpdatesOnly] = useState(false);
  const [postCount, setPostCount] = useState(null);
  const discardDraft = useRef(false);

  // A reload (e.g. after any change elsewhere) must not throw away unsaved edits: keep the draft
  // when it differs from the task as it was loaded before. A conflicting save still gets 409.
  useEffect(() => {
    if (!data) return;
    const keep = !discardDraft.current;
    discardDraft.current = false;
    setDraft((current) =>
      keep && current && task && Object.keys(changedFields(current, task)).length > 0 ? current : draftOf(data),
    );
    setTask(data);
    setStale(false);
  }, [data]);
  useTitle(task ? `${task.ref} ${task.title}` : taskKey);
  const editable = Boolean(task?.permissions.edit);
  const dirty = Boolean(task && draft && editable && Object.keys(changedFields(draft, task)).length > 0);
  // Published during render (not in an effect, which runs after paint) so a close guard that
  // reads it right after a keystroke sees the current value.
  if (dirtyRef) dirtyRef.current = dirty;

  if (error) {
    const missing = error instanceof ApiError && error.status === 404;
    return html`
      <div class="task-panel">
        <div class="task-panel__head"><span class="task-panel__key">T-${String(taskKey).replace(/^T-/i, "")}</span>
          ${onClose && html`<button type="button" class="icon-btn" aria-label="Close" onClick=${onClose}><${CloseIcon} /></button>`}
        </div>
        <div class="task-panel__body">
          <p role="alert">${missing ? "This task doesn't exist, or you don't have access to it." : error.message}</p>
          <a href=${href("priority")}>Go to the priority list</a>
        </div>
      </div>
    `;
  }
  if (!task || !draft) return html`<div class="task-panel"><div class="task-panel__body muted">Loading…</div></div>`;

  const readOnly = !editable;
  const changes = changedFields(draft, task);
  const count = postCount ?? task.post_count;

  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const saved = await api.patch(`/tasks/${task.key}`, { version: task.version, ...changes });
      setTask(saved);
      setDraft(draftOf(saved));
      dataChanged();
      refreshBoot();
      showToast(`${saved.ref} saved.`);
      if (dirtyRef) dirtyRef.current = false;
      if (layout === "drawer") onClose?.();
    } catch (err) {
      if (err instanceof ApiError && err.code === "stale") setStale(true);
      else showError(err);
    } finally {
      setBusy(false);
    }
  };

  // Placement changes apply at once (they don't wait for "Save task"); keep unsaved form edits.
  const placementAction = async (request, message) => {
    try {
      const updated = await request();
      setTask(updated);
      dataChanged();
      refreshBoot();
      showToast(message);
      setPlacementDialog(null);
    } catch (err) {
      showError(err);
    }
  };
  const projectName = (id) => lookup.projects.get(id)?.name ?? "the project";

  const remove = async () => {
    if (!window.confirm(`Delete ${task.ref} "${task.title}" for good? Archiving keeps it instead.`)) return;
    try {
      await api.delete(`/tasks/${task.key}`);
      dataChanged();
      refreshBoot();
      showToast(`${task.ref} deleted.`);
      onClose ? onClose() : navigate("priority");
    } catch (err) {
      showError(err);
    }
  };

  // Links that change the URL (not an ARIA tab widget): the current one is marked as such.
  const tabLink = (name, label, extra = null) => html`
    <a
      class="tab"
      aria-current=${tab === name ? "page" : undefined}
      href=${href(taskPath(task.key, name))}
      onClick=${(e) => {
        e.preventDefault();
        navigate(taskPath(task.key, name), { replace: true });
      }}
    >${label}${extra}</a>
  `;

  return html`
    <div class="task-panel" role="region" aria-label=${`Task ${task.ref}`}>
      <header class="task-panel__head">
        <div class="task-panel__ids">
          <${layout === "page" ? "h1" : "h2"} class="task-panel__heading">
            <span class="task-panel__key">${task.ref}</span><span class="visually-hidden">: ${task.title}</span>
          <//>
          <span class="rank-badge">Rank ${padRank(task.rank)} of ${task.rank_total}</span>
        </div>
        <div class="task-panel__tools">
          <${CopyLinkButton} path=${taskPath(task.key)} label="Copy link to this task" />
          ${onClose && html`<button type="button" class="icon-btn" aria-label="Close" onClick=${onClose}><${CloseIcon} /></button>`}
        </div>
      </header>
      <div class="tabs">
        <nav class="tabs__links" aria-label="Task sections">
          ${tabLink("details", "Details")}
          ${tabLink("conversation", "Conversation", html`<span class="tab__count" aria-label=${`${count} posts`}>${count}</span>`)}
        </nav>
        ${tab === "conversation" &&
        html`<div class="segmented segmented--small tabs__filter" role="group" aria-label="Show">
          <button type="button" aria-pressed=${updatesOnly ? "false" : "true"} onClick=${() => setUpdatesOnly(false)}>All</button>
          <button type="button" aria-pressed=${updatesOnly ? "true" : "false"} onClick=${() => setUpdatesOnly(true)}>Updates only</button>
        </div>`}
      </div>

      ${tab === "conversation"
        ? html`<${ConversationPanel} taskKey=${task.key} lookup=${lookup} updatesOnly=${updatesOnly} onCount=${setPostCount} />`
        : html`<form class="task-panel__form" onSubmit=${save}>
            <div class="task-panel__body">
              ${stale &&
              html`<div class="notice" role="alert">
                <p>Someone else changed this task while you were editing. Reload to see their version (your edits will be lost).</p>
                <button
                  type="button"
                  class="btn"
                  onClick=${() => {
                    discardDraft.current = true;
                    reload();
                  }}
                >Reload</button>
              </div>`}
              <${TaskFields} draft=${draft} setDraft=${setDraft} boot=${boot} lookup=${lookup} readOnly=${readOnly} />
              <${PlacementsField}
                placements=${task.placements}
                lookup=${lookup}
                readOnly=${readOnly}
                onAdd=${() => setPlacementDialog({ moveProjectId: null })}
                onMove=${(projectId) => setPlacementDialog({ moveProjectId: projectId })}
                onRemove=${(projectId) =>
                  placementAction(() => api.delete(`/tasks/${task.key}/placements/${projectId}`), `Removed from ${projectName(projectId)}.`)}
              />
              ${canSomewhere(boot.me, "knowledge.view") &&
              html`<${BoxLinksField} basePath=${`/tasks/${encodeURIComponent(task.key)}/boxes`} editable=${!readOnly} lookup=${lookup} label="Knowledge map" />`}
            </div>
            ${!readOnly &&
            html`<footer class="task-panel__foot">
              ${task.permissions.delete && html`<button type="button" class="btn btn--danger" onClick=${remove}>Delete</button>`}
              <span class="spacer"></span>
              ${onClose && html`<button type="button" class="btn" onClick=${onClose}>Cancel</button>`}
              <button type="submit" class="btn btn--primary" disabled=${busy || !dirty || !draft.title.trim()}>Save task</button>
            </footer>`}
          </form>`}

      <${PlacementDialog}
        open=${placementDialog !== null}
        taskRef=${task.ref}
        projects=${boot.projects}
        placements=${task.placements}
        moveProjectId=${placementDialog?.moveProjectId ?? null}
        onClose=${() => setPlacementDialog(null)}
        onSubmit=${(projectId, nodeId) =>
          placementDialog?.moveProjectId == null
            ? placementAction(() => api.post(`/tasks/${task.key}/placements`, { project_id: projectId, node_id: nodeId }), `Added to ${projectName(projectId)}.`)
            : placementAction(() => api.put(`/tasks/${task.key}/placements/${projectId}`, { node_id: nodeId }), `Moved within ${projectName(projectId)}.`)}
      />
    </div>
  `;
}

/** Defaults for a new task: my own section and me as lead, when I may edit there. */
function newDraft(boot, lookup) {
  const me = boot.me;
  const mine = lookup.personForUser;
  const editable = boot.departments.flatMap((d) => d.sections).filter((s) => canIn(me, "task.edit", s.id));
  const section = mine && editable.some((s) => s.id === mine.section_id) ? mine.section_id : editable[0]?.id;
  const lead = mine?.active ? mine.id : boot.people.find((p) => p.active)?.id;
  return { title: "", description: "", status: "idea", section_id: section, lead_id: lead, helper_ids: [] };
}

/** "New task": the same fields; placements are chosen before the task exists. */
export function NewTaskPanel({ onClose, initialPlacements = [] }) {
  const { boot, lookup } = useAppState();
  const [draft, setDraft] = useState(() => newDraft(boot, lookup));
  const [placements, setPlacements] = useState(initialPlacements);
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState(false);

  const draftPlacements = placements.map((p) => ({ ...p, number: null, path: [] }));
  const create = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const created = await api.post("/tasks", { ...draft, placements });
      dataChanged();
      refreshBoot();
      showToast(`${created.ref} created at the bottom of the ranking.`);
      onClose();
      navigate(taskPath(created.key));
    } catch (err) {
      showError(err);
    } finally {
      setBusy(false);
    }
  };

  return html`
    <div class="task-panel" role="region" aria-label="New task">
      <header class="task-panel__head">
        <div class="task-panel__ids"><span class="task-panel__key">New task</span></div>
        <button type="button" class="icon-btn" aria-label="Close" onClick=${onClose}><${CloseIcon} /></button>
      </header>
      <form class="task-panel__form" onSubmit=${create}>
      <div class="task-panel__body">
        <${TaskFields} draft=${draft} setDraft=${setDraft} boot=${boot} lookup=${lookup} readOnly=${false} />
        <${PlacementsField}
          placements=${draftPlacements}
          lookup=${lookup}
          readOnly=${false}
          onAdd=${() => setDialog({ moveProjectId: null })}
          onMove=${(projectId) => setDialog({ moveProjectId: projectId })}
          onRemove=${(projectId) => setPlacements(placements.filter((p) => p.project_id !== projectId))}
        />
      </div>
      <footer class="task-panel__foot">
        <span class="spacer"></span>
        <button type="button" class="btn" onClick=${onClose}>Cancel</button>
        <button type="submit" class="btn btn--primary" disabled=${busy || !draft.title.trim() || draft.section_id == null}>Create task</button>
      </footer>
      </form>
      <${PlacementDialog}
        open=${dialog !== null}
        taskRef="The new task"
        projects=${boot.projects}
        placements=${draftPlacements}
        moveProjectId=${dialog?.moveProjectId ?? null}
        onClose=${() => setDialog(null)}
        onSubmit=${(projectId, nodeId) => {
          setPlacements([...placements.filter((p) => p.project_id !== projectId), { project_id: projectId, node_id: nodeId }]);
          setDialog(null);
        }}
      />
    </div>
  `;
}

/** Every way of closing (Cancel, ×, Escape, backdrop) asks first when there are unsaved edits. */
export function TaskDrawer({ taskKey, tab, onClose }) {
  const dirty = useRef(false);
  const guardedClose = () => {
    if (dirty.current && !window.confirm("Discard your unsaved changes?")) return;
    onClose();
  };
  return html`
    <${Drawer} label=${`Task ${taskKey}`} onClose=${guardedClose}>
      <${TaskPanel}
        taskKey=${taskKey}
        tab=${tab}
        onClose=${guardedClose}
        dirtyRef=${dirty}
        layout="drawer"
      />
    <//>
  `;
}

export function NewTaskDrawer({ onClose, initialPlacements }) {
  return html`
    <${Drawer} label="New task" onClose=${onClose}>
      <${NewTaskPanel} onClose=${onClose} initialPlacements=${initialPlacements} />
    <//>
  `;
}

/** The permalink page (/t/{key}) when opened directly rather than from a list. */
export function TaskPage({ taskKey, tab }) {
  return html`
    <section class="page task-page">
      <a class="task-page__back" href=${href("priority")}>← Priority</a>
      <div class="panel task-page__panel">
        <${TaskPanel} taskKey=${taskKey} tab=${tab} layout="page" />
      </div>
    </section>
  `;
}
