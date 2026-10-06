/** API tokens for AI agents (pure, D-097): the choices for a new token, what the profile page says
 * about each one, and the commands that hand a new token to an agent. */
import { formatDate } from "./format.js";

export const SCOPES = [
  { value: "read", label: "Read only", hint: "Look things up, summarize, report. Cannot change anything." },
  { value: "write", label: "Read and write", hint: "Also create and edit tasks, posts, changes and the map, as you could. Never administration." },
];

export const EXPIRY_CHOICES = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 365, label: "1 year" },
  { days: null, label: "Never" },
];

export const DEFAULT_EXPIRY = 90;

export function scopeLabel(scope) {
  return SCOPES.find((s) => s.value === scope)?.label ?? scope;
}

/** "Expires 4 Jan 2027", "Expired 4 Jan 2027" or "Never expires". */
export function expiryText(token) {
  if (!token.expires_at) return "Never expires";
  const day = `${formatDate(token.expires_at)} ${new Date(token.expires_at).getFullYear()}`;
  return token.expired ? `Expired ${day}` : `Expires ${day}`;
}

/** "Never used" or "Last used 3 Oct, 14:02". */
export function lastUsedText(token) {
  return token.last_used_at ? `Last used ${formatDate(token.last_used_at, { withTime: true })}` : "Never used";
}

/** Commands that put a new token in TASKBOARD_TOKEN, where the agent guide tells agents to look. */
export function envCommands(secret) {
  return [
    { shell: "PowerShell, this window", command: `$env:TASKBOARD_TOKEN = "${secret}"` },
    { shell: "Windows, every new window", command: `setx TASKBOARD_TOKEN "${secret}"` },
    { shell: "bash or zsh", command: `export TASKBOARD_TOKEN='${secret}'` },
  ];
}
