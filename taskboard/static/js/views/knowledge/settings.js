/** "Kinds & link types" (the MapSettings mockup): the box kinds and link types every map uses.
 * Everyone who reads maps sees them; `knowledge.configure` adds, renames, restyles and deletes. */
import { api } from "../../api.js";
import { Dialog } from "../../components/dialog.js";
import { TrashIcon } from "../../components/icons.js";
import { showError } from "../../components/toasts.js";
import { useApi } from "../../hooks.js";
import { html, useState } from "../../ui.js";

// The palette entries a kind may use (domain/knowledge.py KIND_STYLES).
const STYLES = ["step", "sand", "blue", "violet", "peach", "ink", "green", "rose", "teal", "grey"];

const ROLE_FEATURES = {
  step: "Builds the tree",
  rule: "Says what it protects",
  failure_mode: "Controls",
  defect: "Own view",
};

function features(kind) {
  const list = [];
  if (ROLE_FEATURES[kind.role]) list.push(ROLE_FEATURES[kind.role]);
  if (kind.has_facts) list.push("Key facts table");
  if (kind.has_main_url) list.push("Main URL");
  if (kind.field_schema.length) list.push(`${kind.field_schema.length} extra field${kind.field_schema.length === 1 ? "" : "s"}`);
  return list;
}

/** Extra fields of a kind or link type: key, label, text or number. */
function FieldsEditor({ fields, onChange }) {
  const set = (i, patch) => onChange(fields.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  return html`
    <div class="fields-editor">
      ${fields.map(
        (f, i) => html`
          <div key=${i} class="fields-editor__row">
            <input class="input input--mono" aria-label=${`Field ${i + 1} key`} placeholder="key" pattern="[a-z][a-z0-9_]{0,39}" value=${f.key} onInput=${(e) => set(i, { key: e.currentTarget.value })} />
            <input class="input" aria-label=${`Field ${i + 1} label`} placeholder="Label" value=${f.label} onInput=${(e) => set(i, { label: e.currentTarget.value })} />
            <select class="select" aria-label=${`Field ${i + 1} type`} value=${f.type} onChange=${(e) => set(i, { type: e.currentTarget.value })}>
              <option value="text">Text</option>
              <option value="number">Number</option>
            </select>
            <button type="button" class="icon-btn" aria-label=${`Remove field ${i + 1}`} onClick=${() => onChange(fields.filter((_, j) => j !== i))}><${TrashIcon} /></button>
          </div>
        `,
      )}
      <button type="button" class="btn btn--dashed btn--small" onClick=${() => onChange([...fields, { key: "", label: "", type: "text" }])}>+ Extra field</button>
    </div>
  `;
}

function KindForm({ kind = null, onSave, onCancel }) {
  const [form, setForm] = useState(() => ({
    name: kind?.name ?? "",
    description: kind?.description ?? "",
    style: kind?.style ?? "grey",
    has_facts: kind?.has_facts ?? false,
    has_main_url: kind?.has_main_url ?? false,
    field_schema: kind?.field_schema ?? [],
  }));
  const set = (patch) => setForm({ ...form, ...patch });
  return html`
    <form
      class="settings-form"
      aria-label=${kind ? `Edit the kind ${kind.name}` : "New kind"}
      onSubmit=${(e) => {
        e.preventDefault();
        onSave(form);
      }}
    >
      <div class="settings-form__row">
        <label class="field field--compact"><span class="field__label">Name</span><input class="input" required value=${form.name} onInput=${(e) => set({ name: e.currentTarget.value })} /></label>
        <label class="field field--compact">
          <span class="field__label">Style</span>
          <select class="select" value=${form.style} onChange=${(e) => set({ style: e.currentTarget.value })}>
            ${STYLES.map((s) => html`<option key=${s} value=${s}>${s}</option>`)}
          </select>
        </label>
      </div>
      <label class="field field--compact"><span class="field__label">Description</span><input class="input" value=${form.description} onInput=${(e) => set({ description: e.currentTarget.value })} /></label>
      <label class="check-line"><input type="checkbox" checked=${form.has_facts} onChange=${(e) => set({ has_facts: e.currentTarget.checked })} />Key facts table</label>
      <label class="check-line"><input type="checkbox" checked=${form.has_main_url} onChange=${(e) => set({ has_main_url: e.currentTarget.checked })} />Main URL</label>
      <${FieldsEditor} fields=${form.field_schema} onChange=${(field_schema) => set({ field_schema })} />
      <div class="settings-form__foot">
        <button type="button" class="btn" onClick=${onCancel}>Cancel</button>
        <button type="submit" class="btn btn--dark">${kind ? "Save kind" : "Add kind"}</button>
      </div>
    </form>
  `;
}

function LinkTypeForm({ linkType = null, onSave, onCancel }) {
  const [form, setForm] = useState(() => ({
    forward_name: linkType?.forward_name ?? "",
    backward_name: linkType?.backward_name ?? "",
    description: linkType?.description ?? "",
    field_schema: linkType?.field_schema ?? [],
  }));
  const set = (patch) => setForm({ ...form, ...patch });
  return html`
    <form
      class="settings-form"
      aria-label=${linkType ? `Edit the link type ${linkType.forward_name}` : "New link type"}
      onSubmit=${(e) => {
        e.preventDefault();
        onSave(form);
      }}
    >
      <div class="settings-form__row">
        <label class="field field--compact"><span class="field__label">Forward</span><input class="input" required value=${form.forward_name} onInput=${(e) => set({ forward_name: e.currentTarget.value })} /></label>
        <label class="field field--compact"><span class="field__label">Backward</span><input class="input" required value=${form.backward_name} onInput=${(e) => set({ backward_name: e.currentTarget.value })} /></label>
      </div>
      <label class="field field--compact"><span class="field__label">Used for</span><input class="input" value=${form.description} onInput=${(e) => set({ description: e.currentTarget.value })} /></label>
      <${FieldsEditor} fields=${form.field_schema} onChange=${(field_schema) => set({ field_schema })} />
      <div class="settings-form__foot">
        <button type="button" class="btn" onClick=${onCancel}>Cancel</button>
        <button type="submit" class="btn btn--dark">${linkType ? "Save link type" : "Add link type"}</button>
      </div>
    </form>
  `;
}

function SettingsBody({ onChanged }) {
  const { data, error, reload } = useApi("/map-settings");
  const [editing, setEditing] = useState(null); // "kind:<key>" | "kind:new" | "type:<key>" | "type:new"
  if (error) return html`<p role="alert">${error.message}</p>`;
  if (!data) return html`<p class="muted">Loading…</p>`;
  const can = data.can_configure;
  const run = async (request) => {
    try {
      await request();
      setEditing(null);
      reload();
      onChanged();
    } catch (err) {
      showError(err);
    }
  };
  const fields = (list) => list.filter((f) => f.key.trim()).map((f) => ({ ...f, key: f.key.trim() }));
  return html`
    <div class="settings">
      <p class="muted">Every box in a process map has a kind, and boxes can be linked with a typed link. Add your own when something doesn't fit.</p>
      <section class="settings__section" aria-label="Box kinds">
        <div class="settings__head">
          <h3>Box kinds</h3>
          ${can && editing !== "kind:new" && html`<button type="button" class="btn btn--dashed btn--small" onClick=${() => setEditing("kind:new")}>+ New kind</button>`}
        </div>
        ${editing === "kind:new" &&
        html`<${KindForm} onCancel=${() => setEditing(null)} onSave=${(form) => run(() => api.post("/box-kinds", { ...form, field_schema: fields(form.field_schema) }))} />`}
        <ul class="settings__list">
          ${data.kinds.map((k) =>
            editing === `kind:${k.key}`
              ? html`<li key=${k.key}><${KindForm} kind=${k} onCancel=${() => setEditing(null)} onSave=${(form) => run(() => api.patch(`/box-kinds/${k.key}`, { ...form, field_schema: fields(form.field_schema) }))} /></li>`
              : html`
                  <li key=${k.key} class="settings__row settings__row--kind">
                    <span class=${`kind-swatch kind-swatch--large kind--${k.style}`} aria-hidden="true"></span>
                    <span class="settings__name">${k.name}</span>
                    <span class="settings__description">${k.description}</span>
                    <span class="settings__features">
                      ${features(k).map((f) => html`<span key=${f} class="scope-tag">${f}</span>`)}
                      <span class="scope-tag">${k.box_count} ${k.box_count === 1 ? "box" : "boxes"}</span>
                    </span>
                    ${can &&
                    html`<span class="settings__actions">
                      <button type="button" class="link-button" aria-label=${`Edit the kind ${k.name}`} onClick=${() => setEditing(`kind:${k.key}`)}>Edit</button>
                      ${!k.builtin && k.box_count === 0 && html`<button type="button" class="link-button" aria-label=${`Delete the kind ${k.name}`} onClick=${() => run(() => api.delete(`/box-kinds/${k.key}`))}>Delete</button>`}
                    </span>`}
                  </li>
                `,
          )}
        </ul>
      </section>
      <section class="settings__section" aria-label="Link types">
        <div class="settings__head">
          <h3>Link types</h3>
          ${can && editing !== "type:new" && html`<button type="button" class="btn btn--dashed btn--small" onClick=${() => setEditing("type:new")}>+ New link type</button>`}
        </div>
        <p class="muted">Each link reads both ways, so it shows up on both boxes: “Mould level fluctuation <em>leads to</em> Sliver lines” and “Sliver lines <em>caused by</em> Mould level fluctuation”.</p>
        ${editing === "type:new" &&
        html`<${LinkTypeForm} onCancel=${() => setEditing(null)} onSave=${(form) => run(() => api.post("/link-types", { ...form, field_schema: fields(form.field_schema) }))} />`}
        <ul class="settings__list">
          <li class="settings__row settings__row--type settings__row--head" aria-hidden="true"><span>Forward</span><span>Backward</span><span>Used for</span><span></span></li>
          <li class="settings__row settings__row--type"><span class="settings__name">part of</span><span>contains</span><span class="settings__description">The tree itself. Every box has one place in it.</span><span></span></li>
          ${data.link_types.map((t) =>
            editing === `type:${t.key}`
              ? html`<li key=${t.key}><${LinkTypeForm} linkType=${t} onCancel=${() => setEditing(null)} onSave=${(form) => run(() => api.patch(`/link-types/${t.key}`, { ...form, field_schema: fields(form.field_schema) }))} /></li>`
              : html`
                  <li key=${t.key} class="settings__row settings__row--type">
                    <span class="settings__name">${t.forward_name}</span>
                    <span>${t.backward_name}</span>
                    <span class="settings__description">${t.description}</span>
                    <span class="settings__actions">
                      ${can && html`<button type="button" class="link-button" aria-label=${`Edit the link type ${t.forward_name}`} onClick=${() => setEditing(`type:${t.key}`)}>Edit</button>`}
                      ${can && !t.builtin && t.link_count === 0 && html`<button type="button" class="link-button" aria-label=${`Delete the link type ${t.forward_name}`} onClick=${() => run(() => api.delete(`/link-types/${t.key}`))}>Delete</button>`}
                    </span>
                  </li>
                `,
          )}
        </ul>
      </section>
    </div>
  `;
}

export function MapSettingsDialog({ open, onClose, onChanged }) {
  return html`
    <${Dialog} open=${open} title="Kinds & link types" onClose=${onClose} large>
      <${SettingsBody} onChanged=${onChanged} />
      <div class="dialog__actions"><button type="button" class="btn btn--dark" onClick=${onClose}>Done</button></div>
    <//>
  `;
}
