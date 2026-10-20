/** Recent activity: tasks by their newest comment or status update, everywhere or in one project
 * (or one of its sections), grouped by day, with "Show older". Tasks only for now (D-104). */
import { api } from "../api.js";
import { Avatar, ProjectChip, StatusPill, ViaBadge } from "../components/badges.js";
import { showError } from "../components/toasts.js";
import { useApi, useTitle } from "../hooks.js";
import { dayGroups, postTime } from "../lib/activity.js";
import { formatDate, plural } from "../lib/format.js";
import { activityPath, taskPath } from "../lib/routes.js";
import { href, navigate } from "../router.js";
import { html, useEffect, useState } from "../ui.js";

const PAGE = 30;
const INDENT = "  "; // per level of a section in the picker

/** A project (or one of its sections) has its own address, like a team in People. */
function Where({ projects, project, node, unknown }) {
  const pickProject = (key) => navigate(activityPath(key || null));
  const pickNode = (id) => navigate(activityPath(project.key, id ? Number(id) : null));
  return html`
    <div class="filters">
      <label class="field field--compact">
        <span class="field__label">Project</span>
        <select class="select select--compact" onChange=${(e) => pickProject(e.currentTarget.value)}>
          ${unknown && !project && html`<option value="" selected disabled>Unknown project</option>`}
          <option value="" selected=${!project && !unknown}>All projects</option>
          ${projects.map(
            (p) => html`<option key=${p.id} value=${p.key} selected=${project?.id === p.id}>${p.name}${p.archived ? " (archived)" : ""}</option>`,
          )}
        </select>
      </label>
      ${project?.nodes.length > 0 &&
      html`
        <label class="field field--compact">
          <span class="field__label">Section</span>
          <select class="select select--compact" onChange=${(e) => pickNode(e.currentTarget.value)}>
            ${unknown && html`<option value="" selected disabled>Unknown section</option>`}
            <option value="" selected=${node == null && !unknown}>Whole project</option>
            ${project.nodes.map(
              (n) => html`<option key=${n.id} value=${n.id} selected=${node?.id === n.id}>${INDENT.repeat(n.depth - 1)}${n.number} ${n.name}</option>`,
            )}
          </select>
        </label>
      `}
    </div>
  `;
}

function ActivityItem({ item, lookup, now }) {
  const { task, last_post: post } = item;
  const person = post.author.person_id != null ? lookup.people.get(post.author.person_id) : null;
  return html`
    <li class="activity-item" data-key=${task.key}>
      <div class="activity-item__head">
        <a class="task-title" href=${href(taskPath(task.key, "conversation"))}>${task.title}</a>
        <span class="task-key">${task.ref}</span>
        <${StatusPill} status=${task.status} small />
        ${task.placements.map(
          (p) => html`<${ProjectChip} key=${p.project_id} project=${lookup.projects.get(p.project_id)} placement=${p} />`,
        )}
      </div>
      <div class="activity-item__post">
        <${Avatar} person=${person} name=${post.author.display_name} size="small" />
        <div class="activity-item__body">
          <div class="activity-item__meta">
            <span class="activity-item__author">${post.author.display_name}</span>
            <${ViaBadge} actor=${post.author} />
            ${post.kind === "update" && html`<span class="update-badge">Status update</span>`}
            <time datetime=${post.created_at} title=${formatDate(post.created_at, { withTime: true, withYear: true })}>
              ${postTime(post.created_at, now)}
            </time>
            <span class="activity-item__count"><span aria-hidden="true">· </span>${plural(item.post_count, "post")}</span>
          </div>
          ${post.excerpt && html`<p class="activity-item__excerpt">${post.excerpt}</p>`}
        </div>
      </div>
    </li>
  `;
}

export function ActivityView({ boot, lookup, route }) {
  useTitle("Recent activity");
  const { project: projectKey, node: nodeId } = route.params;
  const project = projectKey ? boot.projects.find((p) => p.key.toLowerCase() === projectKey.toLowerCase()) ?? null : null;
  const node = project && nodeId != null ? project.nodes.find((n) => n.id === nodeId) ?? null : null;
  const unknown = (projectKey != null && !project) || (project != null && nodeId != null && !node);

  const params = { types: "task", project_id: project?.id, node_id: node?.id, limit: PAGE };
  const first = useApi(unknown ? null : "/activity", params);
  const [items, setItems] = useState([]);
  const [next, setNext] = useState(null);
  useEffect(() => {
    if (first.data) {
      setItems(first.data.items);
      setNext(first.data.next);
    }
  }, [first.data]);

  const older = async () => {
    try {
      const more = await api.get("/activity", { ...params, before: next });
      setItems([...items, ...more.items]);
      setNext(more.next);
    } catch (error) {
      showError(error);
    }
  };

  const now = new Date();
  let list;
  if (unknown) {
    list = html`<div class="empty-state" role="alert">This ${project ? "section" : "project"} doesn't exist.</div>`;
  } else if (first.error) {
    list = html`<div class="empty-state" role="alert">${first.error.message}</div>`;
  } else if (!first.data) {
    list = html`<div class="empty-state">Loading…</div>`;
  } else if (items.length === 0) {
    list = html`<div class="empty-state">No comments or status updates ${project ? "on the tasks here " : ""}yet.</div>`;
  } else {
    list = dayGroups(items, now).map(
      (group, index) => html`
        <h2 class="activity-day" id=${`activity-day-${index}`}>${group.label}</h2>
        <ol class="activity-list" aria-labelledby=${`activity-day-${index}`}>
          ${group.items.map((item) => html`<${ActivityItem} key=${item.task.key} item=${item} lookup=${lookup} now=${now} />`)}
        </ol>
      `,
    );
  }

  return html`
    <section class="page" aria-labelledby="activity-title">
      <header class="view-head">
        <div class="view-head__text">
          <h1 id="activity-title">Recent activity</h1>
          <p>Tasks with the newest comments and status updates first.</p>
        </div>
      </header>
      <${Where} projects=${boot.projects} project=${project} node=${node} unknown=${unknown} />
      <div class="panel activity">${list}</div>
      ${!unknown &&
      first.data &&
      items.length > 0 &&
      html`<div class="row count-note">
        <p aria-live="polite">Showing ${plural(items.length, "task")} · newest post first</p>
        ${next && html`<button type="button" class="btn" onClick=${older}>Show older</button>`}
      </div>`}
    </section>
  `;
}
