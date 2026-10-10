/** Administration › Backups wording: sizes, why a backup is kept, the state of the backups. Pure. */
import { formatDate, plural } from "./format.js";

export const KEPT_AS = {
  newest: "Newest",
  weekly: "First of the week",
  monthly: "First of the month",
};

/** Bytes as Windows Explorer counts them: "980 B", "1.5 KB", "12 MB", "2.4 GB". */
export function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = bytes / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size < 10 ? size.toFixed(1) : Math.round(size)} ${units[unit]}`;
}

export function backupTime(value) {
  return formatDate(value, { withTime: true, withYear: true });
}

/** The line above the list: is all well, or should someone look at the scheduled task? */
export function backupStatus(overview) {
  const newest = overview.backups[0];
  if (overview.problem) return { ok: false, text: overview.problem };
  if (!newest) return { ok: false, text: "No backups yet. Check the scheduled task that makes them." };
  if (overview.overdue) {
    return {
      ok: false,
      text: `The newest backup is from ${backupTime(newest.taken_at)}, more than two days ago. Check the scheduled task that makes them.`,
    };
  }
  const count = plural(overview.backups.length, "backup");
  return { ok: true, text: `Newest backup: ${backupTime(newest.taken_at)}. ${count}, ${formatSize(overview.total_size)} in all.` };
}
