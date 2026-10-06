/** Administration › Accounts: list, create (local or SSO pre-provisioned), edit, rights, passwords,
 * API tokens. */
import { api } from "../../api.js";
import { Avatar } from "../../components/badges.js";
import { Dialog } from "../../components/dialog.js";
import { CloseIcon, PlusIcon } from "../../components/icons.js";
import { showError, showToast } from "../../components/toasts.js";
import { useApi } from "../../hooks.js";
import { formatDate } from "../../lib/format.js";
import { parseScope, scopeOptions } from "../../lib/scopes.js";
import { expiryText, lastUsedText, scopeLabel } from "../../lib/tokens.js";
import { refreshBoot } from "../../store.js";
import { html, useState } from "../../ui.js";

const STATUS_LABEL = { active: "Active", suspended: "Suspended", pending: "Waiting for first SSO login" };

function signIn(user) {
  if (user.kind === "anonymous") return "—";
  const methods = [];
  if (user.has_password) methods.push("Password");
  if (user.external_identities.length) methods.push(`SSO (${user.external_identities.map((i) => i.provider).join(", ")})`);
  if (!methods.length) methods.push(user.status === "pending" ? "SSO (not yet)" : "None");
  return methods.join(" + ");
}

function ScopeSelect({ departments, value, onChange, label = "Where" }) {
  const options = scopeOptions(departments);
  return html`
    <label class="field">
      <span class="field__label">${label}</span>
      <select class="select" value=${value} onChange=${(e) => onChange(e.currentTarget.value)}>
        ${options.map((o) => html`<option key=${o.value} value=${o.value} selected=${o.value === value}>${o.label}</option>`)}
      </select>
    </label>
  `;
}

function RoleSelect({ roles, value, onChange }) {
  return html`
    <label class="field">
      <span class="field__label">Role</span>
      <select class="select" onChange=${(e) => onChange(Number(e.currentTarget.value))}>
        ${roles.map((r) => html`<option key=${r.id} value=${r.id} selected=${r.id === value}>${r.name}</option>`)}
      </select>
    </label>
  `;
}

/** Shows a generated password once, with a copy button. */
function SecretBox({ password, label }) {
  return html`
    <div class="stack" style=${{ gap: "6px" }}>
      <span class="field__label">${label}</span>
      <div class="secret-box">
        <code>${password}</code>
        <button type="button" class="btn" onClick=${() => navigator.clipboard?.writeText(password).then(() => showToast("Copied."))}>Copy</button>
      </div>
      <p class="muted">Pass it on securely. It is not shown again, and must be changed at first login.</p>
    </div>
  `;
}

function NewUserDialog({ open, onClose, roles, boot, onCreated }) {
  const [form, setForm] = useState({ username: "", display_name: "", email: "", method: "generated", password: "", person_id: "" });
  const [grant, setGrant] = useState({ role_id: "", scope: "global" });
  const [error, setError] = useState(null);
  const [created, setCreated] = useState(null);
  const set = (patch) => setForm({ ...form, ...patch });

  const close = () => {
    setCreated(null);
    setError(null);
    setForm({ username: "", display_name: "", email: "", method: "generated", password: "", person_id: "" });
    onClose();
  };

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    const body = {
      username: form.username,
      display_name: form.display_name,
      email: form.email || null,
      person_id: form.person_id ? Number(form.person_id) : null,
      sso_only: form.method === "sso",
      password: form.method === "chosen" ? form.password : null,
      assignments: grant.role_id ? [{ role_id: Number(grant.role_id), ...parseScope(grant.scope) }] : [],
    };
    try {
      const result = await api.post("/admin/users", body);
      setCreated(result);
      onCreated();
    } catch (err) {
      setError(err.message);
    }
  };

  const linkable = boot.people.filter((p) => p.active);
  return html`
    <${Dialog} open=${open} title="New account" onClose=${close} large>
      ${created
        ? html`<div class="stack">
            <p><strong>${created.user.display_name}</strong> (@${created.user.username}) can now ${created.user.status === "pending" ? "sign in through SSO; the account activates at the first login." : "log in."}</p>
            ${created.generated_password && html`<${SecretBox} password=${created.generated_password} label="Initial password" />`}
            <div class="dialog__actions"><button type="button" class="btn btn--primary" onClick=${close}>Done</button></div>
          </div>`
        : html`<form class="stack" onSubmit=${submit}>
            ${error && html`<div class="form-error" role="alert">${error}</div>`}
            <div class="form-grid">
              <label class="field"><span class="field__label">Username</span>
                <input class="input" required value=${form.username} onInput=${(e) => set({ username: e.currentTarget.value })} /></label>
              <label class="field"><span class="field__label">Display name</span>
                <input class="input" required value=${form.display_name} onInput=${(e) => set({ display_name: e.currentTarget.value })} /></label>
              <label class="field field--wide"><span class="field__label">Email (SSO accounts are matched on it; not needed for Windows sign-in)</span>
                <input class="input" type="email" value=${form.email} required=${form.method === "sso" && !boot.me.login.windows} onInput=${(e) => set({ email: e.currentTarget.value })} /></label>
            </div>
            <fieldset class="choice-list"><legend class="field__label">Sign-in</legend>
              <div class="choice-row">
                ${[
                  ["generated", "Password, generated"],
                  ["chosen", "Password, I choose"],
                  ["sso", "SSO only (pre-provisioned)"],
                ].map(
                  ([value, label]) => html`<label key=${value}><input type="radio" name="method" checked=${form.method === value} onChange=${() => set({ method: value })} />${label}</label>`,
                )}
              </div>
            </fieldset>
            ${form.method === "chosen" &&
            html`<label class="field"><span class="field__label">Password (at least 10 characters)</span>
              <input class="input" type="password" autocomplete="new-password" required minlength="10" value=${form.password} onInput=${(e) => set({ password: e.currentTarget.value })} /></label>`}
            <label class="field"><span class="field__label">Person on the board (optional)</span>
              <select class="select" onChange=${(e) => set({ person_id: e.currentTarget.value })}>
                <option value="">— none —</option>
                ${linkable.map((p) => html`<option key=${p.id} value=${p.id} selected=${String(p.id) === form.person_id}>${p.name}</option>`)}
              </select></label>
            <div class="assign-row">
              <label class="field"><span class="field__label">Initial role (optional)</span>
                <select class="select" onChange=${(e) => setGrant({ ...grant, role_id: e.currentTarget.value })}>
                  <option value="">— none —</option>
                  ${roles.map((r) => html`<option key=${r.id} value=${r.id}>${r.name}</option>`)}
                </select></label>
              <${ScopeSelect} departments=${boot.departments} value=${grant.scope} onChange=${(scope) => setGrant({ ...grant, scope })} />
            </div>
            <div class="dialog__actions">
              <button type="button" class="btn" onClick=${close}>Cancel</button>
              <button type="submit" class="btn btn--primary">Create account</button>
            </div>
          </form>`}
    <//>
  `;
}

/** The account's API tokens (D-097): what acts as this person, and revoking it. */
function UserTokens({ user }) {
  const tokens = useApi(`/admin/users/${user.id}/tokens`);
  const revoke = async (token) => {
    if (!window.confirm(`Revoke “${token.name}” of ${user.display_name}?`)) return;
    try {
      await api.delete(`/admin/users/${user.id}/tokens/${token.id}`);
      showToast(`${token.name} revoked.`);
      tokens.reload();
    } catch (err) {
      showError(err);
    }
  };
  if (!tokens.data) return null;
  return html`
    <div class="stack" style=${{ gap: "8px" }}>
      <span class="field__label">API tokens (AI agents and scripts)</span>
      ${tokens.data.length === 0 && html`<span class="muted">None.</span>`}
      ${tokens.data.map(
        (t) => html`
          <div key=${t.id} class="row token-row">
            <span><strong>${t.name}</strong> · ${scopeLabel(t.scope)} · ${expiryText(t)} · ${lastUsedText(t)}</span>
            <span class="spacer" style=${{ flex: 1 }}></span>
            <button type="button" class="btn btn--danger" onClick=${() => revoke(t)}>Revoke</button>
          </div>
        `,
      )}
    </div>
  `;
}

function UserDialog({ user, onClose, roles, boot, me, onChanged }) {
  const [form, setForm] = useState({ display_name: user.display_name, email: user.email ?? "", person_id: user.person_id ?? "" });
  const [grant, setGrant] = useState({ role_id: roles[0]?.id, scope: "global" });
  const [password, setPassword] = useState(null);
  const [error, setError] = useState(null);
  const anonymous = user.kind === "anonymous";
  const self = user.username === me.username;

  const call = async (request, message) => {
    setError(null);
    try {
      const result = await request();
      onChanged();
      if (message) showToast(message);
      return result;
    } catch (err) {
      setError(err.message);
      return null;
    }
  };
  const base = `/admin/users/${user.id}`;
  const save = (event) => {
    event.preventDefault();
    call(
      () =>
        api.patch(base, {
          display_name: form.display_name,
          email: form.email || null,
          person_id: form.person_id === "" ? null : Number(form.person_id),
        }),
      "Account saved.",
    );
  };
  const setStatus = (status) => call(() => api.patch(base, { status }), status === "suspended" ? "Account suspended." : "Account reactivated.");
  const reset = async () => {
    if (!window.confirm(`Give ${user.display_name} a new password? They are logged out everywhere.`)) return;
    const result = await call(() => api.post(`${base}/password`, {}));
    if (result) setPassword(result.generated_password);
  };

  return html`
    <${Dialog} open title=${anonymous ? "Anonymous visitors" : user.display_name} onClose=${onClose} large>
      <div class="stack">
        ${error && html`<div class="form-error" role="alert">${error}</div>`}
        ${anonymous
          ? html`<p class="muted">Everyone who is not logged in. What you grant here also applies to every account, as a minimum. Remove all roles to make the board login-only.</p>`
          : html`<form class="stack" onSubmit=${save}>
              <div class="form-grid">
                <label class="field"><span class="field__label">Display name</span>
                  <input class="input" required value=${form.display_name} onInput=${(e) => setForm({ ...form, display_name: e.currentTarget.value })} /></label>
                <label class="field"><span class="field__label">Email</span>
                  <input class="input" type="email" value=${form.email} onInput=${(e) => setForm({ ...form, email: e.currentTarget.value })} /></label>
                <label class="field field--wide"><span class="field__label">Person on the board</span>
                  <select class="select" onChange=${(e) => setForm({ ...form, person_id: e.currentTarget.value })}>
                    <option value="" selected=${form.person_id === ""}>— none —</option>
                    ${boot.people.map((p) => html`<option key=${p.id} value=${p.id} selected=${String(p.id) === String(form.person_id)}>${p.name}</option>`)}
                  </select></label>
              </div>
              <div class="row">
                <span>@${user.username} · ${signIn(user)} · <span class=${`status status--${user.status}`}>${STATUS_LABEL[user.status]}</span></span>
                <span class="spacer" style=${{ flex: 1 }}></span>
                <button type="submit" class="btn">Save details</button>
              </div>
            </form>`}

        <div class="stack" style=${{ gap: "8px" }}>
          <span class="field__label">Access rights</span>
          <div class="chips">
            ${user.assignments.length === 0 && html`<span class="muted">No roles.</span>`}
            ${user.assignments.map(
              (a) => html`<span key=${a.id} class="chip">${a.role_name} · ${a.scope_label}
                <button type="button" aria-label=${`Remove ${a.role_name} (${a.scope_label})`} onClick=${() => call(() => api.delete(`${base}/assignments/${a.id}`), "Right removed.")}>
                  <${CloseIcon} size=${12} />
                </button></span>`,
            )}
          </div>
          <div class="assign-row">
            <${RoleSelect} roles=${roles} value=${grant.role_id} onChange=${(role_id) => setGrant({ ...grant, role_id })} />
            <${ScopeSelect} departments=${boot.departments} value=${grant.scope} onChange=${(scope) => setGrant({ ...grant, scope })} />
            <button type="button" class="btn" onClick=${() => call(() => api.post(`${base}/assignments`, { role_id: grant.role_id, ...parseScope(grant.scope) }), "Right granted.")}>
              <${PlusIcon} />Grant
            </button>
          </div>
        </div>

        ${!anonymous && html`<${UserTokens} user=${user} />`}
        ${!anonymous &&
        html`<div class="row" style=${{ flexWrap: "wrap" }}>
          <button type="button" class="btn" onClick=${reset}>Reset password</button>
          ${!self &&
          (user.status === "suspended"
            ? html`<button type="button" class="btn" onClick=${() => setStatus("active")}>Reactivate</button>`
            : html`<button type="button" class="btn btn--danger" onClick=${() => setStatus("suspended")}>Suspend</button>`)}
        </div>`}
        ${password && html`<${SecretBox} password=${password} label="New password" />`}
      </div>
    <//>
  `;
}

export function UsersTab({ boot }) {
  const users = useApi("/admin/users");
  const roles = useApi("/admin/roles");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);

  const changed = () => {
    users.reload();
    refreshBoot();
  };
  if (users.error) return html`<div class="panel empty-state" role="alert">${users.error.message}</div>`;
  if (!users.data || !roles.data) return html`<div class="panel empty-state">Loading…</div>`;
  const current = editing ? users.data.find((u) => u.id === editing) : null;

  return html`
    <div class="section-head">
      <div><h2>Accounts</h2><p>Who can log in, and what they may do where.</p></div>
      <button type="button" class="btn btn--primary" onClick=${() => setCreating(true)}><${PlusIcon} />New account</button>
    </div>
    <div class="panel table-wrap">
      <table class="data-table">
        <thead><tr><th>Name</th><th>Status</th><th>Access</th><th>Sign-in</th><th>Last login</th></tr></thead>
        <tbody>
          ${users.data.map(
            (u) => html`
              <tr key=${u.id} class=${`is-clickable${u.kind === "anonymous" ? " anonymous-row" : ""}`} onClick=${() => setEditing(u.id)}>
                <td>
                  <div class="who">
                    <${Avatar} person=${boot.people.find((p) => p.id === u.person_id)} name=${u.display_name} size="small" />
                    <div class="who__text">
                      <button type="button" class="link-button" style=${{ padding: 0, textAlign: "left" }}>${u.kind === "anonymous" ? "Anonymous visitors" : u.display_name}</button>
                      <span class="who__sub">${u.kind === "anonymous" ? html`<em>not logged in; the minimum for everyone</em>` : `@${u.username}`}</span>
                    </div>
                  </div>
                </td>
                <td>${u.kind === "anonymous" ? "" : html`<span class=${`status status--${u.status}`}>${STATUS_LABEL[u.status]}</span>`}</td>
                <td><div class="chips">${u.assignments.map((a) => html`<span key=${a.id} class="chip">${a.role_name} · ${a.scope_label}</span>`)}</div></td>
                <td>${signIn(u)}</td>
                <td class="mono">${u.last_login_at ? formatDate(u.last_login_at, { withTime: true }) : "—"}</td>
              </tr>
            `,
          )}
        </tbody>
      </table>
    </div>
    <${NewUserDialog} open=${creating} onClose=${() => setCreating(false)} roles=${roles.data} boot=${boot} onCreated=${changed} />
    ${current && html`<${UserDialog} key=${current.id} user=${current} roles=${roles.data} boot=${boot} me=${boot.me} onClose=${() => setEditing(null)} onChanged=${changed} />`}
  `;
}
