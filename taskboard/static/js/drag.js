/** Reordering ranked lists: pointer drag-and-drop (mouse, touch, pen) and the keyboard. */
import { dropSide, keyboardStep } from "./lib/dnd.js";
import { useEffect, useRef, useState } from "./ui.js";

const THRESHOLD = 5; // px of movement before a press becomes a drag (so clicks still work)
const EDGE = 60; // px from the viewport edge where auto-scrolling starts
const INTERACTIVE = "a, button, input, select, textarea, label, [contenteditable]";

/**
 * Make the items of a list sortable by dragging.
 * Items are the elements matching `[data-key]` inside the list (`data-draggable="false"` makes one
 * a drop target only). Mouse drags start anywhere on an
 * item except on links and controls (a link marked `data-drag-surface`, such as a whole card, is
 * fine: a click still follows it); touch drags start on the item's `.grip` (so the page can
 * still be scrolled by touch). Escape cancels.
 *
 * Keyboard: on an item's `.grip` button, Arrow Up/Down move the item one place and Home/End to
 * the ends of the list, as drops on the neighbour; focus stays on the moved item's grip.
 *
 * Returns a callback ref for the list element (the list may mount later, e.g. after loading).
 * @param {{enabled: boolean, onDrop: (draggedKey: string, targetKey: string, where: string) => void}} options
 */
export function useSortable({ enabled, onDrop }) {
  const [list, setList] = useState(null);
  const onDropRef = useRef(onDrop);
  onDropRef.current = onDrop;

  useEffect(() => {
    if (!list || !enabled) return undefined;
    let press = null; // { item, key, x, y, pointerId, dragging, target, where }
    let scrollFrame = 0;
    let lastY = 0;

    const items = () => [...list.querySelectorAll("[data-key]")];
    const clearMarks = () => {
      for (const item of items()) item.removeAttribute("data-drop");
    };

    const stop = () => {
      cancelAnimationFrame(scrollFrame);
      if (press?.dragging) {
        press.item.classList.remove("is-dragging");
        list.classList.remove("is-sorting");
        clearMarks();
      }
      press = null;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", stop);
      window.removeEventListener("keydown", onKey);
    };

    const autoScroll = () => {
      if (!press?.dragging) return;
      const speed = lastY < EDGE ? -12 : lastY > window.innerHeight - EDGE ? 12 : 0;
      if (speed) window.scrollBy(0, speed);
      scrollFrame = requestAnimationFrame(autoScroll);
    };

    const onMove = (event) => {
      if (!press || event.pointerId !== press.pointerId) return;
      lastY = event.clientY;
      if (!press.dragging) {
        if (Math.hypot(event.clientX - press.x, event.clientY - press.y) < THRESHOLD) return;
        press.dragging = true;
        window.getSelection()?.removeAllRanges();
        press.item.classList.add("is-dragging");
        list.classList.add("is-sorting");
        scrollFrame = requestAnimationFrame(autoScroll);
      }
      event.preventDefault();
      const under = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-key]");
      clearMarks();
      press.target = null;
      if (under && list.contains(under) && under !== press.item) {
        const order = items().map((item) => item.dataset.key);
        press.target = under.dataset.key;
        press.where = dropSide(order, press.key, press.target);
        under.setAttribute("data-drop", press.where);
      }
    };

    const onUp = (event) => {
      if (!press || event.pointerId !== press.pointerId) return;
      const { dragging, key, target, where } = press;
      stop();
      if (!dragging) return;
      // Swallow the click the browser fires right after the drag, so it doesn't open the task.
      // It is dispatched in the same turn as pointerup, so the guard is removed right after.
      const swallow = (e) => {
        e.stopPropagation();
        e.preventDefault();
      };
      window.addEventListener("click", swallow, { capture: true });
      setTimeout(() => window.removeEventListener("click", swallow, { capture: true }), 0);
      if (target) onDropRef.current(key, target, where);
    };

    const onKey = (event) => {
      if (event.key === "Escape") stop();
    };

    const onDown = (event) => {
      if (event.button !== 0 || press) return;
      const item = event.target.closest("[data-key]");
      if (!item || !list.contains(item) || item.dataset.draggable === "false") return;
      const onGrip = Boolean(event.target.closest(".grip"));
      if (event.pointerType !== "mouse" && !onGrip) return;
      const control = event.target.closest(INTERACTIVE);
      if (!onGrip && control && !control.hasAttribute("data-drag-surface")) return;
      event.preventDefault(); // no text selection or native image drag while pressing a row
      press = { item, key: item.dataset.key, x: event.clientX, y: event.clientY, pointerId: event.pointerId, dragging: false };
      window.addEventListener("pointermove", onMove, { passive: false });
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", stop);
      window.addEventListener("keydown", onKey);
    };

    const onGripKey = (event) => {
      if (press || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const item = event.target.closest(".grip")?.closest("[data-key]");
      if (!item || !list.contains(item) || item.dataset.draggable === "false") return;
      const { key } = item.dataset;
      const step = keyboardStep(items().map((i) => i.dataset.key), key, event.key);
      if (step === undefined) return;
      event.preventDefault(); // also at the ends: the arrow keys don't scroll the page
      if (!step) return;
      onDropRef.current(key, step.target, step.where);
      // The re-render moves the row, which drops its focus: put it back once rendered.
      requestAnimationFrame(() => list.querySelector(`[data-key="${CSS.escape(key)}"] .grip`)?.focus());
    };

    list.addEventListener("pointerdown", onDown);
    list.addEventListener("keydown", onGripKey);
    return () => {
      list.removeEventListener("pointerdown", onDown);
      list.removeEventListener("keydown", onGripKey);
      stop();
    };
  }, [list, enabled]);

  return setList;
}
