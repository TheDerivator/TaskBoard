/** "Add to another project" / "Move" dialog: step 1 pick a project, step 2 pick a node or top level. */
import { html, useState } from "../ui.js";
import { Dialog } from "./dialog.js";

/**
 * @param {{
 *   open: boolean,
 *   taskRef: string,               // "T-104" (or "the new task")
 *   projects: object[],            // bootstrap projects, each with `nodes` in outline order
 *   placements: object[],          // the task's current placements
 *   moveProjectId?: number|null,   // set: move within this project (step 1 is skipped)
 *   onSubmit: (projectId: number, nodeId: number|null) => Promise<void>|void,
 *   onClose: () => void,
 * }} props
 */
export function PlacementDialog({ open, taskRef, projects, placements, moveProjectId = null, onSubmit, onClose }) {
  return html`
    <${Dialog}
      open=${open}
      wide
      title=${moveProjectId == null ? "Add to another project" : "Move within project"}
      onClose=${onClose}
    >
      <${PlacementForm} ...${{ taskRef, projects, placements, moveProjectId, onSubmit, onClose }} />
    <//>
  `;
}

function PlacementForm({ taskRef, projects, placements, moveProjectId, onSubmit, onClose }) {
  const placedIn = new Map(placements.map((p) => [p.project_id, p]));
  const available = projects.filter((p) => !p.archived && !placedIn.has(p.id));
  const [projectId, setProjectId] = useState(moveProjectId ?? available[0]?.id ?? null);
  const current = moveProjectId != null ? placedIn.get(moveProjectId) : null;
  const [nodeId, setNodeId] = useState(current ? current.node_id : null);
  const [busy, setBusy] = useState(false);
  const project = projects.find((p) => p.id === projectId);

  const pickProject = (id) => {
    setProjectId(id);
    setNodeId(null);
  };

  const submit = async (event) => {
    event.preventDefault();
    if (projectId == null) return;
    setBusy(true);
    try {
      await onSubmit(projectId, nodeId);
    } finally {
      setBusy(false);
    }
  };

  const node = project?.nodes.find((n) => n.id === nodeId);
  const summary = project ? html`${project.name} › ${node ? html`<span class="mono">${node.number}</span> ${node.name}` : "top level"}` : "";

  return html`
    <form class="stack" onSubmit=${submit}>
      <p class="muted"><span class="mono">${taskRef}</span> can sit in one section of each project.</p>

      ${moveProjectId == null &&
      html`
        <fieldset class="choice-list">
          <legend class="label-caps">1 · Project</legend>
          ${projects
            .filter((p) => !p.archived)
            .map((p) => {
              const already = placedIn.get(p.id);
              return html`
                <label key=${p.id} class=${`choice${already ? " choice--disabled" : ""}`}>
                  <input
                    type="radio"
                    name="project"
                    disabled=${Boolean(already)}
                    checked=${projectId === p.id}
                    onChange=${() => pickProject(p.id)}
                  />
                  <span class="project-dot" style=${{ "--project-color": p.color }}></span>
                  <span class="choice__text">
                    <span>${p.name}</span>
                    ${already &&
                    html`<span class="choice__hint">
                      Already in ${already.number ? `${already.number} ${already.path.at(-1)}` : "the top level"}. Use Move to change it.
                    </span>`}
                  </span>
                </label>
              `;
            })}
          ${available.length === 0 && html`<p class="muted">This task is already in every project.</p>`}
        </fieldset>
      `}

      ${project &&
      html`
        <fieldset class="choice-list node-choices">
          <legend class="label-caps">${moveProjectId == null ? "2 · " : ""}Section in ${project.name}</legend>
          <label class="choice node-choice">
            <input type="radio" name="node" checked=${nodeId === null} onChange=${() => setNodeId(null)} />
            <span class="muted"><em>Top level (no section)</em></span>
          </label>
          ${project.nodes.map(
            (n) => html`
              <label key=${n.id} class=${`choice node-choice${n.depth === 1 ? " node-choice--top" : ""}`} style=${{ "--depth": n.depth - 1 }}>
                <input type="radio" name="node" checked=${nodeId === n.id} onChange=${() => setNodeId(n.id)} />
                <span class="mono muted">${n.number}</span>
                <span>${n.name}</span>
              </label>
            `,
          )}
        </fieldset>
      `}

      <div class="dialog__actions">
        <span class="dialog__summary">${summary}</span>
        <button type="button" class="btn" onClick=${onClose}>Cancel</button>
        <button type="submit" class="btn btn--primary" disabled=${busy || projectId == null}>
          ${moveProjectId == null ? "Add" : "Move"}
        </button>
      </div>
    </form>
  `;
}
