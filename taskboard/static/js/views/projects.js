/** Projects view: project tree on the left, the selected project or section unfolded as an outline. */
import { api } from "../api.js";
import { Avatar, StatusPill } from "../components/badges.js";
import { Dialog } from "../components/dialog.js";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  ChevronIcon,
  IndentIcon,
  OutdentIcon,
  PlusIcon,
  TrashIcon,
} from "../components/icons.js";
import { showError, showToast } from "../components/toasts.js";
import { useApi, useTitle } from "../hooks.js";
import { padRank, plural } from "../lib/format.js";
import { canSomewhere } from "../lib/lookup.js";
import { projectPath, taskPath } from "../lib/routes.js";
import { href, navigate } from "../router.js";
import { dataChanged, refreshBoot } from "../store.js";
import { html, useEffect, useState } from "../ui.js";
import { NewTaskDrawer } from "./task.js";

export const PROJECT_COLORS = ["#C4561C", "#2D5BA8", "#1F7A6E", "#7A4A9C", "#A8431A", "#56652A", "#8A3A56", "#1E4686"];

// ---------------------------------------------------------------- tree (left)

function ProjectTree({ projects, selectedKey, selectedNode, canManage, onNewProject }) {
  return html`
    <aside class="project-tree" aria-label="Projects and sections">
      <div class="project-tree__head">
        <h2>Projects</h2>
        ${canManage && html`<button type="button" class="btn" aria-label="New project" title="New project" onClick=${onNewProject}><${PlusIcon} /></button>`}
      </div>
      <ul class="tree" role="tree" aria-label="Projects and sections">
        ${projects.map((p) => {
          const open = p.key === selectedKey;
          return html`
            <li key=${p.id} role="treeitem" aria-expanded=${open ? "true" : "false"}>
              <a
                class=${`tree-item tree-item--project${p.archived ? " tree-item--archived" : ""}`}
                href=${href(projectPath(p.key))}
                aria-current=${open && selectedNode == null ? "true" : undefined}
              >
                <span class=${`tree-item__chevron${open ? " tree-item__chevron--open" : ""}`}><${ChevronIcon} /></span>
                <span class="project-dot" style=${{ "--project-color": p.color }}></span>
                <span class="tree-item__label">${p.name}${p.archived ? " (archived)" : ""}</span>
                <span class="tree-item__count">${p.count}</span>
              </a>
              ${open &&
              p.nodes.length > 0 &&
              html`
                <ul class="tree" role="group">
                  ${p.nodes.map(
                    (n) => html`
                      <li key=${n.id} role="treeitem">
                        <a
                          class=${`tree-item${n.depth === 1 ? " tree-item--top" : ""}`}
                          style=${{ "--depth": n.depth }}
                          href=${href(projectPath(p.key, n.id))}
                          aria-current=${selectedNode === n.id ? "true" : undefined}
                        >
                          <span class="tree-item__num">${n.number}</span>
                          <span class="tree-item__label">${n.name}</span>
                          <span class="tree-item__count">${n.count}</span>
                        </a>
                      </li>
                    `,
                  )}
                </ul>
              `}
            </li>
          `;
        })}
      </ul>
    </aside>
  `;
}

// ---------------------------------------------------------------- outline (right)

function TaskLine({ task, indent, projectId, lookup }) {
  const others = task.placements.filter((p) => p.project_id !== projectId).map((p) => lookup.projects.get(p.project_id)?.name);
  const lead = lookup.people.get(task.lead_id);
  return html`
    <a class="outline-row outline-row--task" style=${{ "--indent": indent }} href=${href(taskPath(task.key))}>
      <span class=${`outline-row__rank${task.rank <= 3 ? " outline-row__rank--top" : ""}`}>#${padRank(task.rank)}</span>
      <span class="outline-row__title">${task.title}</span>
      ${others.length > 0 && html`<span class="outline-row__also" title="Also placed in another project">also in ${others.join(", ")}</span>`}
      <${Avatar} person=${lead} title=${lead ? `Lead: ${lead.name}` : "Lead"} />
      <${StatusPill} status=${task.status} />
    </a>
  `;
}

function Outline({ outline, lookup }) {
  const base = outline.node ? outline.node.depth : 1;
  const rows = [];
  for (const task of outline.top_level_tasks) {
    rows.push(html`<${TaskLine} key=${`t${task.key}`} task=${task} indent=${-1} projectId=${outline.project.id} lookup=${lookup} />`);
  }
  for (const { node, tasks } of outline.sections) {
    const indent = node.depth - base;
    rows.push(html`
      <div key=${`n${node.id}`} class=${`outline-row outline-row--section-${Math.min(node.depth, 3)}`} style=${{ "--indent": indent }}>
        <span class="outline-row__num">${node.number}</span>
        <span class="outline-row__name">${node.name}</span>
        <span class="outline-row__count">${plural(node.count, "task")}</span>
      </div>
    `);
    for (const task of tasks) {
      rows.push(html`<${TaskLine} key=${`t${task.key}`} task=${task} indent=${indent} projectId=${outline.project.id} lookup=${lookup} />`);
    }
  }
  if (rows.length === 0) {
    return html`<div class="empty-state">No sections or tasks here yet.</div>`;
  }
  return html`<div class="outline">${rows}</div>`;
}

// ---------------------------------------------------------------- section editor

function ColorPicker({ value, onChange, label = "Colour" }) {
  return html`
    <div class="field">
      <span class="field__label">${label}</span>
      <div class="swatches" role="group" aria-label=${label}>
        ${PROJECT_COLORS.map(
          (color) => html`<button
            key=${color}
            type="button"
            class="swatch"
            style=${{ "--swatch": color }}
            aria-label=${color}
            aria-pressed=${value.toUpperCase() === color ? "true" : "false"}
            onClick=${() => onChange(color)}
          ></button>`,
        )}
      </div>
    </div>
  `;
}

/** A section name being edited; typing survives re-renders until the server's name changes. */
function SectionNameInput({ node, onRename }) {
  const [value, setValue] = useState(node.name);
  useEffect(() => setValue(node.name), [node.name]);
  return html`
    <input
      class="input"
      aria-label=${`Name of section ${node.number}`}
      value=${value}
      maxlength="200"
      onInput=${(e) => setValue(e.currentTarget.value)}
      onBlur=${() => onRename(node, value)}
      onKeyDown=${(e) => e.key === "Enter" && e.currentTarget.blur()}
    />
  `;
}

function SectionEditor({ project, onDone }) {
  const [name, setName] = useState(project.name);
  const [color, setColor] = useState(project.color);
  useEffect(() => {
    setName(project.name);
    setColor(project.color);
  }, [project.id]);

  const call = async (request, message) => {
    try {
      await request();
      await refreshBoot();
      dataChanged();
      if (message) showToast(message);
    } catch (err) {
      showError(err);
    }
  };
  const base = `/projects/${encodeURIComponent(project.key)}`;
  const siblings = (node) => project.nodes.filter((n) => n.parent_id === node.parent_id);
  const indexOf = (node) => siblings(node).findIndex((n) => n.id === node.id);

  const rename = (node, value) => {
    const trimmed = value.trim();
    if (trimmed && trimmed !== node.name) call(() => api.patch(`${base}/nodes/${node.id}`, { name: trimmed }));
  };
  const moveBy = (node, delta) => call(() => api.patch(`${base}/nodes/${node.id}`, { index: indexOf(node) + delta }));
  const indent = (node) => {
    const previous = siblings(node)[indexOf(node) - 1];
    if (previous) call(() => api.patch(`${base}/nodes/${node.id}`, { parent_id: previous.id }));
  };
  const outdent = (node) => {
    const parent = project.nodes.find((n) => n.id === node.parent_id);
    if (!parent) return;
    const parentIndex = indexOf(parent);
    call(() => api.patch(`${base}/nodes/${node.id}`, { parent_id: parent.parent_id, index: parentIndex + 1 }));
  };
  const addChild = (parentId) => call(() => api.post(`${base}/nodes`, { name: "New section", parent_id: parentId }));
  const remove = (node) => {
    const where = node.parent_id == null ? "the top level of the project" : "the section above it";
    if (!window.confirm(`Delete ${node.number} ${node.name} and everything below it? Its tasks move to ${where}.`)) return;
    call(() => api.delete(`${base}/nodes/${node.id}`), `Deleted ${node.number} ${node.name}.`);
  };
  const saveSettings = () => call(() => api.patch(base, { name, color }), "Project saved.");
  const toggleArchived = () =>
    call(() => api.patch(base, { archived: !project.archived }), project.archived ? "Project restored." : "Project archived.");
  const deleteProject = () => {
    if (!window.confirm(`Delete the project "${project.name}"? Its sections go; its tasks stay on the board.`)) return;
    call(async () => {
      await api.delete(base);
      navigate("projects");
    }, "Project deleted.");
  };

  return html`
    <div class="section-editor">
      <div class="project-settings">
        <label class="field">
          <span class="field__label">Project name</span>
          <input class="input" value=${name} maxlength="200" onInput=${(e) => setName(e.currentTarget.value)} />
        </label>
        <button type="button" class="btn" disabled=${!name.trim() || (name === project.name && color === project.color)} onClick=${saveSettings}>
          Save name and colour
        </button>
        <${ColorPicker} value=${color} onChange=${setColor} />
        <div class="row">
          <button type="button" class="btn" onClick=${toggleArchived}>${project.archived ? "Restore project" : "Archive project"}</button>
          <button type="button" class="btn btn--danger" onClick=${deleteProject}>Delete project</button>
        </div>
      </div>
      ${project.nodes.map((node) => {
        const index = indexOf(node);
        const count = siblings(node).length;
        return html`
          <div key=${node.id} class="section-edit" style=${{ "--indent": node.depth - 1 }}>
            <span class="mono">${node.number}</span>
            <${SectionNameInput} node=${node} onRename=${rename} />
            <button type="button" class="icon-btn" title="Move up" aria-label=${`Move ${node.number} up`} disabled=${index === 0} onClick=${() => moveBy(node, -1)}><${ArrowUpIcon} /></button>
            <button type="button" class="icon-btn" title="Move down" aria-label=${`Move ${node.number} down`} disabled=${index === count - 1} onClick=${() => moveBy(node, 1)}><${ArrowDownIcon} /></button>
            <button type="button" class="icon-btn" title="Make it a subsection of the one above" aria-label=${`Indent ${node.number}`} disabled=${index === 0} onClick=${() => indent(node)}><${IndentIcon} /></button>
            <button type="button" class="icon-btn" title="Move it one level up" aria-label=${`Outdent ${node.number}`} disabled=${node.parent_id == null} onClick=${() => outdent(node)}><${OutdentIcon} /></button>
            <button type="button" class="icon-btn" title="Add a subsection" aria-label=${`Add a subsection to ${node.number}`} onClick=${() => addChild(node.id)}><${PlusIcon} /></button>
            <button type="button" class="icon-btn" title="Delete" aria-label=${`Delete ${node.number}`} onClick=${() => remove(node)}><${TrashIcon} /></button>
          </div>
        `;
      })}
      <div class="section-editor__foot">
        <button type="button" class="dashed-button dashed-button--square" onClick=${() => addChild(null)}>+ Add section</button>
        <span class="spacer" style=${{ flex: 1 }}></span>
        <button type="button" class="btn btn--primary" onClick=${onDone}>Done</button>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------- new project

function NewProjectDialog({ open, onClose }) {
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [color, setColor] = useState(PROJECT_COLORS[0]);
  const [error, setError] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    try {
      const project = await api.post("/projects", { key, name, color });
      await refreshBoot();
      dataChanged();
      showToast(`Project "${project.name}" created.`);
      onClose();
      navigate(projectPath(project.key));
    } catch (err) {
      setError(err.message);
    }
  };

  return html`
    <${Dialog} open=${open} title="New project" onClose=${onClose}>
      <form class="stack" onSubmit=${submit}>
        ${error && html`<div class="form-error" role="alert">${error}</div>`}
        <label class="field">
          <span class="field__label">Name</span>
          <input class="input" required maxlength="200" value=${name} onInput=${(e) => setName(e.currentTarget.value)} />
        </label>
        <label class="field">
          <span class="field__label">Short key (2–10 letters or digits)</span>
          <input
            class="input mono"
            required
            pattern="[A-Za-z0-9]{2,10}"
            value=${key}
            onInput=${(e) => setKey(e.currentTarget.value.toUpperCase())}
          />
        </label>
        <${ColorPicker} value=${color} onChange=${setColor} />
        <div class="dialog__actions">
          <button type="button" class="btn" onClick=${onClose}>Cancel</button>
          <button type="submit" class="btn btn--primary">Create project</button>
        </div>
      </form>
    <//>
  `;
}

// ---------------------------------------------------------------- the view

let showArchivedRemembered = false;

export function ProjectsView({ boot, lookup, route }) {
  const { key, node } = route.params;
  const [showArchived, setShowArchivedState] = useState(showArchivedRemembered);
  const setShowArchived = (value) => {
    showArchivedRemembered = value;
    setShowArchivedState(value);
  };
  const [editing, setEditing] = useState(false);
  const [creatingTask, setCreatingTask] = useState(false);
  const [creatingProject, setCreatingProject] = useState(false);
  const canManage = boot.me.permissions["project.manage"]?.everywhere ?? false;
  const canCreateTask = canSomewhere(boot.me, "task.edit");

  const firstKey = boot.projects.find((p) => !p.archived)?.key ?? boot.projects[0]?.key;
  useEffect(() => {
    if (!key && firstKey) navigate(projectPath(firstKey), { replace: true });
  }, [key, firstKey]);
  useEffect(() => setEditing(false), [key]);

  const tree = useApi("/projects", { include_archived: showArchived });
  const outline = useApi(key ? `/projects/${encodeURIComponent(key)}/outline` : null, {
    node: node ?? undefined,
    include_archived: showArchived,
  });
  const data = outline.data;
  useTitle(data ? data.project.name : "Projects");

  const projects = tree.data ?? boot.projects;
  const editedProject = data ? boot.projects.find((p) => p.id === data.project.id) : null;

  let main;
  if (!key && boot.projects.length === 0) {
    main = html`<div class="panel empty-state">No projects yet.${canManage ? " Create the first one with the + button." : ""}</div>`;
  } else if (outline.error) {
    main = html`<div class="panel empty-state" role="alert">${outline.error.status === 404 ? "This project or section doesn't exist." : outline.error.message}</div>`;
  } else if (!data) {
    main = html`<div class="panel empty-state">Loading…</div>`;
  } else {
    const title = data.node ? `${data.node.number} ${data.node.name}` : data.project.name;
    main = html`
      <div class="view-head">
        <div class="view-head__text">
          <nav class="breadcrumb" aria-label="Breadcrumb">
            ${data.breadcrumb.map(
              (c, i) => html`${i > 0 && html`<span aria-hidden="true">›</span>`}
                <a href=${href(projectPath(data.project.key, c.node_id))}>${c.label}</a>`,
            )}
          </nav>
          <div class="project-title">
            <span class="project-dot" style=${{ "--project-color": data.project.color }}></span>
            <h1>${title}</h1>
          </div>
          <div class="project-summary">
            <span>${plural(data.open_count, "open task")} in this ${data.node ? "section" : "project"}${data.lead_ids.length ? " · leads" : ""}</span>
            <span class="avatar-stack">
              ${data.lead_ids.map((id) => html`<${Avatar} key=${id} person=${lookup.people.get(id)} ring />`)}
            </span>
          </div>
        </div>
        <div class="project-actions">
          <button type="button" class="toggle-chip" aria-pressed=${showArchived ? "true" : "false"} onClick=${() => setShowArchived(!showArchived)}>
            Show archived
          </button>
          ${canManage && html`<button type="button" class="btn" aria-pressed=${editing ? "true" : "false"} onClick=${() => setEditing(!editing)}>Edit sections</button>`}
          ${canCreateTask && html`<button type="button" class="btn btn--primary" onClick=${() => setCreatingTask(true)}><${PlusIcon} />Add task here</button>`}
        </div>
      </div>
      <div class="panel">
        ${editing && editedProject
          ? html`<${SectionEditor} project=${editedProject} onDone=${() => setEditing(false)} />`
          : html`<${Outline} outline=${data} lookup=${lookup} />`}
      </div>
      ${creatingTask &&
      html`<${NewTaskDrawer} onClose=${() => setCreatingTask(false)} initialPlacements=${[{ project_id: data.project.id, node_id: node ?? null }]} />`}
    `;
  }

  return html`
    <div class="projects-layout">
      <${ProjectTree}
        projects=${projects}
        selectedKey=${key}
        selectedNode=${node}
        canManage=${canManage}
        onNewProject=${() => setCreatingProject(true)}
      />
      <section class="project-main" aria-label="Project outline">${main}</section>
      <${NewProjectDialog} open=${creatingProject} onClose=${() => setCreatingProject(false)} />
    </div>
  `;
}
