/** Map URL paths to app routes and back. Pure: the deployment's base path is passed in. */

const TASK_TABS = new Set(["details", "conversation"]);
export const ADMIN_TABS = ["users", "roles", "organization", "people", "groups", "audit", "backups"];
export const TIMELINE_RANGES = [3, 6, 12]; // months back; planned periods are always included
const CHANGE_KEY = /^[A-Za-z0-9]+-\d+$/; // "LM-07"

function positiveInt(text) {
  return text && /^\d+$/.test(text) ? Number(text) : null;
}

/** Process changes: /changes[/{dept}[/{process}[/timeline | /{KEY}[/conversation]]]]. */
function parseChanges(rest, query) {
  const [department = null, process = null, third, fourth] = rest;
  if (rest.length > 4) return null;
  const base = { department, process };
  if (third === undefined) return { name: "changes", params: { ...base, view: "list" } };
  if (third === "timeline" && fourth === undefined) {
    const range = positiveInt(query.get("range"));
    return {
      name: "changes",
      params: {
        ...base,
        view: "timeline",
        range: TIMELINE_RANGES.includes(range) ? range : 6,
        box: query.get("box") || null,
      },
    };
  }
  if (CHANGE_KEY.test(third)) {
    const tab = fourth ?? "details";
    if (TASK_TABS.has(tab)) return { name: "change", params: { ...base, key: third.toUpperCase(), tab } };
  }
  return null;
}

/** Process knowledge: /knowledge, /fmea and /cpl, as in DESIGN.md "Stable links". */
function parseKnowledge(head, rest, query) {
  const release = query.get("release") || null;
  if (head === "knowledge" && rest.length <= 3) {
    const [department = null, process = null, box = null] = rest;
    return { name: "knowledge", params: { department, process, box } };
  }
  if (head === "fmea" && rest.length <= 2) {
    const [department = null, process = null] = rest;
    return { name: "fmea", params: { department, process, box: query.get("box") || null, release } };
  }
  if (head === "cpl" && rest.length <= 3) {
    const [department = null, defect = null, cause = null] = rest;
    return { name: "cpl", params: { department, defect, cause, process: query.get("process") || null, release } };
  }
  return null;
}

/**
 * @param {string} pathname  e.g. "/taskboard/t/K7Q2MX/conversation"
 * @param {string} search    e.g. "?node=12"
 * @param {string} base      the app's base path, always ending in "/", e.g. "/taskboard/"
 * @returns {{name: string, params: Record<string, any>}}
 */
export function parseRoute(pathname, search = "", base = "/") {
  const relative = pathname.startsWith(base) ? pathname.slice(base.length) : pathname.replace(/^\/+/, "");
  const parts = relative.split("/").filter(Boolean).map(decodeURIComponent);
  const query = new URLSearchParams(search);
  const [head, ...rest] = parts;

  if (parts.length === 0) return { name: "home", params: {} };
  if (head === "priority" && rest.length === 0) return { name: "priority", params: {} };
  if (head === "profile" && rest.length === 0) return { name: "profile", params: {} };
  if (head === "people" && rest.length <= 2) {
    return { name: "people", params: { department: rest[0] ?? null, section: rest[1] ?? null } };
  }
  if (head === "projects" && rest.length <= 1) {
    const node = query.get("node");
    return {
      name: "projects",
      params: { key: rest[0] ?? null, node: node && /^\d+$/.test(node) ? Number(node) : null },
    };
  }
  if (head === "admin" && rest.length <= 1) {
    const tab = rest[0] ?? "users";
    if (ADMIN_TABS.includes(tab)) return { name: "admin", params: { tab } };
  }
  if (head === "changes") return parseChanges(rest, query) ?? { name: "notFound", params: {} };
  if (head === "knowledge" || head === "fmea" || head === "cpl") {
    return parseKnowledge(head, rest, query) ?? { name: "notFound", params: {} };
  }
  if (head === "box" && rest.length === 1) return { name: "box", params: { key: rest[0] } };
  if (head === "t" && (rest.length === 1 || rest.length === 2)) {
    const tab = rest[1] ?? "details";
    if (TASK_TABS.has(tab)) return { name: "task", params: { key: rest[0], tab } };
  }
  return { name: "notFound", params: {} };
}

/** App-relative paths (no leading slash); `href()` in router.js adds the base path. */
export function taskPath(key, tab = "details") {
  const bare = String(key).replace(/^T-/i, "");
  return tab === "details" ? `t/${encodeURIComponent(bare)}` : `t/${encodeURIComponent(bare)}/${tab}`;
}

export function projectPath(key, nodeId = null) {
  if (!key) return "projects";
  return nodeId == null ? `projects/${encodeURIComponent(key)}` : `projects/${encodeURIComponent(key)}?node=${nodeId}`;
}

/** A team view: everyone, a department (by code) or one of its sections (by name). */
export function peoplePath(departmentCode = null, sectionName = null) {
  if (departmentCode == null) return "people";
  const department = `people/${encodeURIComponent(departmentCode)}`;
  return sectionName == null ? department : `${department}/${encodeURIComponent(sectionName)}`;
}

function segments(...parts) {
  const used = [];
  for (const part of parts) {
    if (part == null) break;
    used.push(encodeURIComponent(part));
  }
  return used;
}

function withQuery(path, query) {
  const search = new URLSearchParams(Object.entries(query).filter(([, value]) => value != null && value !== ""));
  const text = search.toString();
  return text ? `${path}?${text}` : path;
}

/** A process's changes: the list, or the timeline (range in months, optionally one map box). */
export function changesPath(departmentCode = null, processCode = null, { view = "list", range = 6, box = null } = {}) {
  const path = ["changes", ...segments(departmentCode, processCode)].join("/");
  if (view !== "timeline" || processCode == null) return path;
  return withQuery(`${path}/timeline`, { range: range === 6 ? null : range, box });
}

/** One process change (its drawer over the list, or its own page). */
export function changePath(departmentCode, processCode, key, tab = "details") {
  const path = `${changesPath(departmentCode, processCode)}/${encodeURIComponent(key)}`;
  return tab === "details" ? path : `${path}/${tab}`;
}

export function knowledgePath(departmentCode = null, processCode = null, box = null) {
  return ["knowledge", ...segments(departmentCode, processCode, box)].join("/");
}

export function fmeaPath(departmentCode = null, processCode = null, { box = null, release = null } = {}) {
  return withQuery(["fmea", ...segments(departmentCode, processCode)].join("/"), { box, release });
}

/** The control plan of a department's defect (optionally one cause), for one process or all. */
export function cplPath(departmentCode = null, defect = null, cause = null, { process = null, release = null } = {}) {
  return withQuery(["cpl", ...segments(departmentCode, defect, cause)].join("/"), { process, release });
}

/** A box by its key alone, for links from elsewhere (dashboards): it opens where the box lives. */
export function boxLinkPath(key) {
  return `box/${encodeURIComponent(key)}`;
}

/**
 * Where a box lives: its process's map, or (a defect) its department's control plan.
 * @param {{key: string, process_id: ?number, section_id: number}} box
 * @param {{processes: Map, departments: Map, sections: Map}} lookup
 */
export function boxHomePath(box, { processes, departments, sections }) {
  if (box.process_id == null) {
    const department = departments.get(sections.get(box.section_id)?.department_id);
    return cplPath(department?.code ?? null, box.key);
  }
  const process = processes.get(box.process_id);
  return knowledgePath(departments.get(process?.department_id)?.code ?? null, process?.code ?? null, box.key);
}

/** The app-relative path of a parsed route (the inverse of parseRoute for list views). */
export function routePath(route) {
  switch (route.name) {
    case "projects":
      return projectPath(route.params.key, route.params.node);
    case "task":
      return taskPath(route.params.key, route.params.tab);
    case "people":
      return peoplePath(route.params.department, route.params.section);
    case "admin":
      return `admin/${route.params.tab}`;
    case "changes": {
      const { department, process, ...options } = route.params;
      return changesPath(department, process, options);
    }
    case "change":
      return changePath(route.params.department, route.params.process, route.params.key, route.params.tab);
    case "knowledge":
      return knowledgePath(route.params.department, route.params.process, route.params.box);
    case "fmea":
      return fmeaPath(route.params.department, route.params.process, route.params);
    case "cpl":
      return cplPath(route.params.department, route.params.defect, route.params.cause, route.params);
    case "box":
      return boxLinkPath(route.params.key);
    default:
      return "priority";
  }
}
