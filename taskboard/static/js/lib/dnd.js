/** Drag-and-drop reordering rules (pure): drop side, and the optimistic local reorder. */

/**
 * Which side of the target row a dragged row lands on, as in the design mockup and the server:
 * dragging downwards drops after the target, dragging upwards drops before it.
 * @param {string[]} order  keys in rank order (may be a filtered subset)
 */
export function dropSide(order, draggedKey, targetKey) {
  return order.indexOf(draggedKey) < order.indexOf(targetKey) ? "after" : "before";
}

/**
 * The full task list after moving `draggedKey` before/after `targetKey`, with ranks renumbered
 * 1..N. Used to show the result immediately while the server confirms it.
 * @param {Array<{key: string, rank: number}>} tasks  all visible tasks, in rank order
 */
export function reorder(tasks, draggedKey, targetKey, where) {
  if (draggedKey === targetKey) return tasks;
  const dragged = tasks.find((t) => t.key === draggedKey);
  if (!dragged || !tasks.some((t) => t.key === targetKey)) return tasks;
  const rest = tasks.filter((t) => t.key !== draggedKey);
  const index = rest.findIndex((t) => t.key === targetKey) + (where === "after" ? 1 : 0);
  rest.splice(index, 0, dragged);
  // Visible ranks may have gaps (tasks the viewer can't see); keep the same set of rank numbers.
  const ranks = tasks.map((t) => t.rank).sort((a, b) => a - b);
  return rest.map((t, i) => (t.rank === ranks[i] ? t : { ...t, rank: ranks[i] }));
}

const STEP_KEYS = new Set(["ArrowUp", "ArrowDown", "Home", "End"]);

/**
 * Keyboard reordering: where a key sends the task, as a drop on a neighbour.
 * Returns undefined for keys that don't reorder, null when the task is already at that end.
 * @param {string[]} order  keys in rank order (may be a filtered subset)
 * @returns {{target: string, where: "before" | "after"} | null | undefined}
 */
export function keyboardStep(order, key, keyName) {
  if (!STEP_KEYS.has(keyName)) return undefined;
  const index = order.indexOf(key);
  if (index === -1) return undefined;
  const last = order.length - 1;
  const up = keyName === "ArrowUp" || keyName === "Home";
  if ((up && index === 0) || (!up && index === last)) return null;
  switch (keyName) {
    case "ArrowUp":
      return { target: order[index - 1], where: "before" };
    case "ArrowDown":
      return { target: order[index + 1], where: "after" };
    case "Home":
      return { target: order[0], where: "before" };
    default:
      return { target: order[last], where: "after" };
  }
}
