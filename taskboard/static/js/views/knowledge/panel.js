/** The selected box's side panel: what it is, where it sits, its description and key facts, its
 * typed links both ways, controls, external links, the process changes in its branch, related
 * tasks, and its history (revisions). */
import { CopyLinkButton } from "../../components/copy-link.js";
import { Dialog } from "../../components/dialog.js";
import { EditIcon, ExternalIcon } from "../../components/icons.js";
import { useApi } from "../../hooks.js";
import { formatDate, shortName } from "../../lib/format.js";
import { ancestors, typedLinks } from "../../lib/maplayout.js";
import { formatDay } from "../../lib/periods.js";
import { changesPath, knowledgePath } from "../../lib/routes.js";
import { href } from "../../router.js";
import { html, useState } from "../../ui.js";
import { StatePill } from "../changes/list.js";
import { KindIcon, kindClass } from "./map.js";

const LINK_KINDS = {
  dashboard: ["DB", "Dashboard"],
  graph: ["GR", "Graph"],
  calibration: ["CAL", "Calibration diagram"],
  document: ["DOC", "Document"],
  website: ["WEB", "Website"],
};

function host(url) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** Where a box sits: "Continuous casting › Mould › Mould level control". */
export function boxPath(tree, box, { processName, departmentCode, lookup }) {
  if (box.key === tree.root) return departmentCode;
  if (box.process_id == null) return `Defect catalogue · ${departmentCode}`;
  if (!tree.own.has(box.key)) return `In ${lookup.processes.get(box.process_id)?.name ?? "another process"}`;
  return ancestors(tree, box.key)
    .map((key) => (key === tree.root ? processName : tree.byKey.get(key).name))
    .join(" › ");
}

/** A dashboard, graph, diagram or document on another server, opening in a new tab. */
export function ExternalLinkCard({ link }) {
  const [abbr, kind] = LINK_KINDS[link.kind] ?? ["WEB", "Website"];
  return html`
    <a class="ext-link" href=${link.href} target="_blank" rel="noopener noreferrer">
      <span class="ext-link__abbr" aria-hidden="true">${abbr}</span>
      <span class="ext-link__text">
        <span class="ext-link__label">${link.label}</span>
        <span class="ext-link__meta">${kind} · ${host(link.url)}</span>
      </span>
      <${ExternalIcon} /><span class="visually-hidden">(opens in a new tab)</span>
    </a>
  `;
}

function ExternalLinks({ links }) {
  if (!links.length) return null;
  return html`
    <section class="box-panel__section">
      <h3>Dashboards, diagrams & documents</h3>
      ${links.map((link) => html`<${ExternalLinkCard} key=${link.href + link.label} link=${link} />`)}
    </section>
  `;
}

/** Process changes in the box's branch and tasks about it (only what the reader may see). */
export function Related({ boxKey, tree, department, processCode, hasBranch }) {
  const { data } = useApi(`/boxes/${encodeURIComponent(boxKey)}/related`);
  if (!data) return null;
  const name = (key) => (key === tree.root ? "the process" : tree.byKey.get(key)?.name ?? key);
  return html`
    ${data.changes.length > 0 &&
    html`<section class="box-panel__section">
      <div class="box-panel__section-head">
        <h3>Process changes ${hasBranch ? "in this branch" : "here"}</h3>
        <a href=${href(changesPath(department.code, processCode, { view: "timeline", box: boxKey }))}>Show on timeline</a>
      </div>
      ${data.changes.map(
        (c) => html`
          <a key=${c.key} class="related-change" href=${href(c.url.replace(/^\/+/, ""))}>
            <span class="related-change__head"><span class="related-change__key">${c.key}</span><span class="related-change__title">${c.title}</span></span>
            <span class="related-change__state">
              <${StatePill} state=${{ state: c.state, date: c.state_date }} />
              <span class="related-change__where">${c.box_key === boxKey ? "attached here" : `on ${name(c.box_key)}`}</span>
            </span>
          </a>
        `,
      )}
    </section>`}
    ${data.tasks.length > 0 &&
    html`<section class="box-panel__section">
      <h3>Related in Team Tasks</h3>
      <div class="rel-chips">
        ${data.tasks.map(
          (t) => html`<a key=${t.key} class="task-ref" href=${href(t.url.replace(/^\/+/, ""))}><span class="task-ref__key">${t.ref}</span>${t.title}</a>`,
        )}
      </div>
    </section>`}
  `;
}

function HistoryDialog({ boxKey, name, onClose }) {
  const { data, error } = useApi(boxKey == null ? null : `/boxes/${encodeURIComponent(boxKey)}/history`);
  return html`
    <${Dialog} open=${boxKey != null} title=${`History of ${name}`} onClose=${onClose} wide>
      <div class="dialog__body">
        ${error && html`<p role="alert">${error.message}</p>`}
        ${!data && !error && html`<p class="muted">Loading…</p>`}
        ${data &&
        html`<ol class="revision-list">
          ${data.map(
            (r) => html`
              <li key=${`${r.object_type}${r.object_id}:${r.rev}`}>
                <span>${r.summary}</span>
                <span class="revision-list__meta">
                  ${r.author?.display_name ?? "System"} · ${formatDate(r.created_at, { withTime: true })} · ${r.object_type} revision ${r.rev}
                </span>
              </li>
            `,
          )}
        </ol>`}
      </div>
    <//>
  `;
}

/**
 * @param {{graph: object, tree: object, index: object, boxKey: string, department: object,
 *   lookup: object, onSelect: (key: string) => void}} props
 */
export function BoxPanel({ graph, tree, index, boxKey, department, lookup, onSelect, canEdit = () => false, onEdit = null, onAdd = null, draft = null, linkOf = null }) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const box = tree.byKey.get(boxKey);
  if (!box) return html`<aside class="box-panel" aria-label="Selected box"><p class="box-panel__body muted">Select a box.</p></aside>`;
  const kind = tree.kinds.get(box.kind);
  const isRoot = box.key === tree.root;
  // Boxes of other processes are edited in their own map.
  const editable = onEdit && canEdit(box) && (tree.own.has(box.key) || box.process_id == null);
  const title = isRoot ? graph.process.name : box.name;
  const owner = box.owner_person_id != null ? lookup.people.get(box.owner_person_id) : null;
  const controls = graph.controls.filter((c) => c.box_key === box.key).sort((a, b) => a.position - b.position);
  const links = [...box.external_links, ...controls.flatMap((c) => c.external_links)];
  const fields = (kind?.field_schema ?? []).filter((f) => box.fields[f.key] != null && box.fields[f.key] !== "");
  const groups = typedLinks(index, box.key);
  const meta = [
    box.step_no,
    owner && `Owner ${shortName(owner.name)}`,
    box.reviewed_at && `last reviewed ${formatDay(box.reviewed_at, { year: true })}`,
  ].filter(Boolean);
  return html`
    <aside class="box-panel" aria-label="Selected box">
      <div class="box-panel__head">
        <div class="box-panel__top">
          <span class=${`kind-pill ${kindClass(tree, box.key)}`}>${isRoot ? "Process" : kind?.name}</span>
          <span class="box-panel__tools">
            <${CopyLinkButton} path=${linkOf ? linkOf(box.key) : knowledgePath(department.code, graph.process.code, box.key)} label="Copy link to this box" />
            ${editable && html`<button type="button" class="btn btn--small-tool" onClick=${() => onEdit(box.key)}><${EditIcon} />Edit</button>`}
          </span>
        </div>
        <span class="box-panel__path">${boxPath(tree, box, { processName: graph.process.name, departmentCode: department.code, lookup })}</span>
        <h2 class="box-panel__title">${title}</h2>
        <span class="box-panel__meta">
          ${meta.length > 0 && html`<span>${meta.join(" · ")}</span><span aria-hidden="true">·</span>`}
          <button type="button" class="link-button" onClick=${() => setHistoryOpen(true)}>History</button>
        </span>
        ${draft && html`<span class="draft-pill"><span class="draft-pill__dot" aria-hidden="true"></span>${draft}</span>`}
      </div>
      <div class="box-panel__body">
        ${box.main_url &&
        html`<a class="main-url" href=${box.main_url} target="_blank" rel="noopener noreferrer">
          <${ExternalIcon} size=${18} />
          <span class="main-url__text">
            <span class="main-url__label">Open website</span>
            <span class="main-url__address">${box.main_url.replace(/^https?:\/\//, "")}</span>
          </span>
        </a>`}
        ${box.body_html
          ? html`<div class="md" dangerouslySetInnerHTML=${{ __html: box.body_html }}></div>`
          : html`<p class="box-panel__empty">Nothing written here yet.</p>`}
        ${box.facts.length > 0 &&
        html`<section class="box-panel__section">
          <h3>Key facts</h3>
          <dl class="facts">${box.facts.map(([k, v], i) => html`<dt key=${`k${i}`}>${k}</dt><dd key=${`v${i}`}>${v}</dd>`)}</dl>
        </section>`}
        ${fields.length > 0 &&
        html`<section class="box-panel__section">
          <h3>Details</h3>
          <dl class="facts">${fields.map((f) => html`<dt key=${`k${f.key}`}>${f.label || f.key}</dt><dd key=${`v${f.key}`}>${String(box.fields[f.key])}</dd>`)}</dl>
        </section>`}
        ${groups.map(
          (g) => html`
            <section key=${`${g.type}:${g.direction}`} class="box-panel__section">
              <h3>${g.label}</h3>
              <div class="rel-chips">
                ${g.items.map((item) => {
                  const target = tree.byKey.get(item.key);
                  return html`
                    <button key=${item.link.id} type="button" class=${`rel-chip ${kindClass(tree, item.key)}`} title=${item.link.note_md || undefined} onClick=${() => onSelect(item.key)}>
                      <${KindIcon} tree=${tree} boxKey=${item.key} />${item.key === tree.root ? graph.process.name : target?.name ?? item.key}
                    </button>
                  `;
                })}
              </div>
            </section>
          `,
        )}
        ${controls.length > 0 &&
        html`<section class="box-panel__section">
          <h3>Controls</h3>
          ${controls.map(
            (c) => html`
              <div key=${c.id} class="control-line">
                <span class=${`control-tag control-tag--${c.kind}`}>${c.kind === "prevent" ? "Prevent" : "Detect"}</span><span>${c.text}</span>
              </div>
            `,
          )}
        </section>`}
        <${ExternalLinks} links=${links} />
        ${editable && tree.own.has(box.key) && html`<button type="button" class="btn btn--dashed" onClick=${() => onAdd(box.key)}>+ Add a box under this</button>`}
        <${Related}
          key=${box.key}
          boxKey=${box.key}
          tree=${tree}
          department=${department}
          processCode=${graph.process.code}
          hasBranch=${(tree.children.get(box.key) ?? []).length > 0}
        />
      </div>
      <${HistoryDialog} boxKey=${historyOpen ? box.key : null} name=${title} onClose=${() => setHistoryOpen(false)} />
    </aside>
  `;
}
