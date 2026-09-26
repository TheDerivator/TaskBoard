/** Fields of the task form: lifecycle picker, department/section, lead, helpers, placements. */
import { canIn } from "../lib/lookup.js";
import { html, useState } from "../ui.js";
import { Avatar, statusLabel } from "./badges.js";
import { ChevronIcon, CloseIcon } from "./icons.js";
import { PersonPicker } from "./person-picker.js";

const LIFECYCLE = ["idea", "started", "done", "archived"];

function Check() {
  return html`<svg class="check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5L20 7" /></svg>`;
}

export function FieldLabel({ children, id }) {
  return html`<span class="field__label" id=${id}>${children}</span>`;
}

/** Four-way lifecycle switch; earlier stages than the current one get a check mark. */
export function LifecyclePicker({ value, onChange, readOnly }) {
  const current = LIFECYCLE.indexOf(value);
  return html`
    <fieldset class="field" style=${{ border: 0, margin: 0, padding: 0 }}>
      <legend class="field__label" style=${{ paddingBottom: "8px" }}>Lifecycle</legend>
      <div class=${`lifecycle${readOnly ? " lifecycle--readonly" : ""}`}>
        ${LIFECYCLE.map(
          (status, index) => html`
            <button
              key=${status}
              type="button"
              class=${`status-${status}`}
              aria-pressed=${value === status ? "true" : "false"}
              disabled=${readOnly && value !== status}
              onClick=${() => !readOnly && onChange(status)}
            >
              ${index < current && status !== "archived" && html`<${Check} />`}${statusLabel(status)}
            </button>
          `,
        )}
      </div>
    </fieldset>
  `;
}

function orgMeta(lookup, sectionId) {
  const section = lookup.sections.get(sectionId);
  const department = section && lookup.departments.get(section.department_id);
  return department ? `${department.code} · ${section.name}` : "";
}

/** Department then section. Only sections the user may edit are offered (plus the current one). */
export function OrgFields({ sectionId, onChange, boot, lookup, readOnly }) {
  const me = boot.me;
  const current = lookup.sections.get(sectionId);
  if (readOnly) {
    const department = current && lookup.departments.get(current.department_id);
    return html`
      <div class="grid-2">
        <div class="field"><${FieldLabel}>Department<//><span>${department?.code ?? "—"}</span></div>
        <div class="field"><${FieldLabel}>Section<//><span>${current?.name ?? "—"}</span></div>
      </div>
    `;
  }
  const allowed = (s) => s.id === sectionId || canIn(me, "task.edit", s.id);
  const departments = boot.departments.filter((d) => d.sections.some(allowed));
  const departmentId = current?.department_id ?? departments[0]?.id;
  const sections = (lookup.departments.get(departmentId)?.sections ?? []).filter(allowed);

  const pickDepartment = (id) => {
    const first = lookup.departments.get(id)?.sections.find(allowed);
    if (first) onChange(first.id);
  };

  return html`
    <div class="grid-2">
      <label class="field">
        <${FieldLabel}>Department<//>
        <select class="select" onChange=${(e) => pickDepartment(Number(e.currentTarget.value))}>
          ${departments.map((d) => html`<option key=${d.id} value=${d.id} selected=${d.id === departmentId}>${d.code}</option>`)}
        </select>
      </label>
      <label class="field">
        <${FieldLabel}>Section<//>
        <select class="select" onChange=${(e) => onChange(Number(e.currentTarget.value))}>
          ${sections.map((s) => html`<option key=${s.id} value=${s.id} selected=${s.id === sectionId}>${s.name}</option>`)}
        </select>
      </label>
    </div>
  `;
}

/** "Lead · exactly one": a button showing the lead that opens a person picker. */
export function LeadField({ leadId, onChange, boot, lookup, readOnly }) {
  const [open, setOpen] = useState(false);
  const lead = lookup.people.get(leadId);
  const choices = boot.people.filter((p) => p.active || p.id === leadId);
  return html`
    <div class="field">
      <${FieldLabel} id="lead-label">Lead · exactly one<//>
      <div class="picker-anchor">
        <button
          type="button"
          class="person-button"
          aria-labelledby="lead-label lead-name"
          aria-haspopup=${readOnly ? undefined : "dialog"}
          disabled=${readOnly}
          onClick=${() => setOpen(!open)}
        >
          <${Avatar} person=${lead} />
          <span class="person-button__text">
            <span class="person-button__name" id="lead-name">${lead?.name ?? "Choose a lead"}</span>
            <span class="person-button__meta">${lead ? orgMeta(lookup, lead.section_id) : ""}</span>
          </span>
          ${!readOnly && html`<span style=${{ transform: "rotate(90deg)", display: "grid" }}><${ChevronIcon} size=${16} /></span>`}
        </button>
        ${open &&
        html`<${PersonPicker}
          people=${choices}
          lookup=${lookup}
          label="Choose the lead"
          onPick=${(p) => {
            onChange(p.id);
            setOpen(false);
          }}
          onClose=${() => setOpen(false)}
        />`}
      </div>
    </div>
  `;
}

/** "Also working on it": removable person chips plus "+ Add person". */
export function HelpersField({ helperIds, leadId, onChange, boot, lookup, readOnly }) {
  const [open, setOpen] = useState(false);
  const candidates = boot.people.filter((p) => p.active && p.id !== leadId && !helperIds.includes(p.id));
  return html`
    <div class="field">
      <${FieldLabel}>Also working on it<//>
      <div class="person-chips">
        ${helperIds.length === 0 && readOnly && html`<span class="muted">Nobody else.</span>`}
        ${helperIds.map((id) => {
          const person = lookup.people.get(id);
          return html`
            <span key=${id} class=${`person-chip${readOnly ? " person-chip--readonly" : ""}`}>
              <${Avatar} person=${person} />${person?.name ?? "?"}
              ${!readOnly &&
              html`<button type="button" aria-label=${`Remove ${person?.name ?? "person"}`} onClick=${() => onChange(helperIds.filter((h) => h !== id))}>
                <${CloseIcon} size=${14} />
              </button>`}
            </span>
          `;
        })}
        ${!readOnly &&
        html`
          <span class="picker-anchor">
            <button type="button" class="dashed-button" onClick=${() => setOpen(!open)} disabled=${candidates.length === 0}>+ Add person</button>
            ${open &&
            html`<${PersonPicker}
              people=${candidates}
              lookup=${lookup}
              label="Add a person"
              onPick=${(p) => {
                onChange([...helperIds, p.id]);
                setOpen(false);
              }}
              onClose=${() => setOpen(false)}
            />`}
          </span>
        `}
      </div>
    </div>
  `;
}

/** "Projects · one place per project": rows with Move / Remove, and "+ Add to another project". */
export function PlacementsField({ placements, lookup, readOnly, onAdd, onMove, onRemove }) {
  return html`
    <div class="field">
      <${FieldLabel}>Projects · one place per project<//>
      <div class="placements">
        ${placements.length === 0 && html`<span class="muted">Not in any project.</span>`}
        ${placements.map((p) => {
          const project = lookup.projects.get(p.project_id);
          const nodes = project?.nodes ?? [];
          const chain = p.node_id == null ? [] : pathNodes(nodes, p.node_id);
          return html`
            <div key=${p.project_id} class="placement" style=${{ "--project-color": project?.color }}>
              <span class="project-dot"></span>
              <div class="placement__text">
                <span class="placement__project">${project?.name ?? "Unknown project"}</span>
                <span class="placement__path">
                  ${chain.length === 0
                    ? "Top level"
                    : chain.map(
                        (n, i) => html`${i > 0 && " › "}<span class="mono">${n.number}</span> ${n.name}`,
                      )}
                </span>
              </div>
              ${!readOnly &&
              html`
                <button type="button" class="link-button" onClick=${() => onMove(p.project_id)}>Move</button>
                <button type="button" class="icon-btn" aria-label=${`Remove from ${project?.name ?? "project"}`} onClick=${() => onRemove(p.project_id)}>
                  <${CloseIcon} size=${14} />
                </button>
              `}
            </div>
          `;
        })}
        ${!readOnly &&
        html`<button type="button" class="dashed-button dashed-button--square" onClick=${onAdd}>+ Add to another project</button>`}
      </div>
    </div>
  `;
}

/** The chain of nodes from the top-level section down to `nodeId` (bootstrap nodes have parent ids). */
function pathNodes(nodes, nodeId) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const chain = [];
  for (let node = byId.get(nodeId); node; node = byId.get(node.parent_id)) chain.unshift(node);
  return chain;
}
