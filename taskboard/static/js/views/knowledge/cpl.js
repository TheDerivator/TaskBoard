/** The control plan (the DefectView mockup): a department's defects in their groups; for the one
 * chosen, where it comes from (defect → where → how) and how each cause is controlled. For all of
 * the department's processes or one. Defects are edited here, their causes in the knowledge map. */
import { api } from "../../api.js";
import { CopyLinkButton } from "../../components/copy-link.js";
import { Dialog } from "../../components/dialog.js";
import { EditIcon, PlusIcon, PrintIcon, SearchIcon } from "../../components/icons.js";
import { ProcessHeader, ProcessPageMessage, useDepartmentPage } from "../../components/process-header.js";
import { showError, showToast } from "../../components/toasts.js";
import { useApi, useTitle } from "../../hooks.js";
import { causeDiagram, causesOf, defectGroups, groupOf, inSentence, planIndex } from "../../lib/controlplan.js";
import { canIn } from "../../lib/lookup.js";
import { mapTree } from "../../lib/maplayout.js";
import { parseRelease } from "../../lib/releases.js";
import { cplPath, knowledgePath } from "../../lib/routes.js";
import { href, navigate } from "../../router.js";
import { dataChanged } from "../../store.js";
import { html, useMemo, useState } from "../../ui.js";
import { BoxEditorDrawer } from "./editor.js";
import { ExternalLinkCard, Related } from "./panel.js";
import { ControlPlanSheet } from "./print.js";
import { ReleaseBar, ReleaseDialog, versionText } from "./release.js";
import { ViewSwitch } from "./switch.js";

const px = (node) => `left: ${node.x}px; top: ${node.y}px; width: ${node.width}px; height: ${node.height}px;`;

function DefectList({ groups, selected, pathOf, query, setQuery, onNew }) {
  return html`
    <nav class="cpl-defects" aria-label="Defects">
      <h2>Defects</h2>
      <label class="search-box">
        <${SearchIcon} />
        <input type="search" aria-label="Find a defect" placeholder="Find a defect…" value=${query} onInput=${(e) => setQuery(e.currentTarget.value)} />
      </label>
      ${groups.map(
        (g) => html`
          <div key=${g.name} class="cpl-defects__group">
            <h3>${g.name}</h3>
            <ul>
              ${g.defects.map(
                (d) => html`
                  <li key=${d.key}>
                    <a class="cpl-defect" href=${href(pathOf(d.key))} aria-current=${d.key === selected ? "page" : undefined}>
                      <span class="cpl-defect__name">${d.name}</span>
                      <span class="cpl-defect__count" title="Known causes"><span class="visually-hidden">, known causes: </span>${d.count}</span>
                    </a>
                  </li>
                `,
              )}
            </ul>
          </div>
        `,
      )}
      ${groups.length === 0 && html`<p class="muted">${query.trim() ? "No defect matches." : "No defects here yet."}</p>`}
      ${onNew && html`<button type="button" class="btn btn--dashed" onClick=${onNew}><${PlusIcon} />New defect</button>`}
    </nav>
  `;
}

/** Tasks and process changes that refer to the defect. */
function DefectRelated({ defectKey }) {
  const { data } = useApi(`/boxes/${encodeURIComponent(defectKey)}/related`);
  if (!data || (data.tasks.length === 0 && data.changes.length === 0)) return null;
  return html`
    <div class="cpl-related">
      <span class="cpl-related__label">Related</span>
      ${data.tasks.map((t) => html`<a key=${t.key} class="task-ref" href=${href(t.url.replace(/^\/+/, ""))}><span class="task-ref__key">${t.ref}</span>${t.title}</a>`)}
      ${data.changes.map((c) => html`<a key=${c.key} class="task-ref" href=${href(c.url.replace(/^\/+/, ""))}><span class="task-ref__key">${c.key}</span>${c.title}</a>`)}
    </div>
  `;
}

/** "How it arises": the defect, where its causes sit, and the causes (links to pick one). */
function CauseDiagram({ defect, causes, selected, index, lookup, process, pathOf }) {
  const diagram = causeDiagram(causes);
  const several = new Set(causes.map((c) => c.process)).size > 1;
  const name = (key) => index.byKey.get(key)?.name ?? key;
  const kindClass = (box) => `kind--${index.kinds.get(box.kind)?.style ?? "grey"}`;
  const nodes = new Map(diagram.causes.map((n) => [n.key, n]));
  return html`
    <section class="cpl-diagram" aria-label="How it arises">
      <div class="cpl-diagram__labels" aria-hidden="true"><span>Defect</span><span>Where</span><span>How (failure mode)</span></div>
      <div class="cpl-diagram__canvas" style=${`width: ${diagram.width}px; height: ${diagram.height}px;`}>
        ${diagram.lines.map((l, i) => html`<span key=${`l${i}`} class="map__line" style=${px(l)} aria-hidden="true"></span>`)}
        <div class="cpl-node cpl-node--defect" style=${px(diagram.defect)}><span class="cpl-node__label">${defect.name}</span></div>
        ${diagram.wheres.map((w) => {
          const process = lookup.processes.get(index.byKey.get(w.key)?.process_id);
          return html`
            <div key=${w.key} class="cpl-node cpl-node--where" style=${px(w)}>
              <span class="cpl-node__label">${name(w.key)}</span>
              ${several && process && html`<span class="cpl-node__sub">${process.name}</span>`}
            </div>
            ${causes
              .filter((c) => c.where === w.key)
              .map(
                (c) => html`
                  <a key=${c.key} class=${`cpl-node cpl-node--cause ${kindClass(c.box)}`} style=${px(nodes.get(c.key))} href=${href(pathOf(defect.key, c.key))} aria-current=${c.key === selected ? "true" : undefined}>
                    <span class="cpl-node__label">${c.box.name}</span>
                    ${c.sub && html`<span class="cpl-node__sub">${name(c.sub)}</span>`}
                  </a>
                `,
              )}
          `;
        })}
      </div>
      ${causes.length === 0 &&
      html`<p class="cpl-diagram__empty muted">No known causes${process ? ` in ${process.name}` : ""} yet. A failure mode that "leads to" this defect in a knowledge map shows up here.</p>`}
    </section>
  `;
}

/** "How to control it": the chosen cause, how it leads to the defect, its controls and their links. */
function CauseDetail({ cause, defect, index, lookup, boot, link, editable = true }) {
  const kind = index.kinds.get(cause.box.kind);
  const process = lookup.processes.get(cause.process);
  const department = process ? lookup.departments.get(process.department_id) : null;
  const mapPath = process && department ? knowledgePath(department.code, process.code, cause.key) : null;
  const controls = index.controls.get(cause.key) ?? [];
  const how = cause.link.note_html || cause.box.body_html;
  const canEdit = editable && canIn(boot.me, "knowledge.edit", cause.box.section_id);
  return html`
    <aside class="box-panel cpl-cause" aria-label="How to control it">
      <div class="box-panel__head">
        <div class="box-panel__top">
          <span class=${`kind-pill kind--${kind?.style ?? "grey"}`}>${kind?.name ?? "Cause"}</span>
          <span class="box-panel__tools">
            ${mapPath && html`<a href=${href(mapPath)}>Show in knowledge map</a>`}
            <${CopyLinkButton} path=${link} label="Copy link to this cause" />
          </span>
        </div>
        <span class="box-panel__path">${cause.path.map((k) => index.byKey.get(k)?.name ?? k).join(" › ")}</span>
        <h2 class="box-panel__title">${cause.box.name}</h2>
      </div>
      <div class="box-panel__body">
        <section class="box-panel__section">
          <h3>How it leads to ${inSentence(defect.name)}</h3>
          ${how ? html`<div class="md" dangerouslySetInnerHTML=${{ __html: how }}></div>` : html`<p class="box-panel__empty">Not written down yet.</p>`}
        </section>
        <section class="box-panel__section">
          <h3>How it is controlled</h3>
          ${controls.map(
            (c) => html`
              <div key=${c.id} class="control-card">
                <div class="control-line">
                  <span class=${`control-tag control-tag--${c.kind}`}>${c.kind === "prevent" ? "Prevent" : "Detect"}</span><span>${c.text}</span>
                </div>
                ${c.external_links.map((l) => html`<${ExternalLinkCard} key=${l.href + l.label} link=${l} />`)}
              </div>
            `,
          )}
          ${controls.length === 0 &&
          html`<div class="box-panel__empty">
            No controls documented for this cause yet.
            ${canEdit && mapPath && html` <a href=${href(mapPath)}>Add one in the knowledge map</a>`}
          </div>`}
        </section>
        ${cause.box.external_links.length > 0 &&
        html`<section class="box-panel__section">
          <h3>Dashboards, diagrams & documents</h3>
          ${cause.box.external_links.map((l) => html`<${ExternalLinkCard} key=${l.href + l.label} link=${l} />`)}
        </section>`}
        ${department &&
        html`<${Related}
          boxKey=${cause.key}
          tree=${{ root: null, byKey: index.byKey }}
          department=${department}
          processCode=${process.code}
          hasBranch=${[...index.byKey.values()].some((b) => b.parent_key === cause.key)}
        />`}
      </div>
    </aside>
  `;
}

/** "New defect": name, group, and (when you may add to several) the section that owns it. */
function NewDefectDialog({ plan, department, lookup, groupNames, onClose, onCreated }) {
  const kind = plan.kinds.find((k) => k.role === "defect");
  const hasGroup = (kind?.field_schema ?? []).some((f) => f.key === "group");
  const counts = new Map();
  for (const b of plan.boxes) if (b.process_id == null) counts.set(b.section_id, (counts.get(b.section_id) ?? 0) + 1);
  const usual = [...plan.defect_sections].sort((a, b) => (counts.get(b) ?? 0) - (counts.get(a) ?? 0))[0];
  const [name, setName] = useState("");
  const [group, setGroup] = useState("");
  const [section, setSection] = useState(usual);
  const [busy, setBusy] = useState(false);
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const fields = hasGroup && group.trim() ? { group: group.trim() } : {};
      const created = await api.post("/boxes", { kind: kind.key, name, section_id: Number(section), fields });
      showToast(`${created.box.name} added.`);
      onCreated(created.box.key);
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  };
  return html`
    <${Dialog} open=${true} title="New defect" onClose=${onClose}>
      <form class="stack" onSubmit=${submit}>
        <label class="field">
          <span class="field__label">Name</span>
          <input class="input" required maxlength="300" value=${name} onInput=${(e) => setName(e.currentTarget.value)} />
        </label>
        ${hasGroup &&
        html`<label class="field">
          <span class="field__label">Group</span>
          <input class="input" list="defect-groups" value=${group} placeholder="Surface, Cracks, …" onInput=${(e) => setGroup(e.currentTarget.value)} />
          <datalist id="defect-groups">${groupNames.map((g) => html`<option key=${g} value=${g}></option>`)}</datalist>
        </label>`}
        ${plan.defect_sections.length > 1 &&
        html`<label class="field">
          <span class="field__label">Section that owns it</span>
          <select class="select" value=${section} onChange=${(e) => setSection(Number(e.currentTarget.value))}>
            ${plan.defect_sections.map((id) => html`<option key=${id} value=${id}>${department.code} › ${lookup.sections.get(id)?.name ?? id}</option>`)}
          </select>
        </label>`}
        <div class="dialog__actions">
          <button type="button" class="btn" onClick=${onClose}>Cancel</button>
          <button type="submit" class="btn btn--primary" disabled=${busy || !name.trim()}>Add defect</button>
        </div>
      </form>
    <//>
  `;
}

function ControlPlan({ page, route, boot, lookup }) {
  const { department, process } = page;
  // One process's control plan has released versions (all processes together have none, A18).
  const viewing = process ? parseRelease(route.params.release) : null;
  const params = viewing ? { department: department.code, process: process.code, release: viewing } : { department: department.code };
  const { data: plan, error, reload } = useApi("/control-plan", params);
  const releases = useApi(process ? `/processes/${encodeURIComponent(process.code)}/releases` : null);
  const [reviewing, setReviewing] = useState(false);
  const index = useMemo(() => (plan ? planIndex(plan) : null), [plan]);
  // The defect editor works on the department's catalogue as if it were a map without a tree.
  const catalogue = useMemo(
    () => plan && { ...plan, process: { id: null, code: null, name: department.name, section_id: plan.defect_sections[0] ?? null }, root_key: null, change_counts: {} },
    [plan],
  );
  const processOrder = useMemo(() => new Map(boot.processes.map((p, i) => [p.id, i])), [boot.processes]);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(false);
  const pathOf = (defect, cause = null, release = route.params.release) => cplPath(department.code, defect, cause, { process: process?.code ?? null, release });

  if (error) return html`<div class="panel empty-state" role="alert">${error.message}</div>`;
  if (!plan) return html`<div class="panel empty-state">Loading the control plan…</div>`;

  const requested = route.params.defect ? String(route.params.defect).toLowerCase() : null;
  const filter = process?.id ?? null;
  const groups = defectGroups(index, { process: filter, query });
  const first = groups[0]?.defects[0]?.key ?? null;
  const defectKey = requested ?? first;
  const defect = defectKey && index.byKey.get(defectKey)?.process_id == null ? index.byKey.get(defectKey) : null;
  const causes = defect ? causesOf(index, defect.key, { process: filter, processOrder }) : [];
  const cause = causes.find((c) => c.key === route.params.cause) ?? causes[0] ?? null;
  const canEditDefect = defect && viewing == null && canIn(boot.me, "knowledge.edit", defect.section_id);
  const bar = process && releases.data;
  const groupNames = [...new Set(index.defects.map(groupOf))];

  const actions = html`
    <span class="view-head__actions">
      ${defect && html`<${CopyLinkButton} path=${cplPath(department.code, defect.key, null, { process: process?.code ?? null, release: route.params.release })} label="Copy link to this defect" />`}
      ${canEditDefect && html`<button type="button" class="btn" onClick=${() => setEditing(true)}><${EditIcon} />Edit defect</button>`}
      ${!bar && html`<button type="button" class="btn" onClick=${() => window.print()}><${PrintIcon} />Export PDF</button>`}
    </span>
  `;
  return html`
    <div class="cpl">
      <${DefectList}
        groups=${groups}
        selected=${defect?.key}
        pathOf=${(key) => pathOf(key)}
        query=${query}
        setQuery=${setQuery}
        onNew=${plan.defect_sections.length > 0 && viewing == null ? () => setCreating(true) : null}
      />
      <div class="cpl-main">
        <${ProcessHeader}
          page=${page}
          module="Process knowledge"
          crumb="Control plan"
          title=${defect?.name ?? "Control plan"}
          badge=${defect && html`<span class="group-pill">${groupOf(defect)}</span>`}
          actions=${actions}
          allProcesses
        >
          <${ViewSwitch} department=${department} process=${process} current="cpl" />
        <//>
        ${bar &&
        html`<${ReleaseBar}
          document="CPL"
          list=${releases.data}
          viewing=${viewing}
          onView=${(release) => navigate(pathOf(route.params.defect, route.params.cause, release))}
          onReview=${() => setReviewing(true)}
        />`}
        ${requested && !defect && html`<div class="panel empty-state" role="alert">This defect does not exist, or you may not see it.</div>`}
        ${!requested && !defect && html`<div class="panel empty-state">${department.name} has no defects yet.</div>`}
        ${defect &&
        html`
          <div class="cpl-defect-info">
            ${defect.body_html ? html`<div class="md cpl-description" dangerouslySetInnerHTML=${{ __html: defect.body_html }}></div>` : html`<p class="muted">No description yet.</p>`}
            <${DefectRelated} key=${defect.key} defectKey=${defect.key} />
          </div>
          <div class="cpl-body">
            <${CauseDiagram} defect=${defect} causes=${causes} selected=${cause?.key} index=${index} lookup=${lookup} process=${process} pathOf=${pathOf} />
            ${cause && html`<${CauseDetail} key=${cause.key} cause=${cause} defect=${defect} index=${index} lookup=${lookup} boot=${boot} link=${pathOf(defect.key, cause.key)} editable=${viewing == null} />`}
          </div>
        `}
      </div>
    </div>
    <${ControlPlanSheet} index=${index} groups=${defectGroups(index, { process: filter, caused: filter != null })} department=${department} process=${process} processOrder=${processOrder} today=${boot.today} version=${bar ? versionText(releases.data, viewing) : "current draft"} />
    ${reviewing &&
    bar &&
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
    ${creating &&
    html`<${NewDefectDialog}
      plan=${plan}
      department=${department}
      lookup=${lookup}
      groupNames=${groupNames}
      onClose=${() => setCreating(false)}
      onCreated=${(key) => {
        setCreating(false);
        reload();
        navigate(pathOf(key));
      }}
    />`}
    ${editing &&
    defect &&
    html`<${BoxEditorDrawer}
      graph=${catalogue}
      tree=${mapTree(catalogue)}
      boot=${boot}
      lookup=${lookup}
      boxKey=${defect.key}
      place=${`the ${department.code} defect catalogue`}
      onClose=${() => setEditing(false)}
      onDone=${(key) => {
        setEditing(false);
        reload();
        if (!key) navigate(pathOf(null));
      }}
    />`}
  `;
}

export function ControlPlanView({ boot, lookup, route }) {
  // Another process keeps the defect shown (it belongs to the department); another department not.
  const sameDepartment = (department) => String(route.params.department ?? "").toLowerCase() === department.code.toLowerCase();
  const page = useDepartmentPage(boot, route, "knowledge.view", (department, process, same) =>
    cplPath(department.code, same || sameDepartment(department) ? route.params.defect : null, same ? route.params.cause : null, {
      process: process?.code ?? null,
      release: same ? route.params.release : null,
    }),
  );
  useTitle(page.department ? `Control plan · ${page.department.name}` : "Control plan");
  if (page.status !== "ready") return html`<${ProcessPageMessage} page=${page} module="Process knowledge" />`;
  return html`
    <section class="page page--cpl" aria-label="Process knowledge">
      <${ControlPlan} key=${page.department.id} page=${page} route=${route} boot=${boot} lookup=${lookup} />
    </section>
  `;
}
