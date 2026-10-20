/** Which views a visitor may open, and where "home" leads (pure; the server enforces the rules). */
import { canSomewhere } from "./lookup.js";

// The permission each view needs somewhere. Administration checks its own tabs.
const NEEDS = {
  tasks: "task.view",
  people: "task.view",
  projects: "task.view",
  activity: "task.view", // tasks only for now; the API also lists process changes (D-104)
  task: "task.view",
  changes: "change.view",
  change: "change.view",
  knowledge: "knowledge.view",
  fmea: "knowledge.view",
  cpl: "knowledge.view",
  box: "knowledge.view",
};

/** True when the visitor may see what the route shows (somewhere: details are per section). */
export function routeAllowed(me, routeName) {
  if (routeName === "profile") return !me.is_anonymous; // your account and API tokens
  const permission = NEEDS[routeName];
  if (permission) return canSomewhere(me, permission);
  return ["task.view", "change.view", "knowledge.view"].some((p) => canSomewhere(me, p));
}

/** The first view the visitor may use: tasks, then process changes, then process knowledge. */
export function homeRoute(me) {
  if (canSomewhere(me, "task.view")) return "tasks";
  if (canSomewhere(me, "change.view")) return "changes";
  if (canSomewhere(me, "knowledge.view")) return "knowledge";
  return "tasks"; // shows "log in" or "no access"
}
