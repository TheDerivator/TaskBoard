/** Human wording for automatic task events ("Anna Claes moved this from Idea to Started"). Pure. */

const STATUS = { idea: "Idea", started: "Started", done: "Done", archived: "Archived" };

function personName(lookup, id) {
  return lookup.people.get(id)?.name ?? "someone";
}

function projectName(lookup, id) {
  return lookup.projects.get(id)?.name ?? "a deleted project";
}

function nodeLabel(lookup, id) {
  if (id == null) return "the top level";
  const node = lookup.nodes.get(id);
  return node ? `${node.number} ${node.name}` : "a deleted section";
}

function sectionLabel(lookup, id) {
  const section = lookup.sections.get(id);
  const department = section && lookup.departments.get(section.department_id);
  return section ? `${department ? `${department.code} · ` : ""}${section.name}` : "another section";
}

/**
 * @param {{kind: string, data: object, actor: ?{display_name: string}}} event
 * @param {object} lookup  from lib/lookup.js
 * @returns {{actor: string, text: string}}  shown as "<strong>actor</strong> text"
 */
export function describeEvent(event, lookup) {
  const actor = event.actor?.display_name ?? "Someone";
  const d = event.data ?? {};
  switch (event.kind) {
    case "created":
      return { actor, text: "created this task" };
    case "status_changed":
      return { actor, text: `moved this from ${STATUS[d.from] ?? d.from} to ${STATUS[d.to] ?? d.to}` };
    case "lead_changed":
      return { actor, text: `made ${personName(lookup, d.to)} the lead (was ${personName(lookup, d.from)})` };
    case "helper_added":
      return { actor, text: `added ${personName(lookup, d.person)}` };
    case "helper_removed":
      return { actor, text: `removed ${personName(lookup, d.person)}` };
    case "section_changed":
      return { actor, text: `moved this to ${sectionLabel(lookup, d.to)}` };
    case "placement_added":
      return { actor, text: `added this to ${projectName(lookup, d.project)} › ${nodeLabel(lookup, d.node)}` };
    case "placement_moved":
      return { actor, text: `moved this within ${projectName(lookup, d.project)} to ${nodeLabel(lookup, d.to)}` };
    case "placement_removed":
      return { actor, text: `removed this from ${projectName(lookup, d.project)}` };
    default:
      return { actor, text: "changed this task" };
  }
}
