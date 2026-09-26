/** Modal dialogs on the native <dialog> element (focus trapping and backdrop for free). */
import { CloseIcon } from "./icons.js";
import { html, useEffect, useRef } from "../ui.js";

/**
 * Shared behaviour of modal <dialog>s (dialogs and drawers):
 * - opens with showModal() on mount, closes on unmount;
 * - Escape is handled on keydown (browsers only let a page veto the `cancel` event once per user
 *   activation), and only for the innermost dialog, so nested dialogs close one at a time;
 * - if the browser closes the dialog anyway, `onClose` is called so the app catches up.
 * `onClose` may be null (not dismissible) or decline to close.
 */
export function useModalDialog(ref, onClose) {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const unmounting = useRef(false);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => {
      unmounting.current = true;
      if (dialog?.open) dialog.close();
    };
  }, []);

  const requestClose = () => onCloseRef.current?.();
  const isInnermost = (event) => event.target.closest("dialog") === ref.current;

  return {
    requestClose,
    props: {
      onKeyDown: (event) => {
        if (event.key !== "Escape" || event.defaultPrevented || !isInnermost(event)) return;
        event.preventDefault();
        requestClose();
      },
      onCancel: (event) => {
        event.preventDefault();
        if (isInnermost(event)) requestClose();
      },
      onClose: (event) => {
        if (!unmounting.current && event.target === ref.current) requestClose();
      },
    },
  };
}

/**
 * Rendered only while open, so closed dialogs leave nothing in the page.
 * @param {{open: boolean, title: string, onClose?: () => void, dismissible?: boolean, children: any}} props
 * `dismissible=false` keeps the dialog open on Escape (e.g. a required password change).
 */
export function Dialog({ open, ...props }) {
  return open ? html`<${OpenDialog} ...${props} />` : null;
}

function OpenDialog({ title, onClose, dismissible = true, children, wide = false, large = false }) {
  const ref = useRef(null);
  const { props } = useModalDialog(ref, dismissible ? onClose : null);
  return html`
    <dialog
      ref=${ref}
      class=${`dialog${wide ? " dialog--wide" : ""}${large ? " dialog--large" : ""}`}
      aria-label=${title}
      ...${props}
    >
      <div class="dialog__form">
        <div class="dialog__head">
          <h2>${title}</h2>
          ${dismissible &&
          html`<button type="button" class="icon-btn" aria-label="Close" onClick=${() => onClose?.()}>
            <${CloseIcon} />
          </button>`}
        </div>
        ${children}
      </div>
    </dialog>
  `;
}
