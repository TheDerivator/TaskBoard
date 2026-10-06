/** Profile: your account, and API tokens that let an AI agent or a script work on the board as you
 * (D-097), with the guide to give the agent. */
import { api } from "../api.js";
import { Avatar } from "../components/badges.js";
import { copyText } from "../components/copy-link.js";
import { Dialog } from "../components/dialog.js";
import { DownloadIcon, PlusIcon } from "../components/icons.js";
import { showError, showToast } from "../components/toasts.js";
import { useApi, useTitle } from "../hooks.js";
import { formatDate } from "../lib/format.js";
import { DEFAULT_EXPIRY, EXPIRY_CHOICES, SCOPES, envCommands, expiryText, lastUsedText, scopeLabel } from "../lib/tokens.js";
import { href } from "../router.js";
import { html, useState } from "../ui.js";

const GUIDE_FILE = "taskboard-agent-guide.md";

function GuideLink({ primary = false }) {
  return html`<a class=${`btn${primary ? " btn--primary" : ""}`} href=${href("api/agent-guide")} download=${GUIDE_FILE}><${DownloadIcon} />Download the agent guide</a>`;
}

function CopyButton({ text, label }) {
  const copy = async () => {
    try {
      await copyText(text);
      showToast("Copied.");
    } catch {
      window.prompt("Copy this:", text);
    }
  };
  return html`<button type="button" class="btn" onClick=${copy} aria-label=${label}>Copy</button>`;
}

function NewTokenDialog({ onClose, onCreated }) {
  const [form, setForm] = useState({ name: "", scope: "read", expires: String(DEFAULT_EXPIRY) });
  const [busy, setBusy] = useState(false);
  const set = (patch) => setForm({ ...form, ...patch });
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const created = await api.post("/auth/tokens", {
        name: form.name,
        scope: form.scope,
        expires_in_days: form.expires === "" ? null : Number(form.expires),
      });
      onCreated(created);
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  };
  return html`
    <${Dialog} open title="New API token" onClose=${onClose}>
      <form class="stack" onSubmit=${submit}>
        <label class="field">
          <span class="field__label">Name</span>
          <input class="input" required maxlength="100" placeholder="Claude Code on my laptop" value=${form.name} onInput=${(e) => set({ name: e.currentTarget.value })} />
          <span class="field__hint">Shown next to everything the agent writes ("via …"), so name the agent or the script.</span>
        </label>
        <fieldset class="choice-list">
          <legend class="field__label">Access</legend>
          ${SCOPES.map(
            (s) => html`
              <label key=${s.value} class="check token-scope">
                <input type="radio" name="scope" checked=${form.scope === s.value} onChange=${() => set({ scope: s.value })} />
                <span><strong>${s.label}</strong><span class="field__hint">${s.hint}</span></span>
              </label>
            `,
          )}
        </fieldset>
        <label class="field">
          <span class="field__label">Expires after</span>
          <select class="select" value=${form.expires} onChange=${(e) => set({ expires: e.currentTarget.value })}>
            ${EXPIRY_CHOICES.map((c) => html`<option key=${c.label} value=${c.days ?? ""}>${c.label}</option>`)}
          </select>
        </label>
        <div class="dialog__actions">
          <button type="button" class="btn" onClick=${onClose}>Cancel</button>
          <button type="submit" class="btn btn--primary" disabled=${busy || !form.name.trim()}>Create token</button>
        </div>
      </form>
    <//>
  `;
}

/** The new token, once: copy it, put it where the agent looks, hand over the guide. */
function TokenCreatedDialog({ created, onClose }) {
  return html`
    <${Dialog} open title="Your new token" onClose=${onClose} wide>
      <div class="stack">
        <p>Copy it now: it is not shown again. Anyone who has it can act as you (${scopeLabel(created.token.scope).toLowerCase()}) until it expires or you revoke it.</p>
        <div class="secret-box">
          <code data-testid="token-secret">${created.secret}</code>
          <${CopyButton} text=${created.secret} label="Copy the token" />
        </div>
        <h3 class="token-steps__title">Give it to your agent</h3>
        <p>Store it in the <code>TASKBOARD_TOKEN</code> environment variable on the computer where the agent runs, rather than pasting it into a chat:</p>
        <div class="token-commands">
          ${envCommands(created.secret).map(
            (c) => html`
              <div key=${c.shell} class="token-command">
                <span class="field__label">${c.shell}</span>
                <div class="row">
                  <code class="token-command__code">${c.command}</code>
                  <${CopyButton} text=${c.command} label=${`Copy the command for ${c.shell}`} />
                </div>
              </div>
            `,
          )}
        </div>
        <p>Then give the agent the guide. It explains the board's API and how to use the token, and contains no token itself.</p>
        <div class="dialog__actions">
          <${GuideLink} />
          <button type="button" class="btn btn--primary" onClick=${onClose}>Done</button>
        </div>
      </div>
    <//>
  `;
}

function TokenTable({ tokens, onRevoke }) {
  return html`
    <div class="panel table-wrap">
      <table class="data-table">
        <thead>
          <tr><th>Name</th><th>Access</th><th>Created</th><th>Expires</th><th>Last used</th><th><span class="visually-hidden">Revoke</span></th></tr>
        </thead>
        <tbody>
          ${tokens.length === 0 && html`<tr><td colspan="6" class="muted">No tokens yet.</td></tr>`}
          ${tokens.map(
            (t) => html`
              <tr key=${t.id} class=${t.expired ? "is-expired" : undefined}>
                <td>${t.name}<div class="who__sub mono">${t.prefix}…</div></td>
                <td>${scopeLabel(t.scope)}</td>
                <td>${formatDate(t.created_at)}</td>
                <td>${expiryText(t)}</td>
                <td title=${t.last_used_ip ? `From ${t.last_used_ip}` : undefined}>${lastUsedText(t)}</td>
                <td><button type="button" class="btn btn--danger" onClick=${() => onRevoke(t)}>${t.expired ? "Remove" : "Revoke"}</button></td>
              </tr>
            `,
          )}
        </tbody>
      </table>
    </div>
  `;
}

function AgentAccess() {
  const tokens = useApi("/auth/tokens");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState(null);
  const revoke = async (token) => {
    if (!token.expired && !window.confirm(`Revoke “${token.name}”? Whatever uses it is refused from now on.`)) return;
    try {
      await api.delete(`/auth/tokens/${token.id}`);
      showToast(token.expired ? `${token.name} removed.` : `${token.name} revoked.`);
      tokens.reload();
    } catch (error) {
      showError(error);
    }
  };
  return html`
    <section class="stack profile-section" aria-labelledby="agents-title">
      <div class="section-head">
        <div>
          <h2 id="agents-title">AI assistants and scripts</h2>
          <p>
            Let an AI agent (Claude Code, GitHub Copilot, …) or a script work on the board for you. It acts as you, with your
            rights, through a token you can revoke at any time. What it writes shows as yours, marked “via” the token's name.
            Administration is never possible through a token.
          </p>
        </div>
        <button type="button" class="btn btn--primary" onClick=${() => setCreating(true)}><${PlusIcon} />New token</button>
      </div>
      <ol class="token-steps">
        <li>Create a token: <em>read only</em> to look things up and report, <em>read and write</em> to let it make changes.</li>
        <li>Store it in the <code>TASKBOARD_TOKEN</code> environment variable where the agent runs.</li>
        <li>Give the agent the guide (or let it fetch <code>api/agent-guide</code> itself).</li>
      </ol>
      <div class="row"><${GuideLink} /></div>
      ${tokens.error && html`<div class="panel empty-state" role="alert">${tokens.error.message}</div>`}
      ${!tokens.data && !tokens.error && html`<div class="panel empty-state">Loading…</div>`}
      ${tokens.data && html`<${TokenTable} tokens=${tokens.data} onRevoke=${revoke} />`}
      ${creating &&
      html`<${NewTokenDialog}
        onClose=${() => setCreating(false)}
        onCreated=${(result) => {
          setCreating(false);
          setCreated(result);
          tokens.reload();
        }}
      />`}
      ${created && html`<${TokenCreatedDialog} created=${created} onClose=${() => setCreated(null)} />`}
    </section>
  `;
}

export function ProfileView({ boot, lookup }) {
  useTitle("Profile");
  const me = boot.me;
  const person = lookup.personForUser;
  const section = person ? lookup.sections.get(person.section_id) : null;
  const department = section ? lookup.departments.get(section.department_id) : null;
  return html`
    <section class="page page--profile" aria-labelledby="profile-title">
      <header class="view-head">
        <div class="view-head__text">
          <h1 id="profile-title">Profile</h1>
          <p>Your account, and access for your AI assistant.</p>
        </div>
      </header>
      <div class="panel profile-card">
        <${Avatar} person=${person} name=${me.display_name} />
        <div>
          <div class="profile-card__name">${me.display_name}</div>
          <div class="muted">
            @${me.username}${department ? ` · ${department.code} › ${section.name}` : ""}${me.signed_in_by ? ` · signed in through ${me.signed_in_by}` : ""}
          </div>
        </div>
      </div>
      <${AgentAccess} />
    </section>
  `;
}
