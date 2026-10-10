/** Administration › Audit log: security-relevant actions, newest first, with "Show older". */
import { api } from "../../api.js";
import { showError } from "../../components/toasts.js";
import { useApi } from "../../hooks.js";
import { formatDate } from "../../lib/format.js";
import { html, useEffect, useState } from "../../ui.js";

const PAGE = 50;

function details(entry) {
  const parts = Object.entries(entry.details ?? {}).map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`);
  return parts.join(" · ");
}

export function AuditTab() {
  const first = useApi("/admin/audit", { limit: PAGE });
  const [entries, setEntries] = useState([]);
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (first.data) {
      setEntries(first.data);
      setDone(first.data.length < PAGE);
    }
  }, [first.data]);

  const older = async () => {
    try {
      const more = await api.get("/admin/audit", { limit: PAGE, before_id: entries.at(-1)?.id });
      setEntries([...entries, ...more]);
      setDone(more.length < PAGE);
    } catch (err) {
      showError(err);
    }
  };

  if (first.error) return html`<div class="panel empty-state" role="alert">${first.error.message}</div>`;
  if (!first.data) return html`<div class="panel empty-state">Loading…</div>`;
  return html`
    <div class="section-head">
      <div><h2>Audit log</h2><p>Logins, account and access changes, organization changes and backup settings. Newest first.</p></div>
    </div>
    <div class="panel table-wrap">
      <table class="data-table">
        <thead><tr><th>When</th><th>Who</th><th>What</th><th>Target</th><th>Details</th></tr></thead>
        <tbody>
          ${entries.map(
            (e) => html`
              <tr key=${e.id}>
                <td class="mono">${formatDate(e.at, { withTime: true })}</td>
                <td>${e.actor ?? html`<em class="muted">system</em>`}</td>
                <td class="mono">${e.action}</td>
                <td class="mono">${e.target_type ? `${e.target_type} ${e.target_id ?? ""}` : "—"}</td>
                <td>${details(e)}</td>
              </tr>
            `,
          )}
        </tbody>
      </table>
    </div>
    ${!done && html`<div class="row"><button type="button" class="btn" onClick=${older}>Show older</button></div>`}
  `;
}
