/** Transient notifications: `showToast(text)`, `showError(error)`, and the <Toasts/> outlet. */
import { CloseIcon } from "./icons.js";
import { html, useEffect, useState } from "../ui.js";

let toasts = [];
let nextId = 1;
const listeners = new Set();

function publish() {
  for (const listener of listeners) listener(toasts);
}

export function dismissToast(id) {
  toasts = toasts.filter((t) => t.id !== id);
  publish();
}

export function showToast(text, { kind = "info", timeout = 4000 } = {}) {
  const id = nextId++;
  toasts = [...toasts, { id, text, kind }];
  publish();
  if (timeout) setTimeout(() => dismissToast(id), timeout);
}

export function showError(error) {
  showToast(error?.message ?? String(error), { kind: "error", timeout: 7000 });
}

export function Toasts() {
  const [items, setItems] = useState(toasts);
  useEffect(() => {
    listeners.add(setItems);
    return () => listeners.delete(setItems);
  }, []);
  return html`
    <div class="toasts" role="status" aria-live="polite">
      ${items.map(
        (t) => html`
          <div class=${`toast toast--${t.kind}`} key=${t.id}>
            <span>${t.text}</span>
            <button type="button" aria-label="Dismiss" onClick=${() => dismissToast(t.id)}>
              <${CloseIcon} size=${14} />
            </button>
          </div>
        `,
      )}
    </div>
  `;
}
