/** "Copy link" button: puts the full URL of an app path on the clipboard (task permalinks, team views). */
import { href } from "../router.js";
import { html } from "../ui.js";
import { showToast } from "./toasts.js";

const LinkIcon = () => html`
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
    <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />
  </svg>
`;

/** Copy text; falls back to a hidden textarea where the Clipboard API is unavailable (plain HTTP). */
async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}

/** @param {{path: string, label: string}} props  app-relative path, and the button's accessible name */
export function CopyLinkButton({ path, label }) {
  const copy = async () => {
    const url = new URL(href(path), location.origin).href;
    try {
      await copyText(url);
      showToast("Link copied.");
    } catch {
      window.prompt("Copy this link:", url);
    }
  };
  return html`<button type="button" class="icon-btn" aria-label=${label} title="Copy link" onClick=${copy}><${LinkIcon} /></button>`;
}
