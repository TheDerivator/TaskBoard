/** Map URL paths to app routes and back. Pure: the deployment's base path is passed in. */

const TASK_TABS = new Set(["details", "conversation"]);
export const ADMIN_TABS = ["users", "roles", "organization", "people", "groups", "audit"];

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
  if (head === "people" && rest.length === 0) return { name: "people", params: {} };
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

/** The app-relative path of a parsed route (the inverse of parseRoute for list views). */
export function routePath(route) {
  switch (route.name) {
    case "projects":
      return projectPath(route.params.key, route.params.node);
    case "task":
      return taskPath(route.params.key, route.params.tab);
    case "people":
      return "people";
    case "admin":
      return `admin/${route.params.tab}`;
    default:
      return "priority";
  }
}
