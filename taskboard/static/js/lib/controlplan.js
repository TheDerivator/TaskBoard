/** The control plan (pure): a department's defects in their groups, what leads to each defect in
 * map order, where each cause sits, and the DefectView mockup's diagram. Works on the API's
 * GET /api/control-plan. Positions are pixels on the diagram. */

const UNGROUPED = "Other";

/** Lookups for a plan: boxes by key, the leads-to links into each defect, controls per box. */
export function planIndex(plan) {
  const leadsTo = new Set(plan.link_types.filter((t) => t.role === "leads_to").map((t) => t.key));
  const causes = new Map();
  for (const link of plan.links) {
    if (!leadsTo.has(link.type)) continue;
    if (!causes.has(link.to_key)) causes.set(link.to_key, []);
    causes.get(link.to_key).push(link);
  }
  const controls = new Map();
  for (const control of [...plan.controls].sort((a, b) => a.position - b.position)) {
    if (!controls.has(control.box_key)) controls.set(control.box_key, []);
    controls.get(control.box_key).push(control);
  }
  return {
    byKey: new Map(plan.boxes.map((b) => [b.key, b])),
    kinds: new Map(plan.kinds.map((k) => [k.key, k])),
    defects: plan.boxes.filter((b) => b.process_id == null),
    causes,
    controls,
  };
}

/** From the process (its map's top box) down to the box's parent. */
export function pathOf(index, key) {
  const path = [];
  for (let at = index.byKey.get(key)?.parent_key; at != null; at = index.byKey.get(at)?.parent_key) path.unshift(at);
  return path;
}

/** Process order first, then the positions from the top of the map down: its reading order. */
function mapOrder(index, key, processOrder) {
  const box = index.byKey.get(key);
  const positions = [...pathOf(index, key), key].map((k) => index.byKey.get(k).position);
  return [processOrder.get(box.process_id) ?? Number.MAX_SAFE_INTEGER, ...positions];
}

function compareOrders(a, b) {
  for (let i = 0; i < Math.min(a.length, b.length); i += 1) {
    if (a[i] !== b[i]) return a[i] - b[i];
  }
  return a.length - b.length; // a box comes before the boxes under it
}

/**
 * What leads to a defect, in map order (D-091): each cause with its link (the "how" note), its
 * process, the boxes above it, and where it sits: the box under the process on its path
 * ("Mould") and, when the cause sits deeper, its parent ("Mould level control").
 * @param {{process?: ?number, processOrder?: Map<number, number>}} options  `process` keeps one
 *   process's causes; `processOrder` gives each process id its place (the organization's order)
 */
export function causesOf(index, defectKey, { process = null, processOrder = new Map() } = {}) {
  const seen = new Set();
  const causes = [];
  for (const link of index.causes.get(defectKey) ?? []) {
    const box = index.byKey.get(link.from_key);
    if (!box || box.process_id == null || seen.has(box.key)) continue;
    if (process != null && box.process_id !== process) continue;
    seen.add(box.key);
    const path = pathOf(index, box.key);
    const where = path[1] ?? path[0] ?? box.key;
    const parent = path.length ? path[path.length - 1] : null;
    causes.push({ key: box.key, box, link, process: box.process_id, path, where, sub: parent != null && parent !== where ? parent : null, order: mapOrder(index, box.key, processOrder) });
  }
  return causes.sort((a, b) => compareOrders(a.order, b.order) || a.key.localeCompare(b.key));
}

/** A defect's group: its "group" field (DESIGN: Surface, Cracks, ...), or "Other". */
export function groupOf(defect) {
  return String(defect.fields?.group ?? "").trim() || UNGROUPED;
}

/**
 * The defect list: groups (the defect kind's "group" field; none is "Other", last) in the order
 * they first appear in the catalogue, each defect with its number of known causes (with a process
 * chosen, its causes in that process). Every defect is listed, also one without causes yet (D-096);
 * `caused` keeps only those with causes; a query narrows by name.
 * @returns {{name: string, defects: {key: string, name: string, count: number}[]}[]}
 */
export function defectGroups(index, { process = null, query = "", caused = false } = {}) {
  const needle = query.trim().toLocaleLowerCase();
  const groups = [];
  for (const defect of index.defects) {
    const count = causesOf(index, defect.key, { process }).length;
    if (caused && count === 0) continue;
    if (needle && !defect.name.toLocaleLowerCase().includes(needle)) continue;
    const name = groupOf(defect);
    let group = groups.find((g) => g.name === name);
    if (!group) groups.push((group = { name, defects: [] }));
    group.defects.push({ key: defect.key, name: defect.name, count });
  }
  const other = groups.findIndex((g) => g.name === UNGROUPED);
  if (other >= 0) groups.push(...groups.splice(other, 1));
  return groups;
}

/** A name inside a sentence: "How it leads to sliver lines", but "CO2 blisters" keeps its capitals. */
export function inSentence(name) {
  const [first = "", second = ""] = name;
  const capital = first !== first.toLocaleLowerCase();
  return capital && second === second.toLocaleLowerCase() ? first.toLocaleLowerCase() + name.slice(1) : name;
}

// ---------------------------------------------------------------- the diagram

// The DefectView mockup's columns: the defect, where (the step under the process), how (the cause).
export const DIAGRAM = {
  top: 20,
  pitch: 74, // one cause per row
  defect: { x: 0, width: 150, height: 48 },
  where: { x: 190, width: 130, height: 42 },
  cause: { x: 360, width: 170, height: 60 },
};
const STUB = 20; // the short horizontal lines between the columns

/**
 * Lay out "how it arises": causes stack downwards in their order; each "where" sits level with the
 * middle of its causes; the defect level with the middle of the wheres. Lines join them.
 * @param {{key: string, where: string}[]} causes  from causesOf: causes with the same "where" are
 *   next to each other (map order)
 */
export function causeDiagram(causes) {
  const { top, pitch, defect, where, cause } = DIAGRAM;
  const lines = [];
  const wheres = [];
  const nodes = [];
  let cursor = top;
  for (const c of causes) {
    const last = wheres[wheres.length - 1];
    const y = cursor;
    cursor += pitch;
    nodes.push({ key: c.key, x: cause.x, y, width: cause.width, height: cause.height });
    if (last && last.key === c.where) last.rows.push(y + cause.height / 2);
    else wheres.push({ key: c.where, rows: [y + cause.height / 2] });
  }
  const middles = [];
  for (const w of wheres) {
    const first = w.rows[0];
    const lastRow = w.rows[w.rows.length - 1];
    const middle = (first + lastRow) / 2;
    middles.push(middle);
    w.x = where.x;
    w.y = middle - where.height / 2;
    w.width = where.width;
    w.height = where.height;
    const bus = cause.x - STUB;
    lines.push({ x: where.x + where.width, y: middle - 1, width: bus - where.x - where.width, height: 2 });
    if (w.rows.length > 1) lines.push({ x: bus - 1, y: first, width: 2, height: lastRow - first });
    for (const row of w.rows) lines.push({ x: bus, y: row - 1, width: STUB, height: 2 });
    delete w.rows;
  }
  const middle = middles.length ? (middles[0] + middles[middles.length - 1]) / 2 : top + defect.height / 2;
  if (middles.length) {
    const bus = where.x - STUB;
    lines.push({ x: defect.width, y: middle - 1, width: bus - defect.width, height: 2 });
    if (middles.length > 1) lines.push({ x: bus - 1, y: middles[0], width: 2, height: middles[middles.length - 1] - middles[0] });
    for (const m of middles) lines.push({ x: bus, y: m - 1, width: STUB, height: 2 });
  }
  return {
    defect: { x: defect.x, y: middle - defect.height / 2, width: defect.width, height: defect.height },
    wheres,
    causes: nodes,
    lines,
    width: cause.x + cause.width,
    height: Math.max(cursor, top + defect.height) + top,
  };
}
