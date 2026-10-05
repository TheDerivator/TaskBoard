/** The knowledge map (pure): its tree from the API's graph, what a view shows, the horizontal
 * layout (ported from the ProcessMap mockup), typed links both ways, roll-ups, search and the
 * keyboard. Positions are pixels on the map's canvas. */

// The mockup's columns: depth 0 (the process) is 160 px wide, then 150, 170, 200; deeper ones 200.
const COLUMN_WIDTHS = [160, 150, 170, 200];
const COLUMN_GAP = 36;
const ROW_GAP = 12;
const TOP = 18;
const STUB = 18; // the short horizontal line into each child

export function columnWidth(depth) {
  return COLUMN_WIDTHS[depth] ?? 200;
}

export function columnX(depth) {
  let x = 0;
  for (let d = 0; d < depth; d += 1) x += columnWidth(d) + COLUMN_GAP;
  return x;
}

/**
 * The process's own boxes as a tree, plus lookups for every box in the graph (defects, boxes of
 * other processes linked to this map).
 */
export function mapTree(graph) {
  const byKey = new Map(graph.boxes.map((b) => [b.key, b]));
  const own = graph.boxes.filter((b) => b.process_id === graph.process.id);
  const children = new Map();
  const parent = new Map();
  for (const box of own) {
    if (box.parent_key == null) continue;
    parent.set(box.key, box.parent_key);
    if (!children.has(box.parent_key)) children.set(box.parent_key, []);
    children.get(box.parent_key).push(box);
  }
  for (const list of children.values()) list.sort((a, b) => a.position - b.position || a.key.localeCompare(b.key));
  return {
    root: graph.root_key,
    byKey,
    own: new Set(own.map((b) => b.key)),
    children: new Map([...children].map(([k, list]) => [k, list.map((b) => b.key)])),
    parent,
    kinds: new Map(graph.kinds.map((k) => [k.key, k])),
  };
}

export function roleOf(tree, key) {
  const box = tree.byKey.get(key);
  return box ? tree.kinds.get(box.kind)?.role ?? "plain" : null;
}

/** From the root down to the box's parent. */
export function ancestors(tree, key) {
  const path = [];
  for (let at = tree.parent.get(key); at != null; at = tree.parent.get(at)) path.unshift(at);
  return path;
}

/** The box and everything below it. */
export function subtree(tree, key) {
  const result = new Set([key]);
  const stack = [key];
  while (stack.length) {
    for (const child of tree.children.get(stack.pop()) ?? []) {
      result.add(child);
      stack.push(child);
    }
  }
  return result;
}

/** The process's boxes from the top, each before the boxes under it (the map's reading order). */
export function readingOrder(tree) {
  const order = [];
  const walk = (key) => {
    order.push(key);
    for (const child of tree.children.get(key) ?? []) walk(child);
  };
  if (tree.root != null) walk(tree.root);
  return order;
}

/** What the FMEA shows: the failure modes and every box on the way to one (from the process down). */
export function fmeaBoxes(tree) {
  const kept = new Set(tree.root != null ? [tree.root] : []);
  for (const key of tree.own) {
    if (roleOf(tree, key) !== "failure_mode") continue;
    kept.add(key);
    for (const above of ancestors(tree, key)) kept.add(above);
  }
  return kept;
}

/**
 * The children a view shows: a hidden kind hides its whole branch (Knowledge view's kind chips);
 * `keep(key)`, when given, decides per child (the FMEA keeps steps leading to failure modes).
 */
export function shownChildren(tree, key, { hidden = new Set(), keep = null } = {}) {
  return (tree.children.get(key) ?? []).filter((child) => !hidden.has(tree.byKey.get(child).kind) && (!keep || keep(child)));
}

// ---------------------------------------------------------------- links

/** Outgoing and incoming links per box key. */
export function linkIndex(graph) {
  const outgoing = new Map();
  const incoming = new Map();
  for (const link of graph.links) {
    if (!outgoing.has(link.from_key)) outgoing.set(link.from_key, []);
    if (!incoming.has(link.to_key)) incoming.set(link.to_key, []);
    outgoing.get(link.from_key).push(link);
    incoming.get(link.to_key).push(link);
  }
  return { outgoing, incoming, types: new Map(graph.link_types.map((t) => [t.key, t])) };
}

const capital = (text) => text.charAt(0).toUpperCase() + text.slice(1);

/**
 * A box's typed links, both ways (DESIGN: each link shows on both boxes): grouped by wording, in
 * the link types' order, forward before backward: "Leads to", "Caused by", "Prevented by", ...
 * @returns {{label: string, type: string, direction: "forward"|"backward", items: {key: string, link: object}[]}[]}
 */
export function typedLinks(index, key) {
  const groups = [];
  const types = [...index.types.values()].sort((a, b) => a.position - b.position);
  for (const type of types) {
    const forward = (index.outgoing.get(key) ?? []).filter((l) => l.type === type.key);
    const backward = (index.incoming.get(key) ?? []).filter((l) => l.type === type.key);
    if (forward.length) {
      groups.push({ label: capital(type.forward_name), type: type.key, direction: "forward", items: forward.map((l) => ({ key: l.to_key, link: l })) });
    }
    if (backward.length) {
      groups.push({ label: capital(type.backward_name), type: type.key, direction: "backward", items: backward.map((l) => ({ key: l.from_key, link: l })) });
    }
  }
  return groups;
}

/** What a failure mode leads to that is a defect: the dark chips on its box ("→ Sliver lines"). */
export function effectsOf(tree, index, key) {
  const leadsTo = new Set([...index.types.values()].filter((t) => t.role === "leads_to").map((t) => t.key));
  return (index.outgoing.get(key) ?? [])
    .filter((l) => leadsTo.has(l.type) && roleOf(tree, l.to_key) === "defect")
    .map((l) => tree.byKey.get(l.to_key).name);
}

// ---------------------------------------------------------------- roll-ups and search

/**
 * Process changes per box, as a badge: DESIGN rule 8 rolls a change up to every box above it.
 * An open box counts what is attached to it; a closed one also what is hidden below it.
 */
export function changeBadges(tree, counts, collapsed) {
  const badges = new Map();
  const total = (key) => [...subtree(tree, key)].reduce((sum, k) => sum + (counts[k] ?? 0), 0);
  for (const key of tree.own) {
    if (ancestors(tree, key).some((a) => collapsed.has(a))) continue; // not shown
    const n = collapsed.has(key) ? total(key) : counts[key] ?? 0;
    if (n) badges.set(key, n);
  }
  return badges;
}

/** Name, description, key facts, step number or key containing the query (ignoring case). */
export function boxMatches(box, query) {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return false;
  const facts = box.facts.flat().join(" ");
  return [box.name, box.body_md, facts, box.step_no ?? "", box.key].some((text) => text.toLocaleLowerCase().includes(needle));
}

export function searchMap(tree, query) {
  return new Set([...tree.own].filter((key) => boxMatches(tree.byKey.get(key), query)));
}

/** The boxes to close for an overview: the process's branches, except the one holding `keep`. */
export function overviewCollapsed(tree, keep = null) {
  const open = new Set(keep ? [...ancestors(tree, keep), keep] : []);
  const collapsed = new Set();
  for (const child of tree.children.get(tree.root) ?? []) {
    if ((tree.children.get(child) ?? []).length && !open.has(child)) collapsed.add(child);
  }
  return collapsed;
}

/** Every box with boxes under it ("Collapse"): the process's branches. */
export function allCollapsed(tree) {
  return new Set((tree.children.get(tree.root) ?? []).filter((k) => (tree.children.get(k) ?? []).length));
}

// ---------------------------------------------------------------- layout

/** The mockup's estimate of a box's height: one or two label lines, plus a failure mode's chips. */
export function boxHeight(tree, key, depth, effects = []) {
  if (key === tree.root) return 48;
  const width = columnWidth(depth);
  const twoLines = tree.byKey.get(key).name.length * 7.1 > width - 48;
  if (roleOf(tree, key) === "failure_mode") {
    const chips = effects.reduce((sum, e) => sum + e.length * 6.2 + 26, 0) + 4 * Math.max(0, effects.length - 1);
    return (twoLines ? 18 : 0) + (chips > width - 24 ? 86 : 62);
  }
  return twoLines ? 56 : 40;
}

/**
 * Lay the tree out left to right: depth decides the column; leaves stack downwards; a parent
 * sits level with the middle of its shown children. Nodes come in reading (pre-)order.
 * @returns {{nodes: object[], lines: {x: number, y: number, width: number, height: number}[], width: number, height: number}}
 */
export function layoutMap(tree, { collapsed = new Set(), hidden = new Set(), keep = null, effects = () => [] } = {}) {
  const nodes = [];
  const lines = [];
  let cursor = TOP;
  let deepest = 0;
  if (tree.root == null) return { nodes, lines, width: 0, height: 0 };

  const place = (key, depth) => {
    deepest = Math.max(deepest, depth);
    const shown = shownChildren(tree, key, { hidden, keep });
    const expanded = shown.length > 0 && !collapsed.has(key);
    const height = boxHeight(tree, key, depth, effects(key));
    const node = { key, depth, x: columnX(depth), width: columnWidth(depth), height, y: 0, shownCount: shown.length, expanded };
    nodes.push(node);
    let middle;
    if (expanded) {
      const ys = shown.map((child) => place(child, depth + 1));
      middle = (ys[0] + ys[ys.length - 1]) / 2;
      const bus = columnX(depth + 1) - STUB; // where the vertical line runs
      lines.push({ x: node.x + node.width, y: middle - 1, width: bus - node.x - node.width, height: 2 });
      if (ys.length > 1) lines.push({ x: bus - 1, y: ys[0], width: 2, height: ys[ys.length - 1] - ys[0] });
      for (const y of ys) lines.push({ x: bus, y: y - 1, width: STUB, height: 2 });
    } else {
      middle = cursor + height / 2;
      cursor += height + ROW_GAP;
    }
    node.y = middle - height / 2;
    return middle;
  };
  place(tree.root, 0);
  return { nodes, lines, width: columnX(deepest) + columnWidth(deepest) + 16, height: cursor + 20 };
}

// ---------------------------------------------------------------- keyboard

/**
 * Arrow keys on a box: Up/Down go to the box before or after it in reading order; Right opens a
 * closed box or goes to its first child; Left closes an open box or goes to its parent;
 * Home/End go to the first and last box.
 * @returns {{select: string} | {expand: string} | {collapse: string} | null}
 */
export function keyboardMove(layout, tree, key, keyName) {
  const order = layout.nodes;
  const index = order.findIndex((n) => n.key === key);
  if (index < 0) return null;
  const node = order[index];
  switch (keyName) {
    case "ArrowDown":
      return index + 1 < order.length ? { select: order[index + 1].key } : null;
    case "ArrowUp":
      return index > 0 ? { select: order[index - 1].key } : null;
    case "Home":
      return { select: order[0].key };
    case "End":
      return { select: order[order.length - 1].key };
    case "ArrowRight":
      if (node.shownCount && !node.expanded) return { expand: key };
      return node.expanded ? { select: order[index + 1].key } : null;
    case "ArrowLeft":
      if (node.expanded) return { collapse: key };
      return tree.parent.has(key) ? { select: tree.parent.get(key) } : null;
    default:
      return null;
  }
}
