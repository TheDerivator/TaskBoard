/** Images in Markdown open full size over the page; a click anywhere (or Escape) closes them again. */
import { html, useEffect, useRef, useState } from "../ui.js";
import { useModalDialog } from "./dialog.js";
import { CloseIcon } from "./icons.js";

/** An image in rendered Markdown (posts, descriptions, previews), unless its author made it a link. */
function zoomableImage(target) {
  const image = target.closest?.(".md img");
  return image && !image.closest("a") ? image : null;
}

/** Mounted once by the app: a click on any Markdown image opens it (Ctrl/⌘ click: in a new tab). */
export function Lightbox() {
  const [image, setImage] = useState(null); // {src, alt} while open

  useEffect(() => {
    const onClick = (event) => {
      const found = zoomableImage(event.target);
      if (!found) return;
      event.preventDefault();
      if (event.ctrlKey || event.metaKey || event.shiftKey) window.open(found.src, "_blank", "noopener");
      else setImage({ src: found.src, alt: found.alt });
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  return image ? html`<${OpenLightbox} key=${image.src} src=${image.src} alt=${image.alt} onClose=${() => setImage(null)} />` : null;
}

function OpenLightbox({ src, alt, onClose }) {
  const ref = useRef(null);
  const { props } = useModalDialog(ref, onClose);
  // Every click closes it: on the image, beside it, or on the close button (there for keyboards).
  return html`
    <dialog ref=${ref} class="lightbox" aria-label=${alt ? `Image: ${alt}` : "Image"} ...${props} onClick=${onClose}>
      <img class="lightbox__image" src=${src} alt=${alt} />
      <button type="button" class="icon-btn lightbox__close" aria-label="Close image"><${CloseIcon} /></button>
    </dialog>
  `;
}
