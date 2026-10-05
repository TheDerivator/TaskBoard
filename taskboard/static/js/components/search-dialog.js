/** "Search everything" (the GlobalSearch mockup): Ctrl K anywhere or the sidebar entry; type
 * filters with counts; ↑ ↓ move, Enter opens, Ctrl Enter opens in a new tab; every hit shows the
 * link it opens. The input is a combobox over a listbox whose options are the links themselves. */
import { api } from "../api.js";
import { filterChips, hitContext, moveActive, shownGroups, shownHits } from "../lib/search.js";
import { href, navigate } from "../router.js";
import { html, useEffect, useRef, useState } from "../ui.js";
import { useModalDialog } from "./dialog.js";
import { SearchIcon } from "./icons.js";

const DELAY_MS = 150; // typing pauses this long before a search goes out

const SWATCH = { changes: "search-swatch--change", tasks: "search-swatch--task", defects: "kind--ink" };

function swatchClass(hit) {
  if (hit.type === "knowledge") return `search-swatch kind--${hit.style ?? "grey"}`;
  return `search-swatch ${SWATCH[hit.type]}`;
}

function OpenSearch({ onClose }) {
  const ref = useRef(null);
  const input = useRef(null);
  const { props } = useModalDialog(ref, onClose);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [failed, setFailed] = useState(null);
  const [filter, setFilter] = useState(null);
  const [active, setActive] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    input.current?.focus();
  }, []);
  useEffect(() => {
    const ticket = ++latest.current;
    if (query.trim().length < 2) {
      setResults(null);
      return undefined;
    }
    const timer = setTimeout(async () => {
      try {
        const found = await api.get("/search", { q: query });
        if (ticket !== latest.current) return;
        setResults(found);
        setFailed(null);
        setActive(0);
      } catch (error) {
        if (ticket === latest.current) setFailed(error.message);
      }
    }, DELAY_MS);
    return () => clearTimeout(timer);
  }, [query]);

  const groups = results?.groups ?? [];
  const hits = shownHits(groups, filter);
  const current = hits[Math.min(active, hits.length - 1)];
  const optionId = (hit) => `search-hit-${hit.type}-${hit.key}`;
  const open = (hit, newTab) => {
    if (newTab) {
      window.open(href(hit.url), "_blank", "noopener");
      return;
    }
    onClose();
    navigate(hit.url);
  };
  const onKey = (event) => {
    if (event.key === "Enter" && current) {
      event.preventDefault();
      open(current, event.ctrlKey || event.metaKey);
      return;
    }
    if (["ArrowDown", "ArrowUp"].includes(event.key) || (["Home", "End"].includes(event.key) && event.ctrlKey)) {
      event.preventDefault();
      const next = moveActive(active, event.key, hits.length);
      setActive(next);
      document.getElementById(optionId(hits[next] ?? {}))?.scrollIntoView({ block: "nearest" });
    }
  };
  const choose = (type) => {
    setFilter(type);
    setActive(0);
    input.current?.focus();
  };

  return html`
    <dialog ref=${ref} class="dialog search-dialog" aria-label="Search everything" ...${props}>
      <div class="search-dialog__bar">
        <${SearchIcon} />
        <input
          ref=${input}
          type="search"
          role="combobox"
          aria-label="Search tasks, process changes, knowledge and defects"
          aria-expanded=${hits.length > 0 ? "true" : "false"}
          aria-controls="search-results"
          aria-autocomplete="list"
          aria-activedescendant=${current ? optionId(current) : undefined}
          placeholder="Search tasks, process changes, knowledge and defects…"
          value=${query}
          onInput=${(e) => setQuery(e.currentTarget.value)}
          onKeyDown=${onKey}
        />
        <button type="button" class="search-dialog__esc" onClick=${onClose}>Esc</button>
      </div>
      ${results &&
      html`<div class="search-dialog__filters" role="group" aria-label="Filter results">
        ${filterChips(groups).map(
          (c) => html`
            <button key=${c.type ?? "all"} type="button" class="toggle-chip" aria-pressed=${filter === c.type ? "true" : "false"} onClick=${() => choose(c.type)}>
              ${c.label} · ${c.count}
            </button>
          `,
        )}
      </div>`}
      <div class="search-dialog__results">
        ${failed && html`<p class="form-error" role="alert">${failed}</p>`}
        ${!results && !failed && html`<p class="search-dialog__hint muted">Type at least two letters. Every word must match.</p>`}
        ${results && hits.length === 0 && html`<p class="search-dialog__hint muted" role="status">Nothing found for “${results.query}”.</p>`}
        <div id="search-results" role="listbox" aria-label="Results">
          ${shownGroups(groups, filter).map(
            (group) => html`
              <div key=${group.type} role="group" aria-label=${group.label} class="search-group">
                <div class="search-group__name" aria-hidden="true">${group.label}</div>
                ${group.hits.map(
                  (hit) => html`
                    <a
                      key=${hit.key}
                      id=${optionId(hit)}
                      role="option"
                      tabindex="-1"
                      aria-selected=${hit === current ? "true" : "false"}
                      class=${`search-hit${hit === current ? " is-active" : ""}`}
                      href=${href(hit.url)}
                      onClick=${(e) => {
                        if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
                        e.preventDefault();
                        open(hit, false);
                      }}
                      onMouseMove=${() => setActive(hits.indexOf(hit))}
                    >
                      <span class=${swatchClass(hit)} aria-hidden="true"></span>
                      <span class="search-hit__text">
                        <span class="search-hit__title">${hit.ref && html`<span class="search-hit__ref">${hit.ref}</span>`}${hit.title}</span>
                        <span class="search-hit__context">${hitContext(hit)}</span>
                      </span>
                      <span class="search-hit__url">${hit.url}</span>
                    </a>
                  `,
                )}
              </div>
            `,
          )}
        </div>
      </div>
      <div class="search-dialog__keys" aria-hidden="true">
        <span>↑ ↓ move</span><span>Enter open</span><span>Ctrl Enter open in new tab</span>
        <span class="search-dialog__share">Every result has its own link you can share</span>
      </div>
    </dialog>
  `;
}

/** Rendered only while open. */
export function SearchDialog({ open, onClose }) {
  return open ? html`<${OpenSearch} onClose=${onClose} />` : null;
}
