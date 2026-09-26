/** Administration › Organization: departments and their sections (the scopes for access rights). */
import { api } from "../../api.js";
import { TrashIcon } from "../../components/icons.js";
import { showError, showToast } from "../../components/toasts.js";
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

async function call(request, message) {
  try {
    await request();
    await refreshBoot();
    if (message) showToast(message);
  } catch (err) {
    showError(err);
    await refreshBoot();
  }
}

function Department({ department }) {
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
    </section>
  `;
}

export function OrganizationTab({ boot }) {
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
      <div><h2>Organization</h2><p>Departments and sections. Every task and person belongs to a section; access rights are granted per department or section.</p></div>
    </div>
    <div class="panel">
      ${boot.departments.map((d) => html`<${Department} key=${d.id} department=${d} />`)}
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
