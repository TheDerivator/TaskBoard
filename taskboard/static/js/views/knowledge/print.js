/** What "Export PDF" prints: the FMEA and the control plan as tables (the browser saves them as
 * PDF, A16). Hidden on screen; css/print.css shows only the sheet when printing. */
import { causesOf } from "../../lib/controlplan.js";
import { ancestors, readingOrder, roleOf } from "../../lib/maplayout.js";
import { formatDay } from "../../lib/periods.js";
import { html } from "../../ui.js";

function ControlList({ controls, kind }) {
  const shown = controls.filter((c) => c.kind === kind);
  if (!shown.length) return html`<span class="print-sheet__none">—</span>`;
  return html`
    <ul class="print-sheet__list">
      ${shown.map(
        (c) => html`
          <li key=${c.id}>
            ${c.text}
            ${c.external_links.map((link) => html`<span key=${link.href} class="print-sheet__link">${link.label}: ${link.href}</span>`)}
          </li>
        `,
      )}
    </ul>
  `;
}

function Names({ names }) {
  if (!names.length) return html`<span class="print-sheet__none">—</span>`;
  return html`<ul class="print-sheet__list">${names.map((n, i) => html`<li key=${i}>${n}</li>`)}</ul>`;
}

function SheetHead({ title, subtitle, version, today }) {
  return html`
    <header class="print-sheet__head">
      <h1>${title}</h1>
      <p>${subtitle} · ${version}, printed ${formatDay(today, { year: true })}</p>
    </header>
  `;
}

/** The FMEA as a table: one row per failure mode, in the map's reading order. */
export function FmeaSheet({ graph, tree, index, department, today, version = "current draft" }) {
  const leadsTo = new Set(graph.link_types.filter((t) => t.role === "leads_to").map((t) => t.key));
  const name = (key) => (key === tree.root ? graph.process.name : tree.byKey.get(key)?.name ?? key);
  const rows = readingOrder(tree).filter((key) => roleOf(tree, key) === "failure_mode");
  return html`
    <div class="print-sheet">
      <${SheetHead} title=${`FMEA · ${graph.process.name}`} subtitle=${department.name} version=${version} today=${today} />
      ${rows.length === 0
        ? html`<p>No failure modes in this map yet.</p>`
        : html`<table class="print-table">
            <thead>
              <tr><th scope="col">Where</th><th scope="col">Failure mode</th><th scope="col">Leads to</th><th scope="col">Caused by</th><th scope="col">Prevent</th><th scope="col">Detect</th></tr>
            </thead>
            <tbody>
              ${rows.map((key) => {
                const controls = graph.controls.filter((c) => c.box_key === key).sort((a, b) => a.position - b.position);
                const effects = (index.outgoing.get(key) ?? []).filter((l) => leadsTo.has(l.type)).map((l) => name(l.to_key));
                const causes = (index.incoming.get(key) ?? []).filter((l) => leadsTo.has(l.type)).map((l) => name(l.from_key));
                return html`
                  <tr key=${key}>
                    <td>${ancestors(tree, key).slice(1).map(name).join(" › ") || graph.process.name}</td>
                    <th scope="row">${tree.byKey.get(key).name}</th>
                    <td><${Names} names=${effects} /></td>
                    <td><${Names} names=${causes} /></td>
                    <td><${ControlList} controls=${controls} kind="prevent" /></td>
                    <td><${ControlList} controls=${controls} kind="detect" /></td>
                  </tr>
                `;
              })}
            </tbody>
          </table>`}
    </div>
  `;
}

/** The control plan as tables: per defect of the list, its causes, how, and their controls. */
export function ControlPlanSheet({ index, groups, department, process, processOrder, today, version = "current draft" }) {
  const name = (key) => index.byKey.get(key)?.name ?? key;
  return html`
    <div class="print-sheet">
      <${SheetHead} title=${`Control plan · ${department.name}`} subtitle=${process ? process.name : "All processes"} version=${version} today=${today} />
      ${groups.flatMap((group) =>
        group.defects.map((d) => {
          const causes = causesOf(index, d.key, { process: process?.id ?? null, processOrder });
          return html`
            <section key=${d.key} class="print-sheet__defect">
              <h2>${d.name} <span class="print-sheet__group">${group.name}</span></h2>
              ${causes.length === 0
                ? html`<p>No known causes.</p>`
                : html`<table class="print-table">
                    <thead>
                      <tr><th scope="col">Where</th><th scope="col">Cause</th><th scope="col">How it leads to it</th><th scope="col">Prevent</th><th scope="col">Detect</th></tr>
                    </thead>
                    <tbody>
                      ${causes.map(
                        (c) => html`
                          <tr key=${c.key}>
                            <td>${c.path.map(name).join(" › ")}</td>
                            <th scope="row">${c.box.name}</th>
                            <td>${c.link.note_html ? html`<div class="md" dangerouslySetInnerHTML=${{ __html: c.link.note_html }}></div>` : html`<span class="print-sheet__none">—</span>`}</td>
                            <td><${ControlList} controls=${index.controls.get(c.key) ?? []} kind="prevent" /></td>
                            <td><${ControlList} controls=${index.controls.get(c.key) ?? []} kind="detect" /></td>
                          </tr>
                        `,
                      )}
                    </tbody>
                  </table>`}
            </section>
          `;
        }),
      )}
    </div>
  `;
}
