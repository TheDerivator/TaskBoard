/** Process changes of one process: the list or the timeline (Gantt) of its tests and changes. */
import { PlusIcon, SearchIcon } from "../../components/icons.js";
import { ProcessHeader, ProcessPageMessage, useProcessPage } from "../../components/process-header.js";
import { useApi, useTitle } from "../../hooks.js";
import { canIn } from "../../lib/lookup.js";
import { mapTree, subtree } from "../../lib/maplayout.js";
import { changePath, changesPath, TIMELINE_RANGES } from "../../lib/routes.js";
import { href, navigate } from "../../router.js";
import { html, useMemo, useState } from "../../ui.js";
import { NewChangeDrawer } from "./change.js";
import { ChangeList } from "./list.js";
import { ChangeTimeline } from "./timeline.js";

const DESCRIPTIONS = {
  list: "A period with an end date is a test. A period without one is a permanent process change.",
  timeline: "Tests and process changes that went into operation in the last months, plus what is planned.",
};

// The search survives switching between list and timeline during a visit (like the task filters).
let rememberedSearch = "";

function PageSwitch({ department, process, view }) {
  const link = (name, label) => html`
    <a href=${href(changesPath(department.code, process.code, { view: name }))} aria-current=${view === name ? "page" : undefined}>${label}</a>
  `;
  return html`<nav class="segmented process-bar__end" aria-label="View">${link("list", "List")}${link("timeline", "Timeline")}</nav>`;
}

const EM_SPACE = String.fromCodePoint(0x2003); // indents the options of a <select>

/** The map's boxes in reading order, indented, for the timeline's "Map box" filter. */
function boxOptions(tree, processName) {
  const options = [];
  const walk = (key, depth) => {
    if (depth > 0) options.push({ key, label: `${EM_SPACE.repeat(depth - 1)}${tree.byKey.get(key).name}` });
    for (const child of tree.children.get(key) ?? []) walk(child, depth + 1);
  };
  if (tree.root) walk(tree.root, 0);
  return [{ key: "", label: `Whole process (${processName})` }, ...options];
}

/** Case-insensitive search on the key, title, what and why (the list mockup: "Search what or why"). */
export function matchesSearch(change, query) {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return true;
  return [change.key, change.title, change.what_md, change.why_md].some((text) => text.toLocaleLowerCase().includes(needle));
}

function Changes({ page, route, boot, lookup }) {
  const { department, process } = page;
  const view = route.params.view ?? "list";
  const { data, error, loading } = useApi("/changes", { process: process.code });
  const [query, setQuery] = useState(rememberedSearch);
  const [creating, setCreating] = useState(false);
  const canCreate = canIn(boot.me, "change.edit", process.section_id);
  // The timeline can be narrowed to a branch of the process's map (DESIGN Module 2, rule 8).
  const canMap = view === "timeline" && canIn(boot.me, "knowledge.view", process.section_id);
  const map = useApi(canMap ? `/processes/${encodeURIComponent(process.code)}/map` : null);
  const tree = useMemo(() => (map.data?.root_key ? mapTree(map.data) : null), [map.data]);
  const box = tree && route.params.box && tree.byKey.has(route.params.box) ? route.params.box : null;
  const branch = box ? subtree(tree, box) : null;
  const pathOf = (change, tab = "details") => changePath(department.code, process.code, change.key, tab);
  const shown =
    view === "list"
      ? (data ?? []).filter((c) => matchesSearch(c, query))
      : (data ?? []).filter((c) => !branch || c.box_keys.some((k) => branch.has(k)));
  const search = (value) => {
    rememberedSearch = value;
    setQuery(value);
  };

  return html`
    <section class="page" aria-label="Process changes">
      <${ProcessHeader}
        page=${page}
        module="Process changes"
        description=${DESCRIPTIONS[view]}
        actions=${canCreate && html`<button type="button" class="btn btn--primary" onClick=${() => setCreating(true)}><${PlusIcon} />New change</button>`}
      >
        ${view === "list" &&
        html`<label class="search-box process-bar__search">
          <${SearchIcon} />
          <input type="search" aria-label="Search changes" placeholder="Search what or why…" value=${query} onInput=${(e) => search(e.currentTarget.value)} />
        </label>`}
        ${tree &&
        html`<label class="process-bar__department">
          <span class="visually-hidden">Map box</span>
          <select class="select process-bar__box" onChange=${(e) => navigate(changesPath(department.code, process.code, { view, range: route.params.range, box: e.currentTarget.value || null }))}>
            ${boxOptions(tree, process.name).map((o) => html`<option key=${o.key} value=${o.key} selected=${o.key === (box ?? "")}>${o.label}</option>`)}
          </select>
        </label>`}
        ${view === "timeline" &&
        html`<label class="process-bar__department">
          <span class="visually-hidden">Range</span>
          <select class="select" onChange=${(e) => navigate(changesPath(department.code, process.code, { view, range: Number(e.currentTarget.value), box: route.params.box }))}>
            ${TIMELINE_RANGES.map((r) => html`<option key=${r} value=${r} selected=${r === route.params.range}>Last ${r} months</option>`)}
          </select>
        </label>`}
        <${PageSwitch} department=${department} process=${process} view=${view} />
      <//>
      ${error && html`<div class="panel empty-state" role="alert">${error.message}</div>`}
      ${!error && loading && !data && html`<div class="panel empty-state">Loading process changes…</div>`}
      ${data &&
      (data.length === 0
        ? html`<div class="panel empty-state">No process changes for ${process.name} yet.</div>`
        : view === "timeline"
          ? html`<${ChangeTimeline} changes=${shown} today=${boot.today} months=${route.params.range ?? 6} pathOf=${pathOf} />`
          : shown.length === 0
            ? html`<div class="panel empty-state">No change matches this search.</div>`
            : html`<${ChangeList} changes=${shown} today=${boot.today} lookup=${lookup} pathOf=${pathOf} />`)}
      ${creating && html`<${NewChangeDrawer} processId=${process.id} onClose=${() => setCreating(false)} />`}
    </section>
  `;
}

export function ChangesView({ boot, lookup, route }) {
  const view = route.params.view ?? "list";
  const page = useProcessPage(boot, route, "change.view", (department, process, same) =>
    changesPath(department.code, process.code, same ? { ...route.params, view } : { view }),
  );
  useTitle(page.process ? `Process changes · ${page.process.name}` : "Process changes");
  if (page.status !== "ready") return html`<${ProcessPageMessage} page=${page} module="Process changes" />`;
  return html`<${Changes} key=${page.process.id} page=${page} route=${route} boot=${boot} lookup=${lookup} />`;
}
