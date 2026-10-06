/** Releases of the FMEA and control plan (pure): versions in links ("v3"), the release bar's
 * wording, the version picker. */
import { actorName, plural } from "./format.js";
import { formatDay } from "./periods.js";

/** "v3" (or "3") in a link → 3; anything else → null. */
export function parseRelease(text) {
  const match = /^v?(\d{1,6})$/i.exec(String(text ?? "").trim());
  return match ? Number(match[1]) : null;
}

export const releaseLabel = (number) => `v${number}`;

/** The day a release was made, as people read it: "12 Sep 2026" (in the browser's time zone). */
export function releaseDay(datetime) {
  const at = new Date(datetime);
  const iso = `${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, "0")}-${String(at.getDate()).padStart(2, "0")}`;
  return formatDay(iso, { year: true });
}

/** "Draft: 4 changes since v3", "No changes since v3", "Not released yet · 7 changes". */
export function draftText(draft) {
  const count = draft.entries.length;
  if (draft.base == null) return count ? `Not released yet · ${plural(count, "change")}` : "Not released yet";
  return count ? `Draft: ${plural(count, "change")} since ${releaseLabel(draft.base)}` : `No changes since ${releaseLabel(draft.base)}`;
}

/** "Released 12 Sep 2026 · Anna Claes" */
export function releasedText(release) {
  const by = release.released_by ? ` · ${actorName(release.released_by)}` : "";
  return `Released ${releaseDay(release.released_at)}${by}`;
}

/** The version picker: the current draft first, then the releases, newest first. */
export function versionOptions(releases) {
  return [{ value: "", label: "Current draft" }, ...releases.map((r) => ({ value: r.label, label: `${r.label} · ${releaseDay(r.released_at)}` }))];
}

/** "4 affect FMEA, 3 affect CPL" (the release dialog's count of changes in scope). */
export function documentsText(draft) {
  return `${draft.fmea} affect FMEA, ${draft.cpl} affect CPL`;
}
