/** "Link to a box": a dialog that searches every map and defect catalogue the visitor can see
 * (GET /api/boxes?q=) and, when nothing fits, offers to create a defect with that name. */
import { api } from "../api.js";
import { html, useEffect, useRef, useState } from "../ui.js";
import { Dialog } from "./dialog.js";
import { showError } from "./toasts.js";

/** "Ladle metallurgy › Trim & stirring" (the root of a map is its process). */
export function boxRefLabel(ref) {
  return [...ref.path, ref.name].join(" › ");
}

/**
 * @param {{open: boolean, title: string, onPick: (ref: object) => void, onClose: () => void,
 *   exclude?: string[], onCreateDefect?: ?((name: string) => Promise<object>)}} props
 */
export function BoxPicker({ open, title, onPick, onClose, exclude = [], onCreateDefect = null }) {
  return html`<${Dialog} open=${open} title=${title} onClose=${onClose}>
    <${PickerBody} onPick=${onPick} exclude=${exclude} onCreateDefect=${onCreateDefect} />
  <//>`;
}

function PickerBody({ onPick, exclude, onCreateDefect }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [active, setActive] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    const ticket = ++latest.current;
    if (!query.trim()) {
      setResults([]);
      return undefined;
    }
    const timer = setTimeout(() => {
      api.get("/boxes", { q: query }).then(
        (found) => ticket === latest.current && setResults(found.filter((r) => !exclude.includes(r.key))),
        showError,
      );
    }, 150);
    return () => clearTimeout(timer);
  }, [query]);
  useEffect(() => setActive(0), [results]);

  const create = async () => {
    try {
      onPick(await onCreateDefect(query.trim()));
    } catch (error) {
      showError(error);
    }
  };
  const onKey = (event) => {
    if (event.key === "ArrowDown") setActive((i) => Math.min(i + 1, results.length - 1));
    else if (event.key === "ArrowUp") setActive((i) => Math.max(i - 1, 0));
    else if (event.key === "Enter" && results[active]) onPick(results[active]);
    else return;
    event.preventDefault();
  };
  return html`
    <div class="dialog__body box-picker">
      <input
        class="input"
        type="search"
        autofocus
        aria-label="Find a box by name"
        placeholder="Find a box by name…"
        value=${query}
        onInput=${(e) => setQuery(e.currentTarget.value)}
        onKeyDown=${onKey}
      />
      <ul class="box-picker__results" aria-label="Boxes found">
        ${results.map(
          (r, i) => html`
            <li key=${r.key}>
              <button type="button" class=${`box-picker__result${i === active ? " is-active" : ""}`} onClick=${() => onPick(r)}>
                <span class="box-picker__name">${r.name}</span>
                <span class="box-picker__path">${r.path.length ? r.path.join(" › ") : r.process_id == null ? "Defect" : "A process"}</span>
              </button>
            </li>
          `,
        )}
      </ul>
      ${query.trim() && results.length === 0 && html`<p class="muted">No box is called like that.</p>`}
      ${onCreateDefect && query.trim() && html`<button type="button" class="btn btn--dashed" onClick=${create}>Create the defect “${query.trim()}”</button>`}
    </div>
  `;
}
