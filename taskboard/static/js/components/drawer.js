/** Side drawer on a modal <dialog>: slides in from the right, Escape/backdrop close it, can widen. */
import { readPref, writePref } from "../prefs.js";
import { createContext, html, useContext, useRef, useState } from "../ui.js";
import { useModalDialog } from "./dialog.js";
import { MaximizeIcon, RestoreIcon } from "./icons.js";

const WideContext = createContext(null);

/** `onClose` may decline to close (e.g. after "Discard unsaved changes?" → No). */
export function Drawer({ label, onClose, children }) {
  const ref = useRef(null);
  const handlers = useModalDialog(ref, onClose);
  // Full width (all but the sidebar) is remembered per browser, like the collapsed sidebar.
  const [wide, setWide] = useState(() => readPref("drawer.wide", false));
  const toggleWide = () => {
    writePref("drawer.wide", !wide);
    setWide(!wide);
  };

  // A click on the backdrop reaches the dialog element itself (its content covers the rest).
  const onClick = (event) => {
    if (event.target === ref.current) handlers.requestClose();
  };

  return html`
    <dialog ref=${ref} class=${`drawer${wide ? " drawer--wide" : ""}`} aria-label=${label} ...${handlers.props} onClick=${onClick}>
      <${WideContext.Provider} value=${{ wide, toggleWide }}>${children}<//>
    </dialog>
  `;
}

/** "Full width" for a drawer's header; renders nothing outside a drawer (e.g. on a task page). */
export function DrawerWidthToggle() {
  const context = useContext(WideContext);
  if (!context) return null;
  const { wide, toggleWide } = context;
  return html`
    <button
      type="button"
      class="icon-btn drawer-width-toggle"
      aria-label="Full width"
      aria-pressed=${wide ? "true" : "false"}
      title=${wide ? "Back to a side panel" : "Use the full width"}
      onClick=${toggleWide}
    >
      ${wide ? html`<${RestoreIcon} />` : html`<${MaximizeIcon} />`}
    </button>
  `;
}
