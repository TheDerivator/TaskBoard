/** Administration › SSO groups: members of an identity-provider group hold a role at a scope. */
import { api } from "../../api.js";
import { CloseIcon, PlusIcon } from "../../components/icons.js";
import { showError, showToast } from "../../components/toasts.js";
import { useApi } from "../../hooks.js";
import { parseScope, scopeOptions } from "../../lib/scopes.js";
import { html, useState } from "../../ui.js";

export function GroupsTab({ boot }) {
  const mappings = useApi("/admin/group-mappings");
  const roles = useApi("/admin/roles");
  const providers = useApi("/admin/sso-providers");
  const [form, setForm] = useState({ provider: "", group_name: "", role_id: "", scope: "global" });

  if (mappings.error) return html`<div class="panel empty-state" role="alert">${mappings.error.message}</div>`;
  if (!mappings.data || !roles.data || !providers.data) return html`<div class="panel empty-state">Loading…</div>`;
  const providerName = form.provider || providers.data[0]?.name || "";
  const roleId = form.role_id || roles.data[0]?.id;

  const add = async (event) => {
    event.preventDefault();
    try {
      await api.post("/admin/group-mappings", {
        provider: providerName,
        group_name: form.group_name,
        role_id: Number(roleId),
        ...parseScope(form.scope),
      });
      showToast(`Members of ${form.group_name} now get that role.`);
      setForm({ ...form, group_name: "" });
      mappings.reload();
    } catch (err) {
      showError(err);
    }
  };
  const remove = async (mapping) => {
    try {
      await api.delete(`/admin/group-mappings/${mapping.id}`);
      mappings.reload();
    } catch (err) {
      showError(err);
    }
  };

  return html`
    <div class="section-head">
      <div>
        <h2>SSO groups</h2>
        <p>Give everyone in a group at your identity provider a role, for as long as they are in the group. The group is checked at each sign-in.</p>
      </div>
    </div>
    ${providers.data.length === 0 &&
    html`<div class="notice"><p>No SSO provider that reports groups is configured (Microsoft Entra ID, or a proxy that passes them on). Mappings take effect once one is set up (see docs/AUTH.md).</p></div>`}
    <div class="panel table-wrap">
      <table class="data-table">
        <thead><tr><th>Provider</th><th>Group</th><th>Role</th><th>Where</th><th><span class="visually-hidden">Remove</span></th></tr></thead>
        <tbody>
          ${mappings.data.length === 0 && html`<tr><td colspan="5" class="muted">No group mappings yet.</td></tr>`}
          ${mappings.data.map(
            (m) => html`
              <tr key=${m.id}>
                <td class="mono">${m.provider}</td>
                <td class="mono">${m.group_name}</td>
                <td>${m.role_name}</td>
                <td>${m.scope_label}</td>
                <td><button type="button" class="icon-btn" aria-label=${`Remove mapping for ${m.group_name}`} onClick=${() => remove(m)}><${CloseIcon} size=${14} /></button></td>
              </tr>
            `,
          )}
        </tbody>
      </table>
    </div>
    <form class="panel stack" style=${{ padding: "16px" }} onSubmit=${add} aria-label="New group mapping">
      <div class="form-grid">
        <label class="field"><span class="field__label">Provider</span>
          <input class="input mono" list="sso-providers" required value=${providerName} onInput=${(e) => setForm({ ...form, provider: e.currentTarget.value })} />
          <datalist id="sso-providers">${providers.data.map((p) => html`<option key=${p.name} value=${p.name}>${p.display_name}</option>`)}</datalist>
        </label>
        <label class="field"><span class="field__label">Group (as the provider sends it; Entra ID: object id)</span>
          <input class="input mono" required value=${form.group_name} onInput=${(e) => setForm({ ...form, group_name: e.currentTarget.value })} /></label>
        <label class="field"><span class="field__label">Role</span>
          <select class="select" onChange=${(e) => setForm({ ...form, role_id: e.currentTarget.value })}>
            ${roles.data.map((r) => html`<option key=${r.id} value=${r.id} selected=${String(r.id) === String(roleId)}>${r.name}</option>`)}
          </select></label>
        <label class="field"><span class="field__label">Where</span>
          <select class="select" onChange=${(e) => setForm({ ...form, scope: e.currentTarget.value })}>
            ${scopeOptions(boot.departments).map((o) => html`<option key=${o.value} value=${o.value} selected=${o.value === form.scope}>${o.label}</option>`)}
          </select></label>
      </div>
      <div class="row"><button type="submit" class="btn btn--primary"><${PlusIcon} />Add mapping</button></div>
    </form>
  `;
}
