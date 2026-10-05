/** A process change: a drawer over the list, or its own page; plus the "New change" drawer. */
import { api, ApiError } from "../../api.js";
import { Avatar } from "../../components/badges.js";
import { BoxLinksField } from "../../components/box-links-field.js";
import { ChangeConversation, ScopeTags } from "../../components/change-conversation.js";
import { CopyLinkButton } from "../../components/copy-link.js";
import { Drawer } from "../../components/drawer.js";
import { CloseIcon } from "../../components/icons.js";
import { PersonPicker } from "../../components/person-picker.js";
import { FieldLabel } from "../../components/task-fields.js";
import { showError, showToast } from "../../components/toasts.js";
import { useApi, useTitle } from "../../hooks.js";
import { canIn, canSomewhere } from "../../lib/lookup.js";
import { periodDuration, periodSummary } from "../../lib/periods.js";
import { changesPath, routePath } from "../../lib/routes.js";
import { isoOfDay, dayNumber, periodBar } from "../../lib/timeline.js";
import { href, navigate } from "../../router.js";
import { dataChanged, useAppState } from "../../store.js";
import { html, useEffect, useRef, useState } from "../../ui.js";
import { StatePill } from "./list.js";

const FIELDS = ["title", "what_md", "why_md", "owner_person_id", "process_id"];

function draftOf(change) {
  return Object.fromEntries(FIELDS.map((f) => [f, change[f]]));
}

function changedFields(draft, change) {
  return Object.fromEntries(FIELDS.filter((f) => draft[f] !== change[f]).map((f) => [f, draft[f]]));
}

/** A change's own path ("changes/STL/LM/LM-07"), from the URL the server gives it. */
function pathOf(change, tab = "details") {
  const base = change.url.replace(/^\/+/, "");
  return tab === "details" ? base : `${base}/${tab}`;
}

/** Department and process; only processes where the visitor may edit changes are offered. */
function ProcessFields({ processId, onChange, boot, lookup, readOnly }) {
  const current = lookup.processes.get(processId);
  if (readOnly) {
    const department = current && lookup.departments.get(current.department_id);
    return html`
      <div class="grid-2">
        <div class="field"><${FieldLabel}>Department<//><span class="read-text">${department?.code ?? "?"}</span></div>
        <div class="field"><${FieldLabel}>Process<//><span class="read-text">${current?.name ?? "?"}</span></div>
      </div>
    `;
  }
  const allowed = boot.processes.filter((p) => p.id === processId || canIn(boot.me, "change.edit", p.section_id));
  const departments = boot.departments.filter((d) => allowed.some((p) => p.department_id === d.id));
  const departmentId = current?.department_id ?? departments[0]?.id;
  return html`
    <div class="grid-3">
      <label class="field">
        <${FieldLabel}>Department<//>
        <select
          class="select"
          onChange=${(e) => {
            const first = allowed.find((p) => p.department_id === Number(e.currentTarget.value));
            if (first) onChange(first.id);
          }}
        >
          ${departments.map((d) => html`<option key=${d.id} value=${d.id} selected=${d.id === departmentId}>${d.code}</option>`)}
        </select>
      </label>
      <label class="field grid-span-2">
        <${FieldLabel}>Process<//>
        <select class="select" onChange=${(e) => onChange(Number(e.currentTarget.value))}>
          ${allowed
            .filter((p) => p.department_id === departmentId)
            .map((p) => html`<option key=${p.id} value=${p.id} selected=${p.id === processId}>${p.name}</option>`)}
        </select>
      </label>
    </div>
  `;
}

/** The owner: one person, picked from the active people. */
function OwnerField({ ownerId, onChange, boot, lookup, readOnly }) {
  const [open, setOpen] = useState(false);
  const owner = lookup.people.get(ownerId);
  return html`
    <div class="field">
      <${FieldLabel} id="owner-label">Owner<//>
      <div class="picker-anchor">
        <button
          type="button"
          class="person-button"
          aria-labelledby="owner-label owner-name"
          aria-haspopup=${readOnly ? undefined : "dialog"}
          disabled=${readOnly}
          onClick=${() => setOpen(!open)}
        >
          <${Avatar} person=${owner} />
          <span class="person-button__text"><span class="person-button__name" id="owner-name">${owner?.name ?? "Choose an owner"}</span></span>
        </button>
        ${open &&
        html`<${PersonPicker}
          people=${boot.people.filter((p) => p.active)}
          lookup=${lookup}
          label="Choose the owner"
          onPick=${(person) => {
            onChange(person.id);
            setOpen(false);
          }}
          onClose=${() => setOpen(false)}
        />`}
      </div>
    </div>
  `;
}

/** "At a glance": the periods as bars between the first start and today (or the last end). */
function AtAGlance({ periods, today }) {
  if (periods.length === 0) return null;
  const first = periods.reduce((m, p) => (p.start_date < m ? p.start_date : m), periods[0].start_date);
  const last = periods.reduce((m, p) => ((p.end_date ?? today) > m ? p.end_date ?? today : m), today);
  const frame = { start: first, end: isoOfDay(dayNumber(last) + 1) };
  const scale = 1000;
  const bars = periods.map((p) => ({ p, bar: periodBar(p, frame, today, scale, { arrow: 10, minimum: 8 }) }));
  return html`
    <div class="field">
      <${FieldLabel}>At a glance<//>
      <div class="glance" aria-hidden="true">
        <span class="glance__line"></span>
        ${bars.map(
          ({ p, bar }) => html`
            <span
              key=${p.id}
              class=${`glance__bar gantt-bar--${bar.kind}${bar.planned ? " gantt-bar--planned" : ""}${bar.open ? " glance__bar--open" : ""}`}
              style=${{ left: `${(bar.x / scale) * 100}%`, width: `${(bar.width / scale) * 100}%` }}
            ></span>
          `,
        )}
      </div>
      <span class="field-hint">${periodSummary(periods)}</span>
    </div>
  `;
}

/** "Periods in effect": a read-only summary; periods are posted and edited in the conversation. */
function PeriodsSummary({ change, canPost, onViewPost, onPostPeriod }) {
  return html`
    <div class="field">
      <div class="field__row">
        <${FieldLabel}>Periods<//>
        <span class="field-hint">Posted in the conversation</span>
      </div>
      ${change.periods.length === 0 && html`<p class="muted">No periods yet.</p>`}
      ${change.periods.map(
        (p) => html`
          <div key=${p.id} class="period-card">
            <span class=${`period-swatch period-swatch--${p.kind}${p.kind === "change" && !p.end_date ? " period-swatch--open" : ""}`} aria-hidden="true"></span>
            <div class="period-card__text">
              <div class="period-card__head"><span class="period-card__label">${p.label}</span><span class="period-card__dates">${periodDuration(p)}</span></div>
              <${ScopeTags} tags=${p.scope_tags} />
            </div>
            <a
              class="period-card__view"
              href=${href(`${pathOf(change, "conversation")}#post-${p.post_id}`)}
              onClick=${(e) => {
                e.preventDefault();
                onViewPost(p.post_id);
              }}
            >View post</a>
          </div>
        `,
      )}
      ${canPost && html`<button type="button" class="btn btn--dashed" onClick=${onPostPeriod}>+ Post a period</button>`}
    </div>
  `;
}

function ChangeFields({ draft, setDraft, change, boot, lookup, readOnly }) {
  const set = (patch) => setDraft({ ...draft, ...patch });
  if (readOnly) {
    return html`
      <div class="field"><${FieldLabel}>Change<//><h2 class="read-title">${change.title}</h2></div>
      <${ProcessFields} processId=${change.process_id} boot=${boot} lookup=${lookup} readOnly />
      ${canSomewhere(boot.me, "knowledge.view") &&
      html`<${BoxLinksField} basePath=${`/changes/${encodeURIComponent(change.key)}/boxes`} editable=${false} lookup=${lookup} />`}
      <div class="field">
        <${FieldLabel}>What changes<//>
        ${change.what_md ? html`<div class="md" dangerouslySetInnerHTML=${{ __html: change.what_html }}></div>` : html`<p class="muted">Not written yet.</p>`}
      </div>
      <div class="field">
        <${FieldLabel}>Why<//>
        ${change.why_md ? html`<div class="md" dangerouslySetInnerHTML=${{ __html: change.why_html }}></div>` : html`<p class="muted">Not written yet.</p>`}
      </div>
      <${OwnerField} ownerId=${change.owner_person_id} boot=${boot} lookup=${lookup} readOnly />
    `;
  }
  return html`
    <label class="field">
      <${FieldLabel}>Change<//>
      <input class="input input--title" required maxlength="300" value=${draft.title} onInput=${(e) => set({ title: e.currentTarget.value })} />
    </label>
    <${ProcessFields} processId=${draft.process_id} boot=${boot} lookup=${lookup} onChange=${(process_id) => set({ process_id })} />
    ${change &&
    canSomewhere(boot.me, "knowledge.view") &&
    html`<${BoxLinksField}
      basePath=${`/changes/${encodeURIComponent(change.key)}/boxes`}
      editable=${true}
      lookup=${lookup}
      hint="The change then shows up on those boxes, and on every box above them."
    />`}
    <label class="field">
      <${FieldLabel}>What changes<//>
      <textarea class="textarea" rows="3" value=${draft.what_md} onInput=${(e) => set({ what_md: e.currentTarget.value })}></textarea>
    </label>
    <label class="field">
      <${FieldLabel}>Why<//>
      <textarea class="textarea" rows="2" value=${draft.why_md} onInput=${(e) => set({ why_md: e.currentTarget.value })}></textarea>
    </label>
    <${OwnerField} ownerId=${draft.owner_person_id} boot=${boot} lookup=${lookup} onChange=${(owner_person_id) => set({ owner_person_id })} />
  `;
}

/** An existing change: header, tabs, details form (or read-only view), footer. */
export function ChangePanel({ changeKey, tab, route = null, onClose, layout, dirtyRef }) {
  const { boot, lookup } = useAppState();
  const { data, error, reload } = useApi(`/changes/${encodeURIComponent(changeKey)}`);
  const [change, setChange] = useState(null);
  const [draft, setDraft] = useState(null);
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const [periodsOnly, setPeriodsOnly] = useState(false);
  const [postCount, setPostCount] = useState(null);
  const [startWith, setStartWith] = useState("comment");
  const discardDraft = useRef(false);

  useEffect(() => {
    if (!data) return;
    const keep = !discardDraft.current;
    discardDraft.current = false;
    setDraft((current) =>
      keep && current && change && Object.keys(changedFields(current, change)).length > 0 ? current : draftOf(data),
    );
    setChange(data);
    setStale(false);
  }, [data]);

  // The address follows the change: its process may have changed, or a link was spelled loosely.
  useEffect(() => {
    if (!change || !route) return;
    const canonical = pathOf(change, tab);
    if (canonical !== routePath(route)) navigate(canonical + location.hash, { replace: true });
  }, [change?.url, tab]);

  useTitle(change ? `${change.key} ${change.title}` : changeKey);
  const editable = Boolean(change?.permissions.edit);
  const dirty = Boolean(change && draft && editable && Object.keys(changedFields(draft, change)).length > 0);
  if (dirtyRef) dirtyRef.current = dirty;

  if (error) {
    const missing = error instanceof ApiError && error.status === 404;
    return html`
      <div class="task-panel">
        <div class="task-panel__head"><span class="task-panel__key">${changeKey}</span>
          ${onClose && html`<button type="button" class="icon-btn" aria-label="Close" onClick=${onClose}><${CloseIcon} /></button>`}
        </div>
        <div class="task-panel__body">
          <p role="alert">${missing ? "This process change doesn't exist, or you don't have access to it." : error.message}</p>
          <a href=${href(changesPath())}>Go to the process changes</a>
        </div>
      </div>
    `;
  }
  if (!change || !draft) return html`<div class="task-panel"><div class="task-panel__body muted">Loading…</div></div>`;

  const process = lookup.processes.get(change.process_id);
  const changes = changedFields(draft, change);
  const count = postCount ?? change.post_count;
  const openTab = (name, hash = "") => navigate(pathOf(change, name) + hash, { replace: true });

  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const saved = await api.patch(`/changes/${change.key}`, { version: change.version, ...changes });
      setChange(saved);
      setDraft(draftOf(saved));
      dataChanged();
      showToast(`${saved.key} saved.`);
      if (dirtyRef) dirtyRef.current = false;
      if (layout === "drawer") onClose?.();
    } catch (err) {
      if (err instanceof ApiError && err.code === "stale") setStale(true);
      else showError(err);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!window.confirm(`Delete ${change.key} "${change.title}" for good, with its conversation?`)) return;
    try {
      await api.delete(`/changes/${change.key}`);
      dataChanged();
      showToast(`${change.key} deleted.`);
      onClose ? onClose() : navigate(changesPath());
    } catch (err) {
      showError(err);
    }
  };

  const tabLink = (name, label, extra = null) => html`
    <a
      class="tab"
      aria-current=${tab === name ? "page" : undefined}
      href=${href(pathOf(change, name))}
      onClick=${(e) => {
        e.preventDefault();
        openTab(name);
      }}
    >${label}${extra}</a>
  `;

  return html`
    <div class="task-panel" role="region" aria-label=${`Process change ${change.key}`}>
      <header class="task-panel__head">
        <div class="task-panel__ids">
          <${layout === "page" ? "h1" : "h2"} class="task-panel__heading">
            <span class="task-panel__key">${change.key}</span><span class="visually-hidden">: ${change.title}</span>
          <//>
          <${StatePill} state=${change.state} />
        </div>
        <div class="task-panel__tools">
          <${CopyLinkButton} path=${pathOf(change)} label="Copy link to this change" />
          ${onClose && html`<button type="button" class="icon-btn" aria-label="Close" onClick=${onClose}><${CloseIcon} /></button>`}
        </div>
      </header>
      <div class="tabs">
        <nav class="tabs__links" aria-label="Change sections">
          ${tabLink("details", "Details")}
          ${tabLink("conversation", "Conversation", html`<span class="tab__count" aria-label=${`${count} posts`}>${count}</span>`)}
        </nav>
        ${tab === "conversation" &&
        html`<div class="segmented segmented--small tabs__filter" role="group" aria-label="Show">
          <button type="button" aria-pressed=${periodsOnly ? "false" : "true"} onClick=${() => setPeriodsOnly(false)}>All</button>
          <button type="button" aria-pressed=${periodsOnly ? "true" : "false"} onClick=${() => setPeriodsOnly(true)}>Periods only</button>
        </div>`}
      </div>

      ${tab === "conversation"
        ? html`<${ChangeConversation}
            change=${change}
            processCode=${process?.code ?? ""}
            lookup=${lookup}
            today=${boot.today}
            periodsOnly=${periodsOnly}
            startWith=${startWith}
            onCount=${setPostCount}
          />`
        : html`<form class="task-panel__form" onSubmit=${save}>
            <div class="task-panel__body">
              ${stale &&
              html`<div class="notice" role="alert">
                <p>Someone else changed this process change while you were editing. Reload to see their version (your edits will be lost).</p>
                <button
                  type="button"
                  class="btn"
                  onClick=${() => {
                    discardDraft.current = true;
                    reload();
                  }}
                >Reload</button>
              </div>`}
              <${ChangeFields} draft=${draft} setDraft=${setDraft} change=${change} boot=${boot} lookup=${lookup} readOnly=${!editable} />
              <${PeriodsSummary}
                change=${change}
                canPost=${editable}
                onViewPost=${(postId) => openTab("conversation", `#post-${postId}`)}
                onPostPeriod=${() => {
                  setStartWith("period");
                  openTab("conversation");
                }}
              />
              <${AtAGlance} periods=${change.periods} today=${boot.today} />
            </div>
            ${editable &&
            html`<footer class="task-panel__foot">
              ${change.permissions.delete && html`<button type="button" class="btn btn--danger" onClick=${remove}>Delete</button>`}
              <span class="spacer"></span>
              ${onClose && html`<button type="button" class="btn" onClick=${onClose}>Cancel</button>`}
              <button type="submit" class="btn btn--primary" disabled=${busy || !dirty || !draft.title.trim()}>Save change</button>
            </footer>`}
          </form>`}
    </div>
  `;
}

/** "New change" in a process: title, process, what, why, owner (me, when I am on the board). */
export function NewChangePanel({ processId, onClose }) {
  const { boot, lookup } = useAppState();
  const mine = lookup.personForUser;
  const [draft, setDraft] = useState(() => ({
    title: "",
    what_md: "",
    why_md: "",
    process_id: processId,
    owner_person_id: mine?.active ? mine.id : boot.people.find((p) => p.active)?.id,
  }));
  const [busy, setBusy] = useState(false);
  const create = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const created = await api.post("/changes", draft);
      dataChanged();
      showToast(`${created.key} created. Post its first period in the conversation.`);
      onClose();
      navigate(pathOf(created));
    } catch (err) {
      showError(err);
    } finally {
      setBusy(false);
    }
  };
  return html`
    <div class="task-panel" role="region" aria-label="New process change">
      <header class="task-panel__head">
        <div class="task-panel__ids"><span class="task-panel__key">New process change</span></div>
        <button type="button" class="icon-btn" aria-label="Close" onClick=${onClose}><${CloseIcon} /></button>
      </header>
      <form class="task-panel__form" onSubmit=${create}>
        <div class="task-panel__body">
          <${ChangeFields} draft=${draft} setDraft=${setDraft} change=${null} boot=${boot} lookup=${lookup} readOnly=${false} />
        </div>
        <footer class="task-panel__foot">
          <span class="spacer"></span>
          <button type="button" class="btn" onClick=${onClose}>Cancel</button>
          <button type="submit" class="btn btn--primary" disabled=${busy || !draft.title.trim() || draft.owner_person_id == null}>Create change</button>
        </footer>
      </form>
    </div>
  `;
}

/** Every way of closing (Cancel, ×, Escape, backdrop) asks first when there are unsaved edits. */
export function ChangeDrawer({ changeKey, tab, route, onClose }) {
  const dirty = useRef(false);
  const guardedClose = () => {
    if (dirty.current && !window.confirm("Discard your unsaved changes?")) return;
    onClose();
  };
  return html`
    <${Drawer} label=${`Process change ${changeKey}`} onClose=${guardedClose}>
      <${ChangePanel} changeKey=${changeKey} tab=${tab} route=${route} onClose=${guardedClose} dirtyRef=${dirty} layout="drawer" />
    <//>
  `;
}

export function NewChangeDrawer({ processId, onClose }) {
  return html`
    <${Drawer} label="New process change" onClose=${onClose}>
      <${NewChangePanel} processId=${processId} onClose=${onClose} />
    <//>
  `;
}

/** The change's own page, when its link is opened directly rather than from the list. */
export function ChangePage({ changeKey, tab, route }) {
  return html`
    <section class="page task-page">
      <a class="task-page__back" href=${href(changesPath(route.params.department, route.params.process))}>← Process changes</a>
      <div class="panel task-page__panel">
        <${ChangePanel} changeKey=${changeKey} tab=${tab} route=${route} layout="page" />
      </div>
    </section>
  `;
}
