/** Teams for the People view (pure): everyone, a department or a section; found from the URL. */
import { peoplePath } from "./routes.js";

/** The whole board: no department and no section. */
export const EVERYONE = Object.freeze({ department: null, section: null });

/** Exact match first; otherwise ignore case (SQLite allows "QA" next to "qa", MS SQL does not). */
function findByText(items, text, field) {
  return items.find((item) => item[field] === text) ?? items.find((item) => item[field].toLowerCase() === text.toLowerCase());
}

/**
 * The team a People URL names, or null when there is no such department or section.
 * @param {object[]} departments  bootstrap departments, each with its sections
 * @param {{department: ?string, section: ?string}} params  department code and section name
 * @returns {?{department: ?object, section: ?object}}
 */
export function findTeam(departments, { department = null, section = null } = {}) {
  if (department == null) return EVERYONE;
  const found = findByText(departments, department, "code");
  if (!found) return null;
  if (section == null) return { department: found, section: null };
  const foundSection = findByText(found.sections, section, "name");
  return foundSection ? { department: found, section: foundSection } : null;
}

/** The team's own URL (app-relative), spelled as the organization spells it: "people/STL/Quality". */
export function teamPath(team) {
  return peoplePath(team.department?.code ?? null, team.section?.name ?? null);
}

/** "Everyone", "STL" or "STL · Quality" (the same wording as elsewhere in the app). */
export function teamLabel(team) {
  if (!team.department) return "Everyone";
  return team.section ? `${team.department.code} · ${team.section.name}` : team.department.code;
}

/** The people who belong to a team, in their original order. */
export function teamMembers(people, team) {
  if (team.section) return people.filter((p) => p.section_id === team.section.id);
  if (team.department) return people.filter((p) => p.department_id === team.department.id);
  return people;
}
