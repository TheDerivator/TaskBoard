/** The Knowledge / FMEA / CPL switch of Process knowledge, and each view's path for a process. */
import { cplPath, fmeaPath, knowledgePath } from "../../lib/routes.js";
import { href } from "../../router.js";
import { html } from "../../ui.js";

export const VIEWS = [
  { name: "knowledge", label: "Knowledge", hint: "The full knowledge map" },
  { name: "fmea", label: "FMEA", hint: "Failure modes and the steps they sit in" },
  { name: "cpl", label: "CPL", hint: "Control plan: from defect to controls" },
];

/**
 * The path of a view for a process (null: the control plan's "All processes"); `same` keeps the
 * selection when the process stays.
 */
export function viewPath(view, params, department, process, same) {
  const code = process?.code ?? null;
  if (view === "fmea") return fmeaPath(department.code, code, same ? params : {});
  if (view === "cpl") {
    return cplPath(department.code, same ? params.defect : null, same ? params.cause : null, {
      process: code,
      release: same ? params.release : null,
    });
  }
  return knowledgePath(department.code, code, same ? params.box : null);
}

export function ViewSwitch({ department, process, current }) {
  return html`
    <nav class="segmented process-bar__end" aria-label="View">
      ${VIEWS.map(
        (v) => html`
          <a key=${v.name} href=${href(viewPath(v.name, {}, department, process, false))} title=${v.hint} aria-current=${current === v.name ? "page" : undefined}>
            ${v.label}
          </a>
        `,
      )}
    </nav>
  `;
}
