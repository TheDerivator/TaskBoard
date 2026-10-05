/** Header shared by Process changes and Process knowledge: department, process tabs, page switch. */
import { defaultProcess, findProcessRoute, moduleProcesses, processDepartments } from "../lib/processes.js";
import { routePath } from "../lib/routes.js";
import { readPref, writePref } from "../prefs.js";
import { href, navigate } from "../router.js";
import { html, useEffect, useMemo } from "../ui.js";

// The process chosen last, shared by both modules (DESIGN open question 4), per browser.
const PREF = "process";

/** Both page hooks: `wholeDepartment` makes the process optional (the department suffices). */
function useModulePage(boot, route, permission, pathFor, wholeDepartment) {
  const processes = useMemo(() => moduleProcesses(boot.processes, boot.me, permission), [boot, permission]);
  const departments = useMemo(() => processDepartments(boot.departments, processes), [boot.departments, processes]);
  const found = findProcessRoute(departments, processes, route.params);
  const enough = (f) => (wholeDepartment ? f.department : f.process);

  let target = null;
  if (found && !enough(found)) {
    const choice = defaultProcess(processes, {
      remembered: readPref(PREF, null),
      departmentId: wholeDepartment ? null : found.department?.id ?? null,
    });
    if (choice) target = pathFor(departments.find((d) => d.id === choice.department_id), wholeDepartment ? null : choice, false);
  } else if (found) {
    const canonical = pathFor(found.department, found.process, true);
    if (canonical !== routePath(route)) target = canonical;
  }
  const shown = target ? null : found?.process?.code;
  useEffect(() => {
    if (target) navigate(target, { replace: true });
    else if (shown) writePref(PREF, shown);
  }, [target, shown]);

  const base = { departments, processes, pathFor };
  if (processes.length === 0) return { ...base, status: "none" };
  if (!found) return { ...base, status: "missing" };
  if (target || !enough(found)) return { ...base, status: "moving" };
  return { ...base, status: "ready", department: found.department, process: found.process };
}

/**
 * Which process a module page shows. When the URL names none, the page moves (replacing the
 * history entry) to the process used last; a URL spelled differently from the organization
 * ("/changes/stl/lm") is corrected the same way.
 *
 * @param {object} boot  the bootstrap document
 * @param {{name: string, params: object}} route
 * @param {string} permission  "change.view" or "knowledge.view": which processes this module shows
 * @param {(department: object, process: object, same: boolean) => string} pathFor  the module's
 *   path for a process; `same` is true for the process already shown (keep the page's options)
 * @returns {{status: "ready" | "none" | "missing" | "moving", department?: object, process?: object,
 *   departments: object[], processes: object[], pathFor: Function}}
 */
export function useProcessPage(boot, route, permission, pathFor) {
  return useModulePage(boot, route, permission, pathFor, false);
}

/**
 * Like useProcessPage, for a page about a whole department that may narrow to one process (the
 * control plan's "All processes"): the URL names the department, the process is optional. With
 * no department named, the page moves to the department of the process used last.
 *
 * @param {(department: object, process: ?object, same: boolean) => string} pathFor
 * @returns {{status: "ready" | "none" | "missing" | "moving", department?: object, process?: ?object,
 *   departments: object[], processes: object[], pathFor: Function}}
 */
export function useDepartmentPage(boot, route, permission, pathFor) {
  return useModulePage(boot, route, permission, pathFor, true);
}

/**
 * @param {{
 *   page: object,                 // from useProcessPage or useDepartmentPage, status "ready"
 *   module: string,               // "Process changes" or "Process knowledge"
 *   title?: string,               // defaults to the process name
 *   crumb?: string,               // after the department in the crumb ("Control plan")
 *   badge?: any,                  // next to the title (a defect's group)
 *   description?: string,
 *   actions?: any,                // buttons on the right of the title
 *   children?: any,               // more controls in the bar (search, page switch)
 *   allProcesses?: boolean,       // a first tab for the whole department (process null)
 * }} props
 */
export function ProcessHeader({ page, module, title, crumb = null, badge = null, description, actions = null, children = null, allProcesses = false }) {
  const { department, process, departments, processes, pathFor } = page;
  const inDepartment = processes.filter((p) => p.department_id === department.id);
  const switchDepartment = (event) => {
    const chosen = departments.find((d) => d.id === Number(event.currentTarget.value));
    const first = allProcesses ? null : defaultProcess(processes, { remembered: readPref(PREF, null), departmentId: chosen.id });
    navigate(pathFor(chosen, first, false));
  };
  return html`
    <header class="view-head">
      <div class="view-head__text">
        <span class="view-head__crumb">${module} › ${department.code}${crumb ? ` › ${crumb}` : ""}</span>
        <div class="view-head__title">
          <h1>${title ?? process?.name ?? department.name}</h1>
          ${badge}
        </div>
        ${description && html`<p>${description}</p>`}
      </div>
      ${actions}
    </header>
    <div class="process-bar">
      <label class="process-bar__department">
        <span>Department</span>
        <select class="select" onChange=${switchDepartment}>
          ${departments.map((d) => html`<option key=${d.id} value=${d.id} selected=${d.id === department.id}>${d.code}</option>`)}
        </select>
      </label>
      <nav class="segmented" aria-label="Process">
        ${allProcesses &&
        html`<a href=${href(pathFor(department, null, process == null))} aria-current=${process == null ? "page" : undefined}>All processes</a>`}
        ${inDepartment.map(
          (p) => html`
            <a key=${p.id} href=${href(pathFor(department, p, p.id === process?.id))} aria-current=${p.id === process?.id ? "page" : undefined}>
              ${p.name}
            </a>
          `,
        )}
      </nav>
      ${children}
    </div>
  `;
}

/** What a module page shows instead of a process: none exist yet, or the URL names an unknown one. */
export function ProcessPageMessage({ page, module }) {
  if (page.status === "moving") return html`<section class="page" aria-busy="true"></section>`;
  const none = page.status === "none";
  return html`
    <section class="center-page">
      <div class="center-card">
        <h1>${none ? `No processes in ${module} yet` : "This process does not exist"}</h1>
        <p class="muted">
          ${none
            ? "An administrator adds processes under Administration › Organization; each one belongs to a section."
            : "The link names a department or process that does not exist, or that you may not see."}
        </p>
      </div>
    </section>
  `;
}
