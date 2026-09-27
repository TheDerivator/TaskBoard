/** Formatting helpers: ranks ("01"), short names ("Anna C."), initials, dates. Pure. */

export function padRank(rank) {
  return rank < 10 ? `0${rank}` : String(rank);
}

/** "Anna Claes" → "Anna C."; single names stay as they are. */
export function shortName(name) {
  const parts = String(name).trim().split(/\s+/);
  if (parts.length < 2) return parts[0] ?? "";
  return `${parts[0]} ${parts[parts.length - 1][0]}.`;
}

/** "Anna Claes" → "AC", "admin" → "AD". */
export function initials(name) {
  const parts = String(name).trim().split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "12 Sep" (local time); `withTime` adds ", 14:02". Accepts an ISO string or a Date. */
export function formatDate(value, { withTime = false } = {}) {
  const date = value instanceof Date ? value : new Date(value);
  const day = `${date.getDate()} ${MONTHS[date.getMonth()]}`;
  if (!withTime) return day;
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${day}, ${hh}:${mm}`;
}

export function plural(count, one, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`;
}
