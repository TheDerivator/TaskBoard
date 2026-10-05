/** /box/{key}: a box by its key alone (links from dashboards, or a map link naming the wrong
 * process) opens where the box lives: its process's map, or a defect's control plan. */
import { useApi, useTitle } from "../../hooks.js";
import { boxHomePath } from "../../lib/routes.js";
import { navigate } from "../../router.js";
import { html, useEffect } from "../../ui.js";

export function BoxLinkView({ route, lookup }) {
  const { data, error } = useApi(`/boxes/${encodeURIComponent(route.params.key)}`);
  useTitle("Process knowledge");
  useEffect(() => {
    if (data) navigate(boxHomePath(data.box, lookup), { replace: true });
  }, [data]);
  if (!error) return html`<section class="page" aria-busy="true"></section>`;
  return html`
    <section class="center-page">
      <div class="center-card">
        <h1>This box does not exist</h1>
        <p class="muted">The link names a box that was deleted, or that you may not see.</p>
      </div>
    </section>
  `;
}
