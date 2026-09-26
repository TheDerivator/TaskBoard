/** Side drawer on a modal <dialog>: slides in from the right, Escape/backdrop close it. */
import { html, useRef } from "../ui.js";
import { useModalDialog } from "./dialog.js";

/** `onClose` may decline to close (e.g. after "Discard unsaved changes?" → No). */
export function Drawer({ label, onClose, children }) {
  const ref = useRef(null);
  const handlers = useModalDialog(ref, onClose);

  // A click on the backdrop reaches the dialog element itself (its content covers the rest).
  const onClick = (event) => {
    if (event.target === ref.current) handlers.requestClose();
  };

  return html`
    <dialog ref=${ref} class="drawer" aria-label=${label} ...${handlers.props} onClick=${onClick}>
      ${children}
    </dialog>
  `;
}
