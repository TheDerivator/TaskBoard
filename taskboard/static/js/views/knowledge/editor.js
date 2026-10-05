/** Editing a box (the NodeEdit mockup): kind, name, place in the tree, description, key facts,
 * links both ways, controls and external links, saved together (each changed object is a new
 * revision); plus a new box under another, moving and deleting. */
import { api, ApiError } from "../../api.js";
import { BoxPicker } from "../../components/box-picker.js";
import { Dialog } from "../../components/dialog.js";
import { Drawer } from "../../components/drawer.js";
import { CloseIcon, TrashIcon } from "../../components/icons.js";
import { MarkdownField } from "../../components/markdown-field.js";
import { FieldLabel } from "../../components/task-fields.js";
import { showError, showToast } from "../../components/toasts.js";
import { useApi } from "../../hooks.js";
import { ancestors, subtree } from "../../lib/maplayout.js";
import { html, useEffect, useRef, useState } from "../../ui.js";
import { KindIcon, kindClass } from "./map.js";

const LINK_KINDS = [
  ["dashboard", "Dashboard"],
  ["graph", "Graph"],
  ["calibration", "Calibration diagram"],
  ["document", "Document"],
  ["website", "Website"],
];

const pickLink = ({ kind, label, url, pass_box_param }) => ({ kind, label, url, pass_box_param });

function draftOf(saved, key) {
  const box = saved.box;
  return {
    kind: box.kind,
    name: box.name,
    body_md: box.body_md,
    main_url: box.main_url ?? "",
    facts: box.facts.map(([k, v]) => [k, v]),
    fields: { ...box.fields },
    step_no: box.step_no ?? "",
    owner_person_id: box.owner_person_id,
    external_links: box.external_links.map(pickLink),
    links: saved.links.map((lk) => ({
      id: lk.id,
      type: lk.type,
      direction: lk.from_key === key ? "forward" : "backward",
      to_key: lk.from_key === key ? lk.to_key : lk.from_key,
      note_md: lk.note_md,
    })),
    controls: saved.controls.map((c) => ({ id: c.id, kind: c.kind, text: c.text, external_links: c.external_links.map(pickLink) })),
  };
}

function emptyDraft(kind, ownerId) {
  return {
    kind,
    name: "",
    body_md: "",
    main_url: "",
    facts: [],
    fields: {},
    step_no: "",
    owner_person_id: ownerId,
    external_links: [],
    links: [],
    controls: [],
  };
}

/** What the API takes: empty optional texts become null, fields only as the kind defines them. */
function payload(draft, kind) {
  const known = new Set((kind?.field_schema ?? []).map((f) => f.key));
  return {
    ...draft,
    main_url: draft.main_url.trim() || null,
    step_no: draft.step_no.trim() || null,
    facts: draft.facts.filter(([k]) => k.trim()),
    fields: Object.fromEntries(Object.entries(draft.fields).filter(([k, v]) => known.has(k) && v !== "" && v != null)),
  };
}

/** "+ link" for a box or a control: kind, label, URL, and whether the box key goes along. */
function ExternalLinkForm({ boxKey, onAdd, onCancel }) {
  const [form, setForm] = useState({ kind: "dashboard", label: "", url: "", pass_box_param: false });
  const set = (patch) => setForm({ ...form, ...patch });
  const valid = form.label.trim() && /^https?:\/\/\S+$/i.test(form.url.trim());
  return html`
    <fieldset class="ext-form">
      <legend class="field__label">External link · new</legend>
      <div class="ext-form__row">
        <label class="field field--compact">
          <span class="field__label">Kind</span>
          <select class="select" value=${form.kind} onChange=${(e) => set({ kind: e.currentTarget.value })}>
            ${LINK_KINDS.map(([value, label]) => html`<option key=${value} value=${value}>${label}</option>`)}
          </select>
        </label>
        <label class="field field--compact">
          <span class="field__label">Label</span>
          <input class="input" value=${form.label} onInput=${(e) => set({ label: e.currentTarget.value })} />
        </label>
      </div>
      <label class="field field--compact">
        <span class="field__label">URL</span>
        <input class="input input--mono" type="url" placeholder="https://" value=${form.url} onInput=${(e) => set({ url: e.currentTarget.value })} />
      </label>
      <label class="check-line">
        <input type="checkbox" checked=${form.pass_box_param} onChange=${(e) => set({ pass_box_param: e.currentTarget.checked })} />
        Pass this box as a parameter (adds <code>?node=${boxKey ?? "…"}</code>)
      </label>
      <div class="ext-form__foot">
        <button type="button" class="btn" onClick=${onCancel}>Cancel</button>
        <button type="button" class="btn btn--dark" disabled=${!valid} onClick=${() => onAdd({ ...form, label: form.label.trim(), url: form.url.trim() })}>Add link</button>
      </div>
    </fieldset>
  `;
}

function LinkChips({ links, onRemove }) {
  return html`
    <span class="ext-chips">
      ${links.map(
        (link, i) => html`
          <span key=${`${link.url}${i}`} class="scope-tag scope-tag--removable" title=${link.url}>
            ${link.label}
            <button type="button" aria-label=${`Remove ${link.label}`} onClick=${() => onRemove(i)}><${CloseIcon} size=${10} /></button>
          </span>
        `,
      )}
    </span>
  `;
}

/** Moving a box: a new place under another box of the same map, before a sibling or last. */
function MoveDialog({ tree, boxKey, processName, onMove, onClose }) {
  const blocked = subtree(tree, boxKey);
  const order = [];
  const walk = (key, depth) => {
    order.push({ key, depth });
    for (const child of tree.children.get(key) ?? []) walk(child, depth + 1);
  };
  walk(tree.root, 0);
  const [parent, setParent] = useState(tree.parent.get(boxKey));
  const siblings = (tree.children.get(parent) ?? []).filter((k) => k !== boxKey);
  const [before, setBefore] = useState("");
  const name = (key) => (key === tree.root ? processName : tree.byKey.get(key).name);
  return html`
    <${Dialog} open=${true} title=${`Move ${name(boxKey)}`} onClose=${onClose} wide>
      <div class="dialog__body move-dialog">
        <fieldset class="move-dialog__tree">
          <legend class="field__label">Sits under</legend>
          ${order
            .filter((o) => !blocked.has(o.key))
            .map(
              (o) => html`
                <label key=${o.key} class="move-dialog__option" style=${{ paddingLeft: `${o.depth * 18 + 8}px` }}>
                  <input type="radio" name="move-parent" checked=${parent === o.key} onChange=${() => {
                    setParent(o.key);
                    setBefore("");
                  }} />
                  ${name(o.key)}
                </label>
              `,
            )}
        </fieldset>
        <label class="field">
          <${FieldLabel}>Place<//>
          <select class="select" value=${before} onChange=${(e) => setBefore(e.currentTarget.value)}>
            <option value="">Last</option>
            ${siblings.map((k) => html`<option key=${k} value=${k}>Before ${name(k)}</option>`)}
          </select>
        </label>
      </div>
      <div class="dialog__actions">
        <button type="button" class="btn" onClick=${onClose}>Cancel</button>
        <button type="button" class="btn btn--primary" onClick=${() => onMove(parent, before || null)}>Move</button>
      </div>
    <//>
  `;
}

function EditorForm({ graph, tree, boot, lookup, boxKey, parentKey, saved, reload, onDone, onClose, dirtyRef }) {
  const editing = boxKey != null;
  const box = editing ? saved.box : null;
  const isDefect = editing ? box.process_id == null : false;
  const kinds = graph.kinds.filter((k) => (isDefect ? k.role === "defect" : k.role !== "defect"));
  const firstStep = kinds.find((k) => k.role === "step")?.key ?? kinds[0]?.key;
  const [draft, setDraft] = useState(() => (editing ? draftOf(saved, boxKey) : emptyDraft(firstStep, lookup.personForUser?.active ? lookup.personForUser.id : null)));
  const [names, setNames] = useState(() => new Map());
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const [picking, setPicking] = useState(false);
  const [addingLink, setAddingLink] = useState(null); // "box" | control index
  const [moving, setMoving] = useState(false);
  const initial = useRef(JSON.stringify(draft));
  if (dirtyRef) dirtyRef.current = JSON.stringify(draft) !== initial.current;

  const kind = graph.kinds.find((k) => k.key === draft.kind);
  const set = (patch) => setDraft({ ...draft, ...patch });
  const linkTypes = [...graph.link_types].sort((a, b) => a.position - b.position);
  const typeOptions = linkTypes.flatMap((t) =>
    t.forward_name === t.backward_name
      ? [[`${t.key}:forward`, t.forward_name]]
      : [
          [`${t.key}:forward`, t.forward_name],
          [`${t.key}:backward`, t.backward_name],
        ],
  );
  const nameOf = (key) => names.get(key) ?? (key === tree.root ? graph.process.name : tree.byKey.get(key)?.name ?? key);
  const styleOf = (key) => (tree.byKey.has(key) ? kindClass(tree, key) : names.has(`${key}:defect`) ? "kind--ink" : "kind--grey");
  const defectSection = () => {
    const counts = new Map();
    for (const b of graph.boxes) if (b.process_id == null) counts.set(b.section_id, (counts.get(b.section_id) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? graph.process.section_id;
  };
  const createDefect = async (name) => {
    const defectKind = graph.kinds.find((k) => k.role === "defect");
    const created = await api.post("/boxes", { kind: defectKind.key, name, section_id: defectSection() });
    return { key: created.box.key, name: created.box.name, kind: created.box.kind, process_id: null, path: [], created: true };
  };
  const role = kind?.role;
  const showControls = role === "failure_mode" || draft.controls.length > 0;

  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const body = payload(draft, kind);
      const result = editing
        ? await api.patch(`/boxes/${boxKey}`, { version: box.version, ...body })
        : await api.post("/boxes", { parent_key: parentKey, ...body });
      showToast(`${result.box.name} saved.`);
      if (dirtyRef) dirtyRef.current = false;
      onDone(result.box.key);
    } catch (error) {
      if (error instanceof ApiError && error.code === "stale") setStale(true);
      else showError(error);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!window.confirm(`Delete "${box.name}" with its links and controls? Its history is kept.`)) return;
    try {
      await api.delete(`/boxes/${boxKey}`);
      showToast(`${box.name} deleted.`);
      if (dirtyRef) dirtyRef.current = false;
      onDone(tree.parent.get(boxKey) ?? tree.root);
    } catch (error) {
      showError(error);
    }
  };
  const reviewed = async () => {
    try {
      await api.post(`/boxes/${boxKey}/reviewed`);
      showToast("Marked as reviewed today.");
      reload();
    } catch (error) {
      showError(error);
    }
  };
  const move = async (parent, before) => {
    try {
      await api.post(`/boxes/${boxKey}/move`, { parent_key: parent, before_key: before });
      setMoving(false);
      showToast(`${box.name} moved.`);
      if (dirtyRef) dirtyRef.current = false;
      onDone(boxKey);
    } catch (error) {
      showError(error);
    }
  };

  const hasChildren = editing && (tree.children.get(boxKey) ?? []).length > 0;
  const where = editing ? ancestors(tree, boxKey) : [...ancestors(tree, parentKey), parentKey];
  const wherePath = where.map((k) => (k === tree.root ? graph.process.name : tree.byKey.get(k)?.name)).join(" › ");
  const leadsToDefect = (link) => link.direction === "forward" && graph.link_types.find((t) => t.key === link.type)?.role === "leads_to";

  return html`
    <form class="task-panel__form" onSubmit=${save}>
      <div class="task-panel__body">
        ${stale &&
        html`<div class="notice" role="alert">
          <p>Someone else changed this box while you were editing. Reload to see their version (your edits will be lost).</p>
          <button type="button" class="btn" onClick=${reload}>Reload</button>
        </div>`}
        <div class="grid-kind-name">
          <label class="field">
            <${FieldLabel}>Kind<//>
            <select class="select" value=${draft.kind} disabled=${editing && box.key === tree.root} onChange=${(e) => set({ kind: e.currentTarget.value })}>
              ${kinds.map((k) => html`<option key=${k.key} value=${k.key}>${k.name}</option>`)}
            </select>
          </label>
          <label class="field">
            <${FieldLabel}>Name<//>
            <input class="input input--name" required maxlength="300" value=${draft.name} onInput=${(e) => set({ name: e.currentTarget.value })} />
          </label>
        </div>
        ${!isDefect &&
        html`<div class="field">
          <${FieldLabel}>Sits under<//>
          <div class="sits-under">
            <span>${wherePath || "The top of the map"}</span>
            ${editing && box.key !== tree.root && html`<button type="button" class="link-button" onClick=${() => setMoving(true)}>Move</button>`}
          </div>
        </div>`}
        <div class="field">
          <${FieldLabel}>Description · Markdown<//>
          <${MarkdownField}
            label="Description"
            value=${draft.body_md}
            onChange=${(body_md) => set({ body_md })}
            uploadPath=${editing ? `/boxes/${encodeURIComponent(boxKey)}/attachments` : null}
          />
          ${!editing && html`<span class="field-hint">Images can be added once the box exists.</span>`}
        </div>
        ${(kind?.has_main_url || draft.main_url) &&
        html`<label class="field">
          <${FieldLabel}>Main URL<//>
          <input class="input input--mono" type="url" placeholder="https://" value=${draft.main_url} onInput=${(e) => set({ main_url: e.currentTarget.value })} />
        </label>`}
        ${(kind?.has_facts || draft.facts.length > 0) &&
        html`<div class="field">
          <${FieldLabel}>Key facts<//>
          ${draft.facts.map(
            ([k, v], i) => html`
              <div key=${i} class="fact-row">
                <input class="input" aria-label=${`Fact ${i + 1}`} value=${k} onInput=${(e) => set({ facts: draft.facts.map((f, j) => (j === i ? [e.currentTarget.value, f[1]] : f)) })} />
                <input class="input input--mono" aria-label=${`Value of fact ${i + 1}`} value=${v} onInput=${(e) => set({ facts: draft.facts.map((f, j) => (j === i ? [f[0], e.currentTarget.value] : f)) })} />
                <button type="button" class="icon-btn" aria-label=${`Remove fact ${i + 1}`} onClick=${() => set({ facts: draft.facts.filter((_, j) => j !== i) })}><${TrashIcon} /></button>
              </div>
            `,
          )}
          <button type="button" class="btn btn--dashed" onClick=${() => set({ facts: [...draft.facts, ["", ""]] })}>+ Add fact</button>
        </div>`}
        ${(kind?.field_schema ?? []).length > 0 &&
        html`<div class="grid-2">
          ${kind.field_schema.map(
            (f) => html`
              <label key=${f.key} class="field">
                <${FieldLabel}>${f.label || f.key}<//>
                <input
                  class="input"
                  type=${f.type === "number" ? "number" : "text"}
                  value=${draft.fields[f.key] ?? ""}
                  onInput=${(e) => set({ fields: { ...draft.fields, [f.key]: f.type === "number" && e.currentTarget.value !== "" ? Number(e.currentTarget.value) : e.currentTarget.value } })}
                />
              </label>
            `,
          )}
        </div>`}
        <div class="grid-2">
          ${(role === "step" || draft.step_no) &&
          html`<label class="field">
            <${FieldLabel}>Step number<//>
            <input class="input input--mono" maxlength="20" placeholder="OP20" value=${draft.step_no} onInput=${(e) => set({ step_no: e.currentTarget.value })} />
          </label>`}
          <label class="field">
            <${FieldLabel}>Owner<//>
            <select class="select" value=${draft.owner_person_id ?? ""} onChange=${(e) => set({ owner_person_id: e.currentTarget.value ? Number(e.currentTarget.value) : null })}>
              <option value="">No owner</option>
              ${boot.people.filter((p) => p.active || p.id === draft.owner_person_id).map((p) => html`<option key=${p.id} value=${p.id}>${p.name}</option>`)}
            </select>
          </label>
        </div>

        <div class="field">
          <${FieldLabel}>Links to other boxes<//>
          ${draft.links.map(
            (link, i) => html`
              <div key=${link.id ?? `new${i}`} class="link-row">
                <div class="link-row__head">
                  <select
                    class="select select--compact"
                    aria-label=${`Link type with ${nameOf(link.to_key)}`}
                    value=${`${link.type}:${link.direction}`}
                    onChange=${(e) => {
                      const [type, direction] = e.currentTarget.value.split(":");
                      set({ links: draft.links.map((l, j) => (j === i ? { ...l, type, direction } : l)) });
                    }}
                  >
                    ${typeOptions.map(([value, label]) => html`<option key=${value} value=${value}>${label}</option>`)}
                  </select>
                  <span class=${`rel-chip ${styleOf(link.to_key)}`}><${KindIcon} tree=${tree} boxKey=${link.to_key} />${nameOf(link.to_key)}</span>
                  <span class="spacer"></span>
                  <button type="button" class="icon-btn" aria-label=${`Remove the link with ${nameOf(link.to_key)}`} onClick=${() => set({ links: draft.links.filter((_, j) => j !== i) })}><${CloseIcon} size=${14} /></button>
                </div>
                <label class="field field--compact">
                  <span class="field-hint">${leadsToDefect(link) ? "How it leads to this" : "Note (optional)"}</span>
                  <input class="input" value=${link.note_md} onInput=${(e) => set({ links: draft.links.map((l, j) => (j === i ? { ...l, note_md: e.currentTarget.value } : l)) })} />
                </label>
              </div>
            `,
          )}
          <button type="button" class="btn btn--dashed" onClick=${() => setPicking(true)}>+ Link to another box (or create one)</button>
        </div>

        ${showControls &&
        html`<div class="field">
          <${FieldLabel}>Controls<//>
          ${draft.controls.map(
            (control, i) => html`
              <div key=${control.id ?? `new${i}`} class="control-row">
                <select class="select" aria-label=${`Control ${i + 1} type`} value=${control.kind} onChange=${(e) => set({ controls: draft.controls.map((c, j) => (j === i ? { ...c, kind: e.currentTarget.value } : c)) })}>
                  <option value="prevent">Prevent</option>
                  <option value="detect">Detect</option>
                </select>
                <input class="input" aria-label=${`Control ${i + 1}`} value=${control.text} onInput=${(e) => set({ controls: draft.controls.map((c, j) => (j === i ? { ...c, text: e.currentTarget.value } : c)) })} />
                <button type="button" class="icon-btn" aria-label=${`Remove control ${i + 1}`} onClick=${() => set({ controls: draft.controls.filter((_, j) => j !== i) })}><${TrashIcon} /></button>
                <span></span>
                <span class="control-row__links">
                  <${LinkChips}
                    links=${control.external_links}
                    onRemove=${(k) => set({ controls: draft.controls.map((c, j) => (j === i ? { ...c, external_links: c.external_links.filter((_, n) => n !== k) } : c)) })}
                  />
                  ${addingLink !== i && html`<button type="button" class="btn btn--dashed btn--small" onClick=${() => setAddingLink(i)}>+ link</button>`}
                </span>
                <span></span>
                ${addingLink === i &&
                html`<div class="control-row__form">
                  <${ExternalLinkForm}
                    boxKey=${boxKey}
                    onCancel=${() => setAddingLink(null)}
                    onAdd=${(link) => {
                      set({ controls: draft.controls.map((c, j) => (j === i ? { ...c, external_links: [...c.external_links, link] } : c)) });
                      setAddingLink(null);
                    }}
                  />
                </div>`}
              </div>
            `,
          )}
          <button type="button" class="btn btn--dashed" onClick=${() => set({ controls: [...draft.controls, { kind: "prevent", text: "", external_links: [] }] })}>+ Add control</button>
        </div>`}

        <div class="field">
          <${FieldLabel}>Dashboards, diagrams & documents<//>
          <${LinkChips} links=${draft.external_links} onRemove=${(k) => set({ external_links: draft.external_links.filter((_, n) => n !== k) })} />
          ${addingLink === "box"
            ? html`<${ExternalLinkForm}
                boxKey=${boxKey}
                onCancel=${() => setAddingLink(null)}
                onAdd=${(link) => {
                  set({ external_links: [...draft.external_links, link] });
                  setAddingLink(null);
                }}
              />`
            : html`<button type="button" class="btn btn--dashed" onClick=${() => setAddingLink("box")}>+ External link</button>`}
        </div>
      </div>
      <footer class="task-panel__foot">
        ${editing &&
        box.key !== tree.root &&
        html`<button type="button" class="btn btn--danger" disabled=${hasChildren} title=${hasChildren ? "Move or delete the boxes under it first" : undefined} onClick=${remove}>Delete</button>`}
        ${editing && html`<button type="button" class="btn" onClick=${reviewed}>Mark reviewed</button>`}
        <span class="spacer"></span>
        <button type="button" class="btn" onClick=${onClose}>Cancel</button>
        <button type="submit" class="btn btn--primary" disabled=${busy || !draft.name.trim() || draft.controls.some((c) => !c.text.trim())}>${editing ? "Save box" : "Create box"}</button>
      </footer>
      <${BoxPicker}
        open=${picking}
        title="Link to another box"
        exclude=${[boxKey ?? ""]}
        onClose=${() => setPicking(false)}
        onCreateDefect=${editing ? createDefect : null}
        onPick=${(ref) => {
          setNames(new Map([...names, [ref.key, ref.name], ...(ref.process_id == null ? [[`${ref.key}:defect`, true]] : [])]));
          const fm = role === "failure_mode";
          set({ links: [...draft.links, { type: fm ? "leads_to" : "see_also", direction: "forward", to_key: ref.key, note_md: "" }] });
          setPicking(false);
        }}
      />
      ${moving && html`<${MoveDialog} tree=${tree} boxKey=${boxKey} processName=${graph.process.name} onMove=${move} onClose=${() => setMoving(false)} />`}
    </form>
  `;
}

/**
 * The editor in a drawer. With `boxKey` it edits that box; with `parentKey` it makes a new one.
 * @param {{graph: object, tree: object, boot: object, lookup: object, boxKey?: ?string,
 *   parentKey?: ?string, place?: string, onDone: (key: ?string) => void, onClose: () => void}} props
 *   `place` names where the box is ("the STL defect catalogue"); default: the graph's process
 */
export function BoxEditorDrawer({ graph, tree, boot, lookup, boxKey = null, parentKey = null, place = null, onDone, onClose }) {
  const { data: saved, error, reload } = useApi(boxKey ? `/boxes/${encodeURIComponent(boxKey)}` : null);
  const [generation, setGeneration] = useState(0);
  const dirty = useRef(false);
  useEffect(() => setGeneration((n) => n + 1), [saved]);
  const guardedClose = () => {
    if (dirty.current && !window.confirm("Discard your unsaved changes?")) return;
    onClose();
  };
  const where = place ?? graph.process.name;
  const title = boxKey ? `Editing box in ${where}` : `New box in ${where}`;
  const name = boxKey ? (boxKey === tree.root ? graph.process.name : tree.byKey.get(boxKey)?.name ?? boxKey) : "New box";
  return html`
    <${Drawer} label=${title} onClose=${guardedClose}>
      <div class="task-panel" role="region" aria-label=${title}>
        <header class="task-panel__head">
          <div class="editor-title">
            <span class="field-hint">${title}</span>
            <h2 class="editor-title__name">${name}</h2>
          </div>
          <button type="button" class="icon-btn" aria-label="Close" onClick=${guardedClose}><${CloseIcon} /></button>
        </header>
        ${error && html`<div class="task-panel__body"><p role="alert">${error.message}</p></div>`}
        ${boxKey && !saved && !error && html`<div class="task-panel__body muted">Loading…</div>`}
        ${(!boxKey || saved) &&
        html`<${EditorForm}
          key=${generation}
          graph=${graph}
          tree=${tree}
          boot=${boot}
          lookup=${lookup}
          boxKey=${boxKey}
          parentKey=${parentKey}
          saved=${saved}
          reload=${reload}
          onDone=${onDone}
          onClose=${guardedClose}
          dirtyRef=${dirty}
        />`}
      </div>
    <//>
  `;
}
