/** Index the bootstrap document by id (people, sections, departments, projects, nodes, processes). Pure. */

/**
 * @param {object} boot  the GET /api/bootstrap response
 */
export function indexBoot(boot) {
  const people = new Map(boot.people.map((p) => [p.id, p]));
  const departments = new Map(boot.departments.map((d) => [d.id, d]));
  const sections = new Map(boot.departments.flatMap((d) => d.sections.map((s) => [s.id, s])));
  const projects = new Map(boot.projects.map((p) => [p.id, p]));
  const nodes = new Map(boot.projects.flatMap((p) => p.nodes.map((n) => [n.id, { ...n, project_id: p.id }])));
  const processes = new Map((boot.processes ?? []).map((p) => [p.id, p]));
  return {
    people,
    departments,
    sections,
    projects,
    nodes,
    processes,
    projectByKey: new Map(boot.projects.map((p) => [p.key, p])),
    personForUser: boot.me.person_id != null ? people.get(boot.me.person_id) ?? null : null,
  };
}

/** Where a permission applies, from `me.permissions` (display only; the server decides). */
export function canIn(me, permission, sectionId = null) {
  const reach = me.permissions[permission];
  if (!reach) return false;
  if (reach.everywhere) return true;
  return sectionId == null ? false : reach.section_ids.includes(sectionId);
}

export function canSomewhere(me, permission) {
  const reach = me.permissions[permission];
  return Boolean(reach && (reach.everywhere || reach.section_ids.length > 0));
}
