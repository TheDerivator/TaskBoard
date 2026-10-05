/** The release bar of the FMEA and the control plan (the FmeaMap and DefectView mockups) and the
 * "Review & release" dialog (the Release mockup, without approver or notification: D-081). */
import { api, ApiError } from "../../api.js";
import { Dialog } from "../../components/dialog.js";
import { FailureModeIcon, PrintIcon } from "../../components/icons.js";
import { showToast } from "../../components/toasts.js";
import { formatDate } from "../../lib/format.js";
import { documentsText, draftText, releaseDay, releasedText, releaseLabel, versionOptions } from "../../lib/releases.js";
import { html, useState } from "../../ui.js";

const VERBS = { added: "Added", changed: "Changed", removed: "Removed" };

/** The version an old view draws, or the latest release while showing the current draft. */
export function shownRelease(list, viewing) {
  return viewing == null ? list.releases[0] ?? null : list.releases.find((r) => r.number === viewing) ?? null;
}

/** "Current draft" or "v3, released 12 Sep 2026": what a printed sheet says it shows. */
export function versionText(list, viewing) {
  const release = viewing == null ? null : shownRelease(list, viewing);
  return release ? `${release.label}, released ${releaseDay(release.released_at)}` : "current draft";
}

/**
 * @param {{document: string, list: object, viewing: ?number, onView: (label: ?string) => void,
 *   onReview: () => void}} props  `document` is "FMEA" or "CPL"; `list` is GET .../releases
 */
export function ReleaseBar({ document, list, viewing, onView, onReview }) {
  const current = viewing == null;
  const shown = shownRelease(list, viewing);
  const next = releaseLabel((list.releases[0]?.number ?? 0) + 1);
  const changes = list.draft.entries.length;
  return html`
    <div class="release-bar" role="group" aria-label="Released versions">
      <span class="release-bar__info">
        <span class="release-bar__version">${document} ${shown ? shown.label : "draft"}</span>
        <span class="release-bar__text">${shown ? releasedText(shown) : "Not released yet"}</span>
        ${current
          ? html`<span class=${`draft-pill${changes ? "" : " draft-pill--none"}`}><span class="draft-pill__dot" aria-hidden="true"></span>${draftText(list.draft)}</span>`
          : html`<span class="draft-pill draft-pill--old">Earlier version${shown?.note ? `: ${shown.note}` : ""}</span>`}
      </span>
      <span class="release-bar__actions">
        <label class="release-bar__picker">
          Viewing
          <select class="select" value=${current ? "" : releaseLabel(viewing)} onChange=${(e) => onView(e.currentTarget.value || null)}>
            ${versionOptions(list.releases).map((o) => html`<option key=${o.value} value=${o.value}>${o.label}</option>`)}
          </select>
        </label>
        <button type="button" class="btn" onClick=${() => window.print()}><${PrintIcon} />Export PDF</button>
        ${current && list.can_release && changes > 0 && html`<button type="button" class="btn btn--primary" onClick=${onReview}>Review & release ${next}</button>`}
      </span>
    </div>
  `;
}

function revisionText(line) {
  if (line.verb === "added") return `revision ${line.after}`;
  if (line.after == null) return `deleted after revision ${line.before}`;
  return `revision ${line.before} → ${line.after}`;
}

/** "Review & release vN": what changed since the last release, a note, and release at once. */
export function ReleaseDialog({ process, department, list, onClose, onReleased, onStale }) {
  const { draft } = list;
  const base = list.releases[0] ?? null;
  const next = releaseLabel((base?.number ?? 0) + 1);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const release = await api.post(`/processes/${encodeURIComponent(process.code)}/releases`, { note, base: draft.base });
      showToast(`FMEA and control plan ${release.label} released.`);
      onReleased(release);
    } catch (failure) {
      setError(failure.message);
      if (failure instanceof ApiError && failure.status === 409) onStale();
    } finally {
      setBusy(false);
    }
  };
  return html`
    <${Dialog} open=${true} title=${`Release FMEA & control plan ${next}`} onClose=${onClose} large>
      <form class="release-dialog" onSubmit=${submit}>
        <p class="muted">${process.name} · ${department.code}</p>
        <p>A release freezes the current revision of every box, link and control the FMEA and CPL show. Both documents get the same number.</p>
        <dl class="release-tiles">
          <div>
            <dt>Last release</dt>
            <dd class="release-tiles__value">${base ? base.label : "None"}</dd>
            <dd>${base ? releaseDay(base.released_at) : "the first release"}</dd>
          </div>
          <div>
            <dt>Changes in scope</dt>
            <dd class="release-tiles__value">${draft.entries.length}</dd>
            <dd>${documentsText(draft)}</dd>
          </div>
          <div>
            <dt>Outside scope</dt>
            <dd class="release-tiles__value">${draft.outside_scope}</dd>
            <dd>knowledge edits, kept per box</dd>
          </div>
        </dl>
        <section class="release-changes" aria-label=${base ? `Changes since ${base.label}` : "What the first release holds"}>
          <h3>${base ? `Changes since ${base.label}` : "What the first release holds"}</h3>
          <ul>
            ${draft.entries.map(
              (entry) => html`
                <li key=${entry.box_key} class="release-change">
                  <div class="release-change__main">
                    <span class="release-change__head">
                      <strong>${entry.box_name}</strong>
                      <span class=${`verb-pill verb-pill--${entry.verb}`}>${VERBS[entry.verb]}</span>
                    </span>
                    ${entry.lines.map(
                      (line, i) => html`
                        <span key=${i} class="release-change__what">${line.summary}</span>
                        <span key=${`m${i}`} class="release-change__who">
                          ${[line.author?.display_name, line.at && formatDate(line.at), revisionText(line)].filter(Boolean).join(" · ")}
                        </span>
                      `,
                    )}
                    ${entry.warnings.map((w) => html`<span key=${w} class="release-change__warning"><${FailureModeIcon} />${w}</span>`)}
                  </div>
                  <span class="release-change__docs">${entry.documents.map((d) => html`<span key=${d} class="doc-chip">${d.toUpperCase()}</span>`)}</span>
                </li>
              `,
            )}
          </ul>
        </section>
        <label class="field">
          <span class="field__label">Release note</span>
          <textarea class="input release-dialog__note" rows="3" maxlength="4000" value=${note} onInput=${(e) => setNote(e.currentTarget.value)}></textarea>
        </label>
        ${error && html`<div class="form-error" role="alert">${error}</div>`}
        <div class="dialog__actions">
          <button type="button" class="btn" onClick=${onClose}>Cancel</button>
          <button type="submit" class="btn btn--primary" disabled=${busy || draft.entries.length === 0}>Release ${next}</button>
        </div>
      </form>
    <//>
  `;
}
