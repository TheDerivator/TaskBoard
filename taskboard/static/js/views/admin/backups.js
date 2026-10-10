/** Administration › Backups: the backup folder, the backups in it and why each is kept, and how many to keep. */
import { api } from "../../api.js";
import { showError, showToast } from "../../components/toasts.js";
import { useApi } from "../../hooks.js";
import { KEPT_AS, backupStatus, backupTime, formatSize } from "../../lib/backups.js";
import { html, useState } from "../../ui.js";

const FIELDS = [
  { key: "newest", label: "Newest backups", hint: "The most recent backups." },
  { key: "weekly", label: "Weeks", hint: "The first backup of each of the last weeks that have one." },
  { key: "monthly", label: "Months", hint: "The first backup of each of the last months that have one." },
];

export function BackupsTab() {
  const overview = useApi("/admin/backups");
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  if (overview.error) return html`<div class="panel empty-state" role="alert">${overview.error.message}</div>`;
  if (!overview.data) return html`<div class="panel empty-state">Loading…</div>`;
  const data = overview.data;
  const values = form ?? data.retention;
  const status = backupStatus(data);

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await api.put("/admin/backups/retention", Object.fromEntries(FIELDS.map((f) => [f.key, Number(values[f.key])])));
      showToast("Saved. The next backup deletes the backups no longer kept.");
      setForm(null);
      overview.reload();
    } catch (err) {
      showError(err);
    } finally {
      setSaving(false);
    }
  };

  return html`
    <div class="section-head">
      <div>
        <h2>Backups</h2>
        <p>A scheduled task on the server makes a backup once a day (<code>python -m taskboard backup</code>) and deletes the ones no longer kept. TaskBoard itself never makes or restores backups.</p>
      </div>
    </div>
    <div class=${status.ok ? "notice notice--quiet" : "notice notice--danger"} role=${status.ok ? "status" : "alert"}><p>${status.text}</p></div>
    <div class="panel backup-folder">
      <span class="field__label">Backup folder</span>
      <code>${data.location}</code>
      <span class="field__hint">Set on the server, as TASKBOARD_BACKUP_DIR in the .env file.</span>
    </div>
    <div class="panel table-wrap">
      <table class="data-table">
        <thead><tr><th>Taken</th><th>Size</th><th>Kept as</th></tr></thead>
        <tbody>
          ${data.backups.length === 0 && html`<tr><td colspan="3" class="muted">No backups in this folder.</td></tr>`}
          ${data.backups.map(
            (b) => html`
              <tr key=${b.name}>
                <td><div class="who__text"><span>${backupTime(b.taken_at)}</span><span class="who__sub">${b.name}</span></div></td>
                <td class="backup-size">${formatSize(b.size)}</td>
                <td>
                  ${b.kept_as.length
                    ? html`<div class="chips">${b.kept_as.map((k) => html`<span key=${k} class="chip">${KEPT_AS[k]}</span>`)}</div>`
                    : html`<em class="muted">Deleted at the next backup</em>`}
                </td>
              </tr>
            `,
          )}
        </tbody>
      </table>
    </div>
    <form class="panel stack backup-retention" onSubmit=${save} aria-labelledby="retention-title">
      <div>
        <h3 id="retention-title">How many to keep</h3>
        <p class="field__hint">A backup kept for more than one reason counts for each. Changes apply at the next backup.</p>
      </div>
      <div class="form-grid form-grid--3">
        ${FIELDS.map((f) => {
          const limit = data.limits[f.key];
          return html`
            <label key=${f.key} class="field">
              <span class="field__label">${f.label}</span>
              <input class="input" type="number" required min=${limit.min} max=${limit.max} value=${values[f.key]}
                onInput=${(e) => setForm({ ...values, [f.key]: e.currentTarget.value })} />
              <span class="field__hint">${f.hint} ${limit.min} to ${limit.max}.</span>
            </label>
          `;
        })}
      </div>
      <div class="row"><button type="submit" class="btn btn--primary" disabled=${saving || form === null}>Save</button></div>
    </form>
  `;
}
