/** The map canvas: boxes laid out left to right (lib/maplayout.js), the lines between them, a toggle
 * on every box with boxes under it. Boxes are buttons in reading order; arrow keys move between them. */
import { ChangesIcon, ExternalIcon, FailureModeIcon, InfoIcon, PlainKindIcon, RuleIcon } from "../../components/icons.js";
import { effectsOf, keyboardMove } from "../../lib/maplayout.js";
import { html, useEffect, useRef } from "../../ui.js";

const ROLE_ICONS = {
  failure_mode: FailureModeIcon,
  knowledge: InfoIcon,
  reference: ExternalIcon,
  rule: RuleIcon,
  plain: PlainKindIcon,
};

/** The style class of a box: its kind's palette entry, the process at the root a dark pill. */
export function kindClass(tree, key) {
  if (key === tree.root) return "kind--root";
  const kind = tree.kinds.get(tree.byKey.get(key)?.kind);
  return `kind--${kind?.style ?? "grey"}`;
}

export function KindIcon({ tree, boxKey }) {
  const kind = tree.kinds.get(tree.byKey.get(boxKey)?.kind);
  const Icon = boxKey === tree.root ? null : ROLE_ICONS[kind?.role];
  return Icon ? html`<${Icon} />` : null;
}

/** Scroll the map so a box is in view: up or down as needed, sideways only when it is (almost)
 * out of sight, so the process at the left stays visible whenever it can. */
function revealBox(element, viewport) {
  const box = element.getBoundingClientRect();
  const view = viewport.getBoundingClientRect();
  if (box.top < view.top || box.bottom > view.bottom) {
    viewport.scrollTop += box.top - view.top - (view.height - box.height) / 2;
  }
  if (box.right < view.left + 40 || box.left > view.right - 40) {
    viewport.scrollLeft += box.left - view.left - 24;
  }
}

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

function MapBox({ node, tree, index, processName, selected, focusable, badge, draft, match, dimmed, onSelect, onToggle, onKey }) {
  const box = tree.byKey.get(node.key);
  const kind = tree.kinds.get(box.kind);
  const isRoot = node.key === tree.root;
  const label = isRoot ? processName : box.name;
  const effects = kind?.role === "failure_mode" ? effectsOf(tree, index, node.key) : [];
  const spoken = [
    label,
    isRoot ? "the process" : kind?.name,
    effects.length ? `leads to ${effects.join(", ")}` : null,
    badge ? plural(badge, "process change", "process changes") : null,
    draft ? draft : null,
  ]
    .filter(Boolean)
    .join(", ");
  const classes = [
    "map-box",
    kindClass(tree, node.key),
    kind?.role === "step" && node.depth > 1 && "map-box--thin",
    selected && "is-selected",
    match && "is-match",
    dimmed && "is-dimmed",
  ]
    .filter(Boolean)
    .join(" ");
  return html`
    <div class=${classes} data-box=${node.key} style=${{ left: `${node.x}px`, top: `${node.y}px`, width: `${node.width}px`, height: `${node.height}px` }}>
      <button
        type="button"
        class="map-box__main"
        aria-pressed=${selected ? "true" : "false"}
        aria-label=${spoken}
        tabindex=${focusable ? "0" : "-1"}
        onClick=${() => onSelect(node.key)}
        onKeyDown=${(event) => onKey(event, node.key)}
      >
        <span class="map-box__line">
          <${KindIcon} tree=${tree} boxKey=${node.key} />
          <span class="map-box__label">${label}</span>
          ${badge > 0 && html`<span class="map-box__badge" title=${plural(badge, "process change", "process changes")}><${ChangesIcon} size=${10} />${badge}</span>`}
          ${draft && html`<span class="map-box__draft" title=${draft}></span>`}
        </span>
        ${effects.length > 0 && html`<span class="map-box__effects">${effects.map((e) => html`<span key=${e} class="effect-chip">→ ${e}</span>`)}</span>`}
      </button>
      ${node.shownCount > 0 &&
      html`<button
        type="button"
        class="map-box__toggle"
        aria-expanded=${node.expanded ? "true" : "false"}
        aria-label=${`${node.expanded ? "Collapse" : "Expand"} ${label}`}
        onClick=${() => onToggle(node.key, !node.expanded)}
      >${node.expanded ? "−" : `+${node.shownCount}`}</button>`}
    </div>
  `;
}

/**
 * @param {{graph: object, tree: object, index: object, layout: object, selected: string,
 *   onSelect: (key: string) => void, onToggle: (key: string, open: boolean) => void,
 *   badges?: Map<string, number>, drafts?: Map<string, string>, matches?: Set<string>, label: string}} props
 */
export function MapCanvas({ graph, tree, index, layout, selected, onSelect, onToggle, badges = new Map(), drafts = new Map(), matches = null, label }) {
  const canvas = useRef(null);
  // The box a keyboard move goes to; it takes focus once it is shown and selected. (Several
  // renders may come first: opening a branch and changing the address are separate updates.)
  const focusNext = useRef(null);
  const shown = new Set(layout.nodes.map((n) => n.key));
  const focusKey = shown.has(selected) ? selected : tree.root;

  // The selected box comes into view (e.g. opened from a link); after a keyboard move it takes focus.
  useEffect(() => {
    const element = canvas.current?.querySelector(`[data-box="${CSS.escape(focusKey ?? "")}"]`);
    if (!element) return;
    revealBox(element, canvas.current.parentElement);
    if (focusNext.current === focusKey) {
      focusNext.current = null;
      element.querySelector(".map-box__main")?.focus();
    }
  }, [focusKey, layout]);

  const onKey = (event, key) => {
    const move = keyboardMove(layout, tree, key, event.key);
    if (!move) return;
    event.preventDefault();
    focusNext.current = move.select ?? key;
    if (move.select) onSelect(move.select);
    if (move.expand) onToggle(move.expand, true);
    if (move.collapse) onToggle(move.collapse, false);
  };

  return html`
    <div class="map" role="group" aria-label=${label}>
      <div class="map__canvas" ref=${canvas} style=${{ width: `${layout.width}px`, height: `${Math.max(layout.height, 480)}px` }}>
        ${layout.lines.map(
          (l, i) => html`<span key=${i} class="map__line" aria-hidden="true" style=${{ left: `${l.x}px`, top: `${l.y}px`, width: `${l.width}px`, height: `${l.height}px` }}></span>`,
        )}
        ${layout.nodes.map(
          (node) => html`<${MapBox}
            key=${node.key}
            node=${node}
            tree=${tree}
            index=${index}
            processName=${graph.process.name}
            selected=${node.key === selected}
            focusable=${node.key === focusKey}
            badge=${badges.get(node.key) ?? 0}
            draft=${drafts.get(node.key) ?? null}
            match=${matches?.has(node.key) ?? false}
            dimmed=${matches != null && matches.size > 0 && !matches.has(node.key)}
            onSelect=${onSelect}
            onToggle=${onToggle}
            onKey=${onKey}
          />`,
        )}
      </div>
    </div>
  `;
}
