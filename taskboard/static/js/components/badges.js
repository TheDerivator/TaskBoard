/** Small display components: person avatar, lifecycle pill, project chip. */
import { initials } from "../lib/format.js";
import { html } from "../ui.js";

const STATUS_LABELS = { idea: "Idea", started: "Started", done: "Done", archived: "Archived" };

export function statusLabel(status) {
  return STATUS_LABELS[status] ?? status;
}

/** A round avatar: a person's code on their colour; `person` may be null (unknown). */
export function Avatar({ person, name, size = "normal", ring = false, title }) {
  const text = person?.code ?? initials(name ?? "?");
  const classes = ["avatar", size === "small" && "avatar--small", ring && "avatar--ring"].filter(Boolean).join(" ");
  const style = person?.color ? { "--avatar-color": person.color } : undefined;
  const label = title ?? person?.name ?? name;
  return html`<span class=${classes} style=${style} title=${label} aria-label=${label} role="img">${text}</span>`;
}

/** "via Claude Code" next to an author: written through an API token (D-097). */
export function ViaBadge({ actor }) {
  if (!actor?.via) return null;
  return html`<span class="via-badge" title=${`Done by ${actor.display_name} through the API token “${actor.via}”`}>via ${actor.via}</span>`;
}

export function StatusPill({ status, small = false }) {
  return html`<span class=${`pill pill--${status}${small ? " pill--small" : ""}`}>${statusLabel(status)}</span>`;
}

/** "Action plan surface quality 2.2.1" with the project's colour dot. */
export function ProjectChip({ project, placement }) {
  if (!project) return null;
  const number = placement.number ?? "";
  const where = placement.path.length ? `${project.name} › ${placement.path.join(" › ")}` : `${project.name} (top level)`;
  return html`
    <span class="project-chip" style=${{ "--project-color": project.color }} title=${where}>
      <span class="project-dot"></span>
      <span class="project-chip__name">${project.name}</span>
      ${number && html`<span class="project-chip__number">${number}</span>`}
    </span>
  `;
}
