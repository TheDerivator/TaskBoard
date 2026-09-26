// Unit tests for static/js/lib/dnd.js: drop sides, optimistic reordering, keyboard steps.
import assert from "node:assert/strict";
import { test } from "node:test";

import { dropSide, keyboardStep, reorder } from "../../taskboard/static/js/lib/dnd.js";

const tasks = (...keys) => keys.map((key, i) => ({ key, rank: i + 1 }));
const view = (list) => list.map((t) => `${t.rank}:${t.key}`);

test("dragging down drops after the target, up drops before it", () => {
  const order = ["a", "b", "c", "d"];
  assert.equal(dropSide(order, "a", "c"), "after");
  assert.equal(dropSide(order, "d", "b"), "before");
});

test("reorder renumbers ranks", () => {
  const list = tasks("a", "b", "c", "d", "e");
  assert.deepEqual(view(reorder(list, "e", "b", "before")), ["1:a", "2:e", "3:b", "4:c", "5:d"]);
  assert.deepEqual(view(reorder(list, "a", "c", "after")), ["1:b", "2:c", "3:a", "4:d", "5:e"]);
});

test("a drop in a filtered list moves relative to the drop row (rule 2)", () => {
  // Visible filtered rows: a, c, e. Dragging e up onto c puts e directly before c.
  const list = tasks("a", "b", "c", "d", "e");
  const side = dropSide(["a", "c", "e"], "e", "c");
  assert.deepEqual(view(reorder(list, "e", "c", side)), ["1:a", "2:b", "3:e", "4:c", "5:d"]);
});

test("ranks with gaps (restricted viewer) keep their numbers", () => {
  const list = [
    { key: "a", rank: 2 },
    { key: "b", rank: 5 },
    { key: "c", rank: 9 },
  ];
  assert.deepEqual(view(reorder(list, "c", "a", "before")), ["2:c", "5:a", "9:b"]);
});

test("no-ops", () => {
  const list = tasks("a", "b");
  assert.equal(reorder(list, "a", "a", "after"), list);
  assert.equal(reorder(list, "x", "a", "after"), list);
});

test("arrow keys move one place, Home and End to the ends", () => {
  const order = ["a", "b", "c", "d"];
  assert.deepEqual(keyboardStep(order, "c", "ArrowUp"), { target: "b", where: "before" });
  assert.deepEqual(keyboardStep(order, "b", "ArrowDown"), { target: "c", where: "after" });
  assert.deepEqual(keyboardStep(order, "c", "Home"), { target: "a", where: "before" });
  assert.deepEqual(keyboardStep(order, "b", "End"), { target: "d", where: "after" });
  // The same drop, applied, gives the expected order.
  const moved = reorder(tasks(...order), "c", "b", "before");
  assert.deepEqual(view(moved), ["1:a", "2:c", "3:b", "4:d"]);
});

test("keyboard steps stop at the ends and ignore other keys", () => {
  const order = ["a", "b", "c"];
  assert.equal(keyboardStep(order, "a", "ArrowUp"), null);
  assert.equal(keyboardStep(order, "a", "Home"), null);
  assert.equal(keyboardStep(order, "c", "ArrowDown"), null);
  assert.equal(keyboardStep(order, "c", "End"), null);
  assert.equal(keyboardStep(order, "b", "Enter"), undefined);
  assert.equal(keyboardStep(order, "x", "ArrowUp"), undefined);
  assert.equal(keyboardStep(["a"], "a", "ArrowDown"), null);
});
