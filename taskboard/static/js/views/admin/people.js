/** Administration › People: the people on the board (leads and helpers), active or not. */
import { api } from "../../api.js";
import { Avatar } from "../../components/badges.js";
import { Dialog } from "../../components/dialog.js";
import { PlusIcon } from "../../components/icons.js";
import { showToast } from "../../components/toasts.js";
import { useApi } from "../../hooks.js";
import { refreshBoot } from "../../store.js";
import { html, useState } from "../../ui.js";
import { PROJECT_COLORS } from "../projects.js";

const PERSON_COLORS = [...new Set(["#2D5BA8", "#7A4A9C", "#1F7A6E", "#A8431A", "#56652A", "#8A3A56", ...PROJECT_COLORS])];

function PersonDialog({ person, boot, onClose, onSaved }) {
  const firstSection = boot.departments[0]?.sections[0]?.id;
  const [form, setForm] = useState(
    person ?? { code: "", name: "", color: PERSON_COLORS[0], email: "", section_id: firstSection, active: true },
  );
  const [error, setError] = useState(null);
  const set = (patch) => setForm({ ...form, ...patch });

  const submit = async (event) => {
    event.preventDefault();
    const body = {
      code: form.code,
      name: form.name,
      color: form.color,
      email: form.email || null,
      section_id: Number(form.section_id),
      active: form.active,
    };
    try {
      if (person) await api.patch(`/admin/people/${person.id}`, body);
      else await api.post("/admin/people", body);
      showToast(`${form.name} saved.`);
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    }
  };

  return html`
    <${Dialog} open title=${person ? person.name : "New person"} onClose=${onClose} wide>
      <form class="stack" onSubmit=${submit}>
        ${error && html`<div class="form-error" role="alert">${error}</div>`}
        <div class="form-grid">
          <label class="field"><span class="field__label">Name</span>
            <input class="input" required value=${form.name} onInput=${(e) => set({ name: e.currentTarget.value })} /></label>
          <label class="field"><span class="field__label">Code (initials)</span>
            <input class="input mono" required maxlength="8" value=${form.code} onInput=${(e) => set({ code: e.currentTarget.value.toUpperCase() })} /></label>
          <label class="field field--wide"><span class="field__label">Email</span>
            <input class="input" type="email" value=${form.email ?? ""} onInput=${(e) => set({ email: e.currentTarget.value })} /></label>
          <label class="field field--wide"><span class="field__label">Section</span>
            <select class="select" onChange=${(e) => set({ section_id: Number(e.currentTarget.value) })}>
              ${boot.departments.map(
                (d) => html`<optgroup key=${d.id} label=${d.code}>
                  ${d.sections.map((s) => html`<option key=${s.id} value=${s.id} selected=${s.id === Number(form.section_id)}>${d.code} · ${s.name}</option>`)}
                </optgroup>`,
              )}
            </select></label>
        </div>
        <div class="field">
          <span class="field__label">Avatar colour</span>
          <div class="row">
            <${Avatar} person=${{ code: form.code || "?", color: form.color, name: form.name }} />
            <div class="swatches" role="group" aria-label="Avatar colour">
              ${PERSON_COLORS.map(
                (color) => html`<button key=${color} type="button" class="swatch" style=${{ "--swatch": color }} aria-label=${color}
                  aria-pressed=${form.color.toUpperCase() === color ? "true" : "false"} onClick=${() => set({ color })}></button>`,
              )}
            </div>
          </div>
        </div>
        <label class="check"><input type="checkbox" checked=${form.active} onChange=${(e) => set({ active: e.currentTarget.checked })} />Active (can be chosen as lead or helper)</label>
        <div class="dialog__actions">
          <button type="button" class="btn" onClick=${onClose}>Cancel</button>
          <button type="submit" class="btn btn--primary">Save</button>
        </div>
      </form>
    <//>
  `;
}

export function PeopleTab({ boot, lookup }) {
  const people = useApi("/admin/people");
  const [editing, setEditing] = useState(null); // null | "new" | person
  const saved = () => {
    people.reload();
    refreshBoot();
  };
  if (people.error) return html`<div class="panel empty-state" role="alert">${people.error.message}</div>`;
  if (!people.data) return html`<div class="panel empty-state">Loading…</div>`;
  return html`
    <div class="section-head">
      <div><h2>People</h2><p>Everyone who can lead or help on tasks. People who leave are made inactive, not deleted.</p></div>
      <button type="button" class="btn btn--primary" onClick=${() => setEditing("new")}><${PlusIcon} />New person</button>
    </div>
    <div class="panel table-wrap">
      <table class="data-table">
        <thead><tr><th>Name</th><th>Section</th><th>Email</th><th>Account</th><th>Status</th></tr></thead>
        <tbody>
          ${people.data.map((p) => {
            const section = lookup.sections.get(p.section_id);
            const department = lookup.departments.get(p.department_id);
            return html`
              <tr key=${p.id} class="is-clickable" onClick=${() => setEditing(p)}>
                <td><div class="who"><${Avatar} person=${p} size="small" />
                  <div class="who__text"><button type="button" class="link-button" style=${{ padding: 0, textAlign: "left" }}>${p.name}</button><span class="who__sub">${p.code}</span></div></div></td>
                <td>${department?.code} · ${section?.name}</td>
                <td>${p.email ?? "—"}</td>
                <td>${p.user_id ? "Linked" : "—"}</td>
                <td>${p.active ? html`<span class="status status--active">Active</span>` : html`<span class="badge">Inactive</span>`}</td>
              </tr>
            `;
          })}
        </tbody>
      </table>
    </div>
    ${editing &&
    html`<${PersonDialog} key=${editing === "new" ? "new" : editing.id} person=${editing === "new" ? null : editing} boot=${boot} onClose=${() => setEditing(null)} onSaved=${saved} />`}
  `;
}
