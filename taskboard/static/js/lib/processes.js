/** Processes for Process changes and Process knowledge (pure): who may use which, found from the URL. */
import { canIn } from "./lookup.js";

/** Exact match first, then ignoring case (links are forgiving: /changes/stl/lm). */
function findByCode(items, code) {
  if (code == null) return null;
  return items.find((item) => item.code === code) ?? items.find((item) => item.code.toLowerCase() === String(code).toLowerCase()) ?? null;
}

/**
 * The processes a module shows: those whose owning section grants `permission` (D-080).
 * @param {object[]} processes  bootstrap processes, in display order
 * @param {object} me  bootstrap `me`
 * @param {string} permission  "change.view" or "knowledge.view"
 */
export function moduleProcesses(processes, me, permission) {
  return processes.filter((p) => canIn(me, permission, p.section_id));
}

/** The departments that have at least one of `processes`, in the organization's order. */
export function processDepartments(departments, processes) {
  const used = new Set(processes.map((p) => p.department_id));
  return departments.filter((d) => used.has(d.id));
}

/**
 * What a URL names: `{department, process}` (either may be null when not named), or null when
 * it names a department or process that does not exist (or that the visitor may not see).
 * Process codes are unique, so the process decides: a wrong department segment is only spelling.
 */
export function findProcessRoute(departments, processes, { department = null, process = null } = {}) {
  if (process != null) {
    const found = findByCode(processes, process);
    if (!found) return null;
    return { department: departments.find((d) => d.id === found.department_id) ?? null, process: found };
  }
  if (department == null) return { department: null, process: null };
  const found = findByCode(departments, department);
  return found ? { department: found, process: null } : null;
}

/**
 * The process to open when a URL names none: the one used last (if still available, and in the
 * department asked for), otherwise the department's first, otherwise the very first.
 */
export function defaultProcess(processes, { remembered = null, departmentId = null } = {}) {
  const candidates = departmentId == null ? processes : processes.filter((p) => p.department_id === departmentId);
  return candidates.find((p) => p.code === remembered) ?? candidates[0] ?? null;
}
