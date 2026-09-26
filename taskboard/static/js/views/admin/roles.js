/** Administration › Roles: built-in roles (read-only) and custom roles with chosen permissions. */
import { api } from "../../api.js";
import { PlusIcon } from "../../components/icons.js";
import { showError, showToast } from "../../components/toasts.js";
import { useApi } from "../../hooks.js";
import { plural } from "../../lib/format.js";
import { html, useState } from "../../ui.js";

function PermissionChecks({ permissions, selected, onChange, disabled }) {
  const toggle = (value) =>
    onChange(selected.includes(value) ? selected.filter((p) => p !== value) : [...selected, value]);
  return html`
    <div class="permission-list">
      ${permissions.map(
        (p) => html`
          <label key=${p.value} class="check">
            <input type="checkbox" checked=${selected.includes(p.value)} disabled=${disabled} onChange=${() => toggle(p.value)} />
            <span><span class="mono">${p.value}</span><small>${p.description}${p.scoped ? "" : " (always everywhere)"}</small></span>
          </label>
        `,
      )}
    </div>
  `;
}

function RoleCard({ role, permissions, onChanged }) {
  const [draft, setDraft] = useState({ name: role.name, description: role.description, permissions: role.permissions });
  const dirty =
    draft.name !== role.name || draft.description !== role.description || draft.permissions.slice().sort().join() !== role.permissions.join();

  const call = async (request, message) => {
    try {
      await request();
      showToast(message);
      onChanged();
    } catch (err) {
      showError(err);
    }
  };
  return html`
    <section class="role-card" aria-label=${`Role ${role.name}`}>
      <div class="role-card__head">
        ${role.is_builtin
          ? html`<h3>${role.name}</h3>`
          : html`<input class="input" style=${{ maxWidth: "260px" }} aria-label="Role name" value=${draft.name} onInput=${(e) => setDraft({ ...draft, name: e.currentTarget.value })} />`}
        <span class="mono muted">${role.key}</span>
        ${role.is_builtin && html`<span class="badge">Built-in</span>`}
        <span class="muted">${plural(role.assignment_count, "assignment")}</span>
      </div>
      <${PermissionChecks}
        permissions=${permissions}
        selected=${draft.permissions}
        disabled=${role.is_builtin}
        onChange=${(selected) => setDraft({ ...draft, permissions: selected })}
      />
      ${!role.is_builtin &&
      html`<div class="row">
        <button type="button" class="btn" disabled=${!dirty} onClick=${() => call(() => api.patch(`/admin/roles/${role.id}`, draft), "Role saved.")}>Save</button>
        <button
          type="button"
          class="btn btn--danger"
          onClick=${() => window.confirm(`Delete the role ${role.name}?`) && call(() => api.delete(`/admin/roles/${role.id}`), "Role deleted.")}
        >Delete</button>
      </div>`}
    </section>
  `;
}

function NewRoleForm({ permissions, onCreated }) {
  const [form, setForm] = useState({ key: "", name: "", permissions: ["task.view"] });
  const submit = async (event) => {
    event.preventDefault();
    try {
      await api.post("/admin/roles", form);
      showToast(`Role ${form.name} created.`);
      setForm({ key: "", name: "", permissions: ["task.view"] });
      onCreated();
    } catch (err) {
      showError(err);
    }
  };
  return html`
    <form class="role-card" onSubmit=${submit} aria-label="New role">
      <div class="role-card__head"><h3>New role</h3></div>
      <div class="form-grid">
        <label class="field"><span class="field__label">Name</span>
          <input class="input" required value=${form.name} onInput=${(e) => setForm({ ...form, name: e.currentTarget.value })} /></label>
        <label class="field"><span class="field__label">Key (lowercase letters, digits, - or _)</span>
          <input class="input mono" required pattern="[a-z][a-z0-9_\\-]{1,49}" value=${form.key} onInput=${(e) => setForm({ ...form, key: e.currentTarget.value })} /></label>
      </div>
      <${PermissionChecks} permissions=${permissions} selected=${form.permissions} onChange=${(selected) => setForm({ ...form, permissions: selected })} />
      <div class="row"><button type="submit" class="btn btn--primary"><${PlusIcon} />Create role</button></div>
    </form>
  `;
}

export function RolesTab() {
  const roles = useApi("/admin/roles");
  const permissions = useApi("/admin/permissions");
  if (roles.error) return html`<div class="panel empty-state" role="alert">${roles.error.message}</div>`;
  if (!roles.data || !permissions.data) return html`<div class="panel empty-state">Loading…</div>`;
  return html`
    <div class="section-head">
      <div><h2>Roles</h2><p>A role bundles permissions; accounts get roles everywhere, for a department, or for one section.</p></div>
    </div>
    <div class="panel">
      ${roles.data.map(
        (role) => html`<${RoleCard} key=${`${role.id}:${role.permissions.join()}:${role.name}`} role=${role} permissions=${permissions.data} onChanged=${roles.reload} />`,
      )}
      <${NewRoleForm} permissions=${permissions.data} onCreated=${roles.reload} />
    </div>
  `;
}
