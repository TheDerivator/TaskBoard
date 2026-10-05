/** Process knowledge of one process, read three ways: the knowledge map, the FMEA, the control plan. */
import { api } from "../../api.js";
import { SearchIcon, SlidersIcon } from "../../components/icons.js";
import { ProcessHeader, ProcessPageMessage, useProcessPage } from "../../components/process-header.js";
import { showError } from "../../components/toasts.js";
import { useApi, useTitle } from "../../hooks.js";
import { canIn } from "../../lib/lookup.js";
import {
  allCollapsed,
  ancestors,
  changeBadges,
  effectsOf,
  fmeaBoxes,
  layoutMap,
  linkIndex,
  mapTree,
  overviewCollapsed,
  roleOf,
  searchMap,
} from "../../lib/maplayout.js";
import { parseRelease } from "../../lib/releases.js";
import { boxLinkPath, fmeaPath, knowledgePath } from "../../lib/routes.js";
import { navigate } from "../../router.js";
import { dataChanged } from "../../store.js";
import { html, useEffect, useMemo, useState } from "../../ui.js";
import { ControlPlanView } from "./cpl.js";
import { BoxEditorDrawer } from "./editor.js";
import { MapCanvas } from "./map.js";
import { BoxPanel } from "./panel.js";
import { FmeaSheet } from "./print.js";
import { ReleaseBar, ReleaseDialog, versionText } from "./release.js";
import { MapSettingsDialog } from "./settings.js";
import { VIEWS, viewPath, ViewSwitch } from "./switch.js";

function NoMap({ graph, onStarted }) {
  const start = async () => {
    try {
      await api.post(`/processes/${encodeURIComponent(graph.process.code)}/map`);
      onStarted();
    } catch (error) {
      showError(error);
    }
  };
  return html`
    <div class="map-empty">
      <div class="map-empty__card">
        <h2>No map for ${graph.process.name} yet</h2>
        <p class="muted">Start with the process as the root and add its steps. Knowledge, references, rules and failure modes can hang anywhere in the tree.</p>
        ${graph.can_edit && html`<button type="button" class="btn btn--primary" onClick=${start}>Start the map</button>`}
      </div>
    </div>
  `;
}

/** The kinds this map uses (defects live in the catalogue, not in the tree), as show/hide chips. */
function KindChips({ graph, tree, hidden, setHidden }) {
  const used = new Set([...tree.own].filter((k) => k !== tree.root).map((k) => tree.byKey.get(k).kind));
  const kinds = graph.kinds.filter((k) => used.has(k.key));
  const toggle = (key) => {
    const next = new Set(hidden);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setHidden(next);
  };
  return html`
    <div class="chip-group" role="group" aria-label="Show kinds">
      ${kinds.map(
        (k) => html`
          <button key=${k.key} type="button" class=${`kind-chip kind--${k.style}`} aria-pressed=${hidden.has(k.key) ? "false" : "true"} onClick=${() => toggle(k.key)}>
            <span class="kind-swatch" aria-hidden="true"></span>${k.name}
          </button>
        `,
      )}
    </div>
  `;
}

/**
 * A process's map, read as the knowledge map (every box, kind chips) or as the FMEA (only failure
 * modes and the boxes on the way to them, DESIGN "Three views"); the same panel and editor.
 */
function ProcessMap({ view, page, route, boot, lookup }) {
  const { department, process } = page;
  const fmea = view === "fmea";
  const code = encodeURIComponent(process.code);
  // The FMEA can show a released version (read only); the current one marks what changed since.
  const viewing = fmea ? parseRelease(route.params.release) : null;
  const { data: graph, error, reload } = useApi(`/processes/${code}/map`, viewing ? { release: viewing } : undefined);
  const releases = useApi(fmea ? `/processes/${code}/releases` : null);
  const [reviewing, setReviewing] = useState(false);
  const tree = useMemo(() => (graph?.root_key ? mapTree(graph) : null), [graph]);
  const index = useMemo(() => (graph ? linkIndex(graph) : null), [graph]);
  const kept = useMemo(() => (fmea && tree ? fmeaBoxes(tree) : null), [fmea, tree]);
  const keep = kept ? (key) => kept.has(key) : null;
  const requested = route.params.box;
  const selected = tree && requested && tree.byKey.has(requested) && (!keep || keep(requested)) ? requested : tree?.root;
  const [collapsed, setCollapsed] = useState(null);
  const [hidden, setHidden] = useState(() => new Set());
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null); // {boxKey} | {parentKey}

  // The knowledge map opens as an overview: the process's branches closed, except the selected
  // box's. The FMEA, much smaller, opens fully (the FmeaMap mockup).
  const initial = () => (fmea ? new Set() : overviewCollapsed(tree, selected));
  useEffect(() => {
    if (tree && collapsed == null) setCollapsed(initial());
  }, [tree]);
  // A map link naming a box of another process (it moved, or the link was mistyped) goes to
  // where the box lives (DESIGN "Stable links": the key decides).
  const named = graph && requested ? graph.boxes.find((b) => b.key === requested) : null;
  const elsewhere = !fmea && graph && requested && (!named || (named.process_id != null && named.process_id !== graph.process.id));
  useEffect(() => {
    if (elsewhere) navigate(boxLinkPath(requested), { replace: true });
  }, [elsewhere, requested]);

  if (error) return html`<div class="panel empty-state" role="alert">${error.message}</div>`;
  if (!graph) return html`<div class="panel empty-state">Loading the map…</div>`;
  if (!tree) return html`<div class="knowledge"><${NoMap} graph=${graph} onStarted=${reload} /></div>`;

  const found = query.trim() ? searchMap(tree, query) : null;
  const matches = found && keep ? new Set([...found].filter(keep)) : found;
  const closed = collapsed ?? initial();
  // While searching, the branches holding a match open up.
  const opened = matches ? new Set([...matches].flatMap((key) => ancestors(tree, key))) : new Set();
  const effective = new Set([...closed].filter((key) => !opened.has(key)));
  const layout = layoutMap(tree, { collapsed: effective, hidden: fmea ? new Set() : hidden, keep, effects: (key) => effectsOf(tree, index, key) });
  const badges = changeBadges(tree, graph.change_counts, effective);
  const failureModes = kept ? [...kept].filter((key) => roleOf(tree, key) === "failure_mode").length : 0;
  const drafts = fmea && viewing == null && releases.data ? new Map(Object.entries(releases.data.draft.markers)) : new Map();

  const select = (key) => {
    // A box chosen elsewhere (a link chip) may sit in a closed branch: open the way to it.
    if (tree.own.has(key)) setCollapsed(new Set([...closed].filter((k) => !ancestors(tree, key).includes(k))));
    const path = fmea ? fmeaPath(department.code, process.code, { box: key, release: route.params.release }) : knowledgePath(department.code, process.code, key);
    navigate(path, { replace: true });
  };
  const toggle = (key, open) => {
    const next = new Set(closed);
    if (open) next.delete(key);
    else next.add(key);
    setCollapsed(next);
  };

  return html`
    <div class="map-tools">
      <label class="search-box map-tools__search">
        <${SearchIcon} />
        <input type="search" aria-label="Find in map" placeholder="Find anything in the map…" value=${query} onInput=${(e) => setQuery(e.currentTarget.value)} />
      </label>
      ${fmea
        ? html`<span class="muted">${failureModes ? "Only failure modes and the steps leading to them are shown." : "No failure modes in this map yet."}</span>`
        : html`<${KindChips} graph=${graph} tree=${tree} hidden=${hidden} setHidden=${setHidden} />`}
      ${matches && html`<span class="muted" aria-live="polite">${matches.size === 1 ? "1 match" : `${matches.size} matches`}</span>`}
      <span class="map-tools__end">
        <button type="button" class="btn" onClick=${() => setCollapsed(new Set())}>Expand all</button>
        <button type="button" class="btn" onClick=${() => setCollapsed(allCollapsed(tree))}>Collapse</button>
      </span>
    </div>
    ${releases.data &&
    html`<${ReleaseBar}
      document="FMEA"
      list=${releases.data}
      viewing=${viewing}
      onView=${(release) => navigate(fmeaPath(department.code, process.code, { box: route.params.box, release }))}
      onReview=${() => setReviewing(true)}
    />`}
    <div class="knowledge">
      <${MapCanvas}
        graph=${graph}
        tree=${tree}
        index=${index}
        layout=${layout}
        selected=${selected}
        onSelect=${select}
        onToggle=${toggle}
        badges=${badges}
        matches=${matches}
        drafts=${drafts}
        label=${fmea ? `FMEA of ${process.name}` : `Knowledge map of ${process.name}`}
      />
      <${BoxPanel}
        graph=${graph}
        tree=${tree}
        index=${index}
        boxKey=${requested && graph.boxes.some((b) => b.key === requested) ? requested : tree.root}
        department=${department}
        lookup=${lookup}
        onSelect=${select}
        canEdit=${(box) => viewing == null && canIn(boot.me, "knowledge.edit", box.section_id)}
        linkOf=${fmea ? (key) => fmeaPath(department.code, process.code, { box: key, release: route.params.release }) : null}
        draft=${drafts.get(requested && graph.boxes.some((b) => b.key === requested) ? requested : tree.root) ?? null}
        onEdit=${(boxKey) => setEditing({ boxKey })}
        onAdd=${(parentKey) => setEditing({ parentKey })}
      />
    </div>
    ${fmea && html`<${FmeaSheet} graph=${graph} tree=${tree} index=${index} department=${department} today=${boot.today} version=${releases.data ? versionText(releases.data, viewing) : "current draft"} />`}
    ${reviewing &&
    releases.data &&
    html`<${ReleaseDialog}
      process=${process}
      department=${department}
      list=${releases.data}
      onClose=${() => setReviewing(false)}
      onStale=${releases.reload}
      onReleased=${() => {
        setReviewing(false);
        dataChanged();
      }}
    />`}
    ${editing &&
    html`<${BoxEditorDrawer}
      graph=${graph}
      tree=${tree}
      boot=${boot}
      lookup=${lookup}
      boxKey=${editing.boxKey ?? null}
      parentKey=${editing.parentKey ?? null}
      onClose=${() => setEditing(null)}
      onDone=${(key) => {
        setEditing(null);
        reload();
        select(key);
      }}
    />`}
  `;
}

function MapView({ boot, lookup, route }) {
  const view = VIEWS.find((v) => v.name === route.name) ?? VIEWS[0];
  const page = useProcessPage(boot, route, "knowledge.view", (department, process, same) =>
    viewPath(view.name, route.params, department, process, same),
  );
  const [settingsOpen, setSettingsOpen] = useState(false);
  useTitle(page.process ? `${view.label} · ${page.process.name}` : "Process knowledge");
  if (page.status !== "ready") return html`<${ProcessPageMessage} page=${page} module="Process knowledge" />`;
  const settingsButton = html`<button type="button" class="btn" onClick=${() => setSettingsOpen(true)}><${SlidersIcon} />Kinds & links</button>`;
  return html`
    <section class="page" aria-label="Process knowledge">
      <${MapSettingsDialog} open=${settingsOpen} onClose=${() => setSettingsOpen(false)} onChanged=${dataChanged} />
      <${ProcessHeader} page=${page} module="Process knowledge" actions=${settingsButton}>
        <${ViewSwitch} department=${page.department} process=${page.process} current=${view.name} />
      <//>
      <${ProcessMap} key=${`${view.name}:${page.process.id}`} view=${view.name} page=${page} route=${route} boot=${boot} lookup=${lookup} />
    </section>
  `;
}

/** Process knowledge, read three ways: the knowledge map, the FMEA, the control plan (CPL). */
export function KnowledgeView({ boot, lookup, route }) {
  if (route.name === "cpl") return html`<${ControlPlanView} boot=${boot} lookup=${lookup} route=${route} />`;
  return html`<${MapView} boot=${boot} lookup=${lookup} route=${route} />`;
}
