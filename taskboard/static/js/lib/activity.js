/** Recent activity (pure): day headings ("Today", "Yesterday", "19 Sep") and when each post was written. */
import { formatDate, formatTime } from "./format.js";

const DAY = 86_400_000;

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/** "Today", "Yesterday", else "19 Sep" (with the year when it is not this year's). Local time. */
export function dayLabel(value, now = new Date()) {
  const date = new Date(value);
  const days = Math.round((startOfDay(now) - startOfDay(date)) / DAY); // round: days with a DST change
  if (days <= 0) return "Today"; // or a clock running a little behind the server's
  if (days === 1) return "Yesterday";
  return formatDate(date, { withYear: date.getFullYear() !== now.getFullYear() });
}

/**
 * Consecutive items of the same day together, in the order given (newest first).
 * @returns {{label: string, items: object[]}[]}
 */
export function dayGroups(items, now = new Date(), when = (item) => item.last_post.created_at) {
  const groups = [];
  for (const item of items) {
    const label = dayLabel(when(item), now);
    const last = groups.at(-1);
    if (last?.label === label) last.items.push(item);
    else groups.push({ label, items: [item] });
  }
  return groups;
}

/** When a post was written, under its day's heading: "just now", "12 min ago", else "14:02". */
export function postTime(value, now = new Date()) {
  const date = new Date(value);
  const minutes = Math.floor((now - date) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  return formatTime(date);
}
