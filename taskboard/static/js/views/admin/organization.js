/** Administration › Organization: departments, their sections (the scopes for access rights) and processes. */
import { api } from "../../api.js";
import { TrashIcon } from "../../components/icons.js";
import { showError, showToast } from "../../components/toasts.js";
import { useApi } from "../../hooks.js";
import { refreshBoot } from "../../store.js";
import { html, useEffect, useState } from "../../ui.js";

/** A text field that saves when it loses focus (or on Enter) if its value changed. */
function InlineInput({ value, label, onSave, className = "input" }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const commit = () => {
    const trimmed = text.trim();
    if (trimmed && trimmed !== value) onSave(trimmed);
    else setText(value);
  };
  return html`<input
    class=${className}
    aria-label=${label}
    value=${text}
    onInput=${(e) => setText(e.currentTarget.value)}
    onBlur=${commit}
    onKeyDown=${(e) => e.key === "Enter" && e.currentTarget.blur()}
  />`;
}

async function call(request, message, after = null) {
  try {
    await request();
    if (message) showToast(message);
  } catch (err) {
    showError(err);
  }
  after?.();
  await refreshBoot();
}

/** Any section of the organization (a process may be owned by a section of another department). */
function SectionSelect({ departments, value, label, onChange }) {
  return html`
    <select class="select org-select" aria-label=${label} value=${value} onChange=${(e) => onChange(Number(e.currentTarget.value))}>
      ${departments.map(
        (d) => html`
          <optgroup key=${d.id} label=${d.code}>
            ${d.sections.map((s) => html`<option key=${s.id} value=${s.id} selected=${s.id === value}>${d.code} · ${s.name}</option>`)}
          </optgroup>
        `,
      )}
    </select>
  `;
}

/** A department's processes. The code prefixes change keys (CC-31), so it is fixed once created. */
function Processes({ department, departments, processes, onChanged }) {
  const [form, setForm] = useState({ code: "", name: "", section_id: department.sections[0]?.id ?? null });
  const add = (event) => {
    event.preventDefault();
    call(() => api.post("/admin/processes", form), `Process ${form.code.toUpperCase()} added.`, onChanged);
    setForm({ ...form, code: "", name: "" });
  };
  const update = (process, change) => call(() => api.patch(`/admin/processes/${process.id}`, change), null, onChanged);
  return html`
    <div class="org-processes" aria-label=${`Processes of ${department.code}`} role="group">
      <span class="org-subhead">Processes</span>
      ${processes.map(
        (p) => html`
          <div key=${p.id} class="org-line">
            <code class="org-code" title="The code is part of change keys and links; it cannot change">${p.code}</code>
            <${InlineInput} label=${`Name of process ${p.code}`} value=${p.name} onSave=${(name) => update(p, { name })} />
            <${SectionSelect} departments=${departments} value=${p.section_id} label=${`Owning section of ${p.code}`} onChange=${(section_id) => update(p, { section_id })} />
            <button
              type="button"
              class="icon-btn"
              aria-label=${`Delete process ${p.code}`}
              title="Delete (only when nothing uses it)"
              onClick=${() => window.confirm(`Delete the process ${p.name}?`) && call(() => api.delete(`/admin/processes/${p.id}`), "Process deleted.", onChanged)}
            ><${TrashIcon} /></button>
          </div>
        `,
      )}
      ${department.sections.length > 0 &&
      html`
        <form class="org-line" onSubmit=${add}>
          <input class="input input--code" aria-label=${`New process code in ${department.code}`} placeholder="Code" required pattern="[A-Za-z0-9]{1,10}" value=${form.code} onInput=${(e) => setForm({ ...form, code: e.currentTarget.value })} />
          <input class="input" aria-label=${`New process name in ${department.code}`} placeholder="New process…" required value=${form.name} onInput=${(e) => setForm({ ...form, name: e.currentTarget.value })} />
          <${SectionSelect} departments=${[department]} value=${form.section_id} label=${`Owning section of the new process in ${department.code}`} onChange=${(section_id) => setForm({ ...form, section_id })} />
          <button type="submit" class="btn">Add process</button>
        </form>
      `}
    </div>
  `;
}

function Department({ department, departments, processes, onProcessesChanged }) {
  const [newSection, setNewSection] = useState("");
  const base = `/admin/departments/${department.id}`;
  const addSection = (event) => {
    event.preventDefault();
    if (!newSection.trim()) return;
    call(() => api.post("/admin/sections", { department_id: department.id, name: newSection }), `Section ${newSection} added.`);
    setNewSection("");
  };
  return html`
    <section class="org-department" aria-label=${`Department ${department.code}`}>
      <div class="org-line">
        <${InlineInput} className="input input--code" label=${`Code of ${department.code}`} value=${department.code} onSave=${(code) => call(() => api.patch(base, { code }))} />
        <${InlineInput} label=${`Name of ${department.code}`} value=${department.name} onSave=${(name) => call(() => api.patch(base, { name }))} />
        <button
          type="button"
          class="icon-btn"
          aria-label=${`Delete department ${department.code}`}
          title="Delete (only when it has no sections)"
          onClick=${() => window.confirm(`Delete the department ${department.code}?`) && call(() => api.delete(base), "Department deleted.")}
        ><${TrashIcon} /></button>
      </div>
      <div class="org-sections">
        ${department.sections.map(
          (s) => html`
            <div key=${s.id} class="org-line">
              <${InlineInput} label=${`Section ${s.name}`} value=${s.name} onSave=${(name) => call(() => api.patch(`/admin/sections/${s.id}`, { name }))} />
              <button
                type="button"
                class="icon-btn"
                aria-label=${`Delete section ${s.name}`}
                title="Delete (only when nothing uses it)"
                onClick=${() => window.confirm(`Delete the section ${s.name}?`) && call(() => api.delete(`/admin/sections/${s.id}`), "Section deleted.")}
              ><${TrashIcon} /></button>
            </div>
          `,
        )}
        <form class="org-line" onSubmit=${addSection}>
          <input class="input" aria-label=${`New section in ${department.code}`} placeholder="New section…" value=${newSection} onInput=${(e) => setNewSection(e.currentTarget.value)} />
          <button type="submit" class="btn">Add section</button>
        </form>
      </div>
      <${Processes} department=${department} departments=${departments} processes=${processes} onChanged=${onProcessesChanged} />
    </section>
  `;
}

export function OrganizationTab({ boot }) {
  const processes = useApi("/admin/processes");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const add = (event) => {
    event.preventDefault();
    call(() => api.post("/admin/departments", { code, name }), `Department ${code.toUpperCase()} added.`);
    setCode("");
    setName("");
  };
  return html`
    <div class="section-head">
      <div>
        <h2>Organization</h2>
        <p>
          Departments, sections and processes. Every task and person belongs to a section; every process is owned by a
          section, which decides who may see and edit its changes and its map. Access rights are granted per department or section.
        </p>
      </div>
    </div>
    <div class="panel">
      ${boot.departments.map((d) => {
        const own = (processes.data ?? []).filter((p) => p.department_id === d.id);
        return html`<${Department} key=${d.id} department=${d} departments=${boot.departments} processes=${own} onProcessesChanged=${processes.reload} />`;
      })}
      <form class="org-department" onSubmit=${add} aria-label="New department">
        <div class="org-line">
          <input class="input input--code" aria-label="New department code" placeholder="Code" required value=${code} onInput=${(e) => setCode(e.currentTarget.value)} />
          <input class="input" aria-label="New department name" placeholder="Name" required value=${name} onInput=${(e) => setName(e.currentTarget.value)} />
          <button type="submit" class="btn">Add department</button>
        </div>
      </form>
    </div>
  `;
}
