/** Inline SVG icons (paths from the design mockups). Decorative: hidden from screen readers. */
import { html } from "../ui.js";

const svg = (children, { size = 18, width = 2, fill = "none" } = {}) => html`
  <svg
    width=${size}
    height=${size}
    viewBox="0 0 24 24"
    fill=${fill}
    stroke=${fill === "none" ? "currentColor" : "none"}
    stroke-width=${width}
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    ${children}
  </svg>
`;

export const LogoIcon = () => svg(html`<path d="M4 6h16M4 12h10M4 18h6" />`, { size: 16, width: 2.4 });
export const PriorityIcon = () => svg(html`<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />`);
export const PeopleIcon = () =>
  svg(html`<rect x="3" y="4" width="5" height="16" rx="1" /><rect x="10" y="4" width="5" height="11" rx="1" /><rect x="17" y="4" width="4" height="14" rx="1" />`);
export const ProjectsIcon = () =>
  svg(html`<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />`);
export const PlusIcon = ({ size = 16 } = {}) => svg(html`<path d="M12 5v14M5 12h14" />`, { size, width: 2.4 });
export const SearchIcon = () => svg(html`<circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />`, { size: 16 });
export const CloseIcon = ({ size = 20 } = {}) => svg(html`<path d="M6 6l12 12M18 6L6 18" />`, { size });
export const ChevronIcon = ({ size = 14 } = {}) => svg(html`<path d="M9 6l6 6-6 6" />`, { size, width: 2.4 });
export const SunIcon = () =>
  svg(html`<circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />`);
export const MoonIcon = () => svg(html`<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />`);
export const CollapseIcon = () => svg(html`<rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16M15 10l-2 2 2 2" />`);
export const ExpandIcon = () => svg(html`<rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16M13 10l2 2-2 2" />`);
export const MenuIcon = () => svg(html`<path d="M4 6h16M4 12h16M4 18h16" />`, { size: 22 });
export const LoginIcon = () => svg(html`<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3" />`, { size: 16 });
export const LogoutIcon = () => svg(html`<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />`);

/** The six-dot drag handle from the Priority mockup. */
export const GripIcon = () => html`
  <svg width="14" height="20" viewBox="0 0 14 20" fill="currentColor" aria-hidden="true" focusable="false">
    <circle cx="4" cy="4" r="1.6" /><circle cx="10" cy="4" r="1.6" /><circle cx="4" cy="10" r="1.6" />
    <circle cx="10" cy="10" r="1.6" /><circle cx="4" cy="16" r="1.6" /><circle cx="10" cy="16" r="1.6" />
  </svg>
`;
export const AdminIcon = () =>
  svg(html`<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z" /><path d="M9 12l2 2 4-4" />`);
export const ArrowUpIcon = () => svg(html`<path d="M12 19V5M5 12l7-7 7 7" />`, { size: 16 });
export const ArrowDownIcon = () => svg(html`<path d="M12 5v14M19 12l-7 7-7-7" />`, { size: 16 });
export const IndentIcon = () => svg(html`<path d="M3 6h18M11 12h10M11 18h10M3 10l4 3-4 3" />`, { size: 16 });
export const OutdentIcon = () => svg(html`<path d="M3 6h18M11 12h10M11 18h10M7 10l-4 3 4 3" />`, { size: 16 });
export const TrashIcon = () =>
  svg(html`<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />`, { size: 16 });
