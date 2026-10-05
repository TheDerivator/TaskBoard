/** "Where in the knowledge map": the boxes a process change or a task refers to, as chips that
 * open the box; editors link more (applied at once, like placements) or unlink. */
import { api } from "../api.js";
import { useApi } from "../hooks.js";
import { knowledgePath } from "../lib/routes.js";
import { href } from "../router.js";
import { html, useEffect, useState } from "../ui.js";
import { BoxPicker, boxRefLabel } from "./box-picker.js";
import { CloseIcon } from "./icons.js";
import { FieldLabel } from "./task-fields.js";
import { showError } from "./toasts.js";

/**
 * @param {{basePath: string, editable: boolean, lookup: object, label?: string, hint?: string}} props
 *   `basePath` is e.g. "/changes/LM-07/boxes" or "/tasks/K7Q2MX/boxes"
 */
export function BoxLinksField({ basePath, editable, lookup, label = "Where in the knowledge map", hint = null }) {
  const { data, error } = useApi(basePath);
  const [boxes, setBoxes] = useState(null);
  const [picking, setPicking] = useState(false);
  useEffect(() => setBoxes(data), [data]);

  const run = async (request) => {
    try {
      setBoxes(await request());
    } catch (err) {
      showError(err);
    }
  };
  const pathOf = (ref) => {
    const process = ref.process_id != null ? lookup.processes.get(ref.process_id) : null;
    const department = process && lookup.departments.get(process.department_id);
    return process && department ? knowledgePath(department.code, process.code, ref.key) : null;
  };
  if (error) return null;
  return html`
    <div class="field">
      <${FieldLabel}>${label}<//>
      <div class="box-links">
        ${(boxes ?? []).map((ref) => {
          const path = pathOf(ref);
          const text = ref.path.length ? html`${ref.path.join(" › ")} › <strong>${ref.name}</strong>` : html`<strong>${ref.name}</strong>`;
          return html`
            <span key=${ref.key} class=${`box-link${ref.process_id == null ? " box-link--defect" : ""}`}>
              ${path ? html`<a href=${href(path)}>${text}</a>` : html`<span>${text}</span>`}
              ${editable &&
              html`<button type="button" aria-label=${`Unlink ${boxRefLabel(ref)}`} onClick=${() => run(() => api.delete(`${basePath}/${encodeURIComponent(ref.key)}`))}>
                <${CloseIcon} size=${12} />
              </button>`}
            </span>
          `;
        })}
        ${boxes && boxes.length === 0 && !editable && html`<span class="muted">Not linked to the map.</span>`}
        ${editable && html`<button type="button" class="btn btn--dashed" onClick=${() => setPicking(true)}>+ Link to a box</button>`}
      </div>
      ${hint && html`<span class="field-hint">${hint}</span>`}
      <${BoxPicker}
        open=${picking}
        title="Link to a box"
        exclude=${(boxes ?? []).map((b) => b.key)}
        onClose=${() => setPicking(false)}
        onPick=${(ref) => {
          setPicking(false);
          run(() => api.put(`${basePath}/${encodeURIComponent(ref.key)}`));
        }}
      />
    </div>
  `;
}
