/** Searchable person list in a popover (lead picker, "Add person"); keyboard and pointer friendly. */
import { html, useEffect, useMemo, useRef, useState } from "../ui.js";
import { Avatar } from "./badges.js";

/**
 * @param {{people: object[], lookup: object, label: string, onPick: (person) => void, onClose: () => void}} props
 */
export function PersonPicker({ people, lookup, label, onPick, onClose }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const root = useRef(null);
  const input = useRef(null);

  const matches = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return people.filter((p) => !needle || `${p.name} ${p.code}`.toLocaleLowerCase().includes(needle));
  }, [people, query]);

  useEffect(() => {
    input.current?.focus();
    const onPointer = (event) => {
      if (root.current && !root.current.contains(event.target)) onClose();
    };
    document.addEventListener("pointerdown", onPointer, true);
    return () => document.removeEventListener("pointerdown", onPointer, true);
  }, [onClose]);

  useEffect(() => setActive(0), [query]);

  const onKey = (event) => {
    if (event.key === "ArrowDown") setActive((i) => Math.min(i + 1, matches.length - 1));
    else if (event.key === "ArrowUp") setActive((i) => Math.max(i - 1, 0));
    else if (event.key === "Enter" && matches[active]) onPick(matches[active]);
    else if (event.key === "Escape") onClose();
    else return;
    event.preventDefault();
    event.stopPropagation();
  };

  const meta = (person) => {
    const section = lookup.sections.get(person.section_id);
    const department = section && lookup.departments.get(section.department_id);
    return department ? `${department.code} · ${section.name}` : "";
  };

  return html`
    <div class="picker" ref=${root} role="dialog" aria-label=${label}>
      <input
        ref=${input}
        type="search"
        placeholder="Search people…"
        aria-label=${label}
        aria-controls="picker-options"
        value=${query}
        onInput=${(e) => setQuery(e.currentTarget.value)}
        onKeyDown=${onKey}
      />
      ${matches.length === 0
        ? html`<div class="picker__empty">No one matches.</div>`
        : html`
            <ul id="picker-options" role="listbox" aria-label=${label}>
              ${matches.map(
                (person, index) => html`
                  <li
                    key=${person.id}
                    role="option"
                    aria-selected=${index === active ? "true" : "false"}
                    onPointerMove=${() => setActive(index)}
                    onClick=${() => onPick(person)}
                  >
                    <${Avatar} person=${person} size="small" />
                    <span>${person.name}</span>
                    <span class="muted">${meta(person)}</span>
                  </li>
                `,
              )}
            </ul>
          `}
    </div>
  `;
}
