/** Choices for "where does this role apply": everywhere, a department, or a section. Pure. */

/**
 * @param {Array<{id: number, code: string, sections: Array<{id: number, name: string}>}>} departments
 * @returns {Array<{value: string, label: string, group: string}>}
 */
export function scopeOptions(departments) {
  const options = [{ value: "global", label: "Everywhere", group: "" }];
  for (const d of departments) {
    options.push({ value: `department:${d.id}`, label: `${d.code} (whole department)`, group: d.code });
    for (const s of d.sections) {
      options.push({ value: `section:${s.id}`, label: `${d.code} · ${s.name}`, group: d.code });
    }
  }
  return options;
}

/** "section:7" → {scope: "section", scope_id: 7}; "global" → {scope: "global", scope_id: null}. */
export function parseScope(value) {
  const [scope, id] = String(value).split(":");
  return { scope, scope_id: id === undefined ? null : Number(id) };
}
