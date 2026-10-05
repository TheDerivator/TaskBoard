/** A Markdown text field for forms (a box's description): Write/Preview, a formatting toolbar and,
 * where uploads are possible, images by button, paste or drop. Unlike the composer it has no
 * submit of its own: the form around it saves. */
import { api } from "../api.js";
import { insertBlock, lineEnd, prefixLines, wrap } from "../lib/editor.js";
import { html, useRef, useState } from "../ui.js";
import { showError } from "./toasts.js";

const ListIcon = () => html`
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
    <path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" />
  </svg>
`;
const ImageIcon = () => html`
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="2" /><path d="M21 16l-5-5-9 9" />
  </svg>
`;

/**
 * @param {{value: string, onChange: (text: string) => void, label: string, rows?: number,
 *   uploadPath?: ?string}} props  `uploadPath` (e.g. "/boxes/fm-level/attachments") enables images
 */
export function MarkdownField({ value, onChange, label, rows = 7, uploadPath = null }) {
  const [mode, setMode] = useState("write");
  const [preview, setPreview] = useState("");
  const [uploading, setUploading] = useState(0);
  const area = useRef(null);
  const fileInput = useRef(null);

  const apply = ({ text, start, end }) => {
    onChange(text);
    requestAnimationFrame(() => {
      area.current?.focus();
      area.current?.setSelectionRange(start, end);
    });
  };
  const selection = () => (area.current ? [area.current.selectionStart, area.current.selectionEnd] : [value.length, value.length]);
  const format = (kind) => {
    const [start, end] = selection();
    if (kind === "bold") apply(wrap(value, start, end, "**", "**", "bold text"));
    if (kind === "italic") apply(wrap(value, start, end, "_", "_", "italic text"));
    if (kind === "heading") apply(prefixLines(value, start, end, "### "));
    if (kind === "list") apply(prefixLines(value, start, end, "- "));
  };

  const upload = async (files) => {
    let text = value;
    for (const file of [...files].filter((f) => f.type.startsWith("image/"))) {
      setUploading((n) => n + 1);
      try {
        const form = new FormData();
        form.append("file", file, file.name || "pasted-image.png");
        const uploaded = await api.upload(uploadPath, form);
        const caret = Math.min(area.current?.selectionEnd ?? text.length, text.length);
        text = insertBlock(text, lineEnd(text, caret), uploaded.markdown).text;
        onChange(text);
      } catch (error) {
        showError(error);
      } finally {
        setUploading((n) => n - 1);
      }
    }
  };

  const showPreview = async () => {
    setMode("preview");
    try {
      setPreview((await api.post("/markdown/preview", { body_md: value })).html);
    } catch (error) {
      setPreview("");
      showError(error);
    }
  };

  const tool = (name, kind, content) => html`
    <button type="button" class="composer__tool" aria-label=${name} title=${name} disabled=${mode !== "write"} onClick=${() => format(kind)}>${content}</button>
  `;
  return html`
    <div class="composer__box markdown-field">
      <div class="composer__toolbar">
        <div class="composer__modes" role="group" aria-label=${`${label}: editor mode`}>
          <button type="button" aria-pressed=${mode === "write" ? "true" : "false"} onClick=${() => setMode("write")}>Write</button>
          <button type="button" aria-pressed=${mode === "preview" ? "true" : "false"} onClick=${showPreview}>Preview</button>
        </div>
        ${tool("Bold", "bold", html`<b>B</b>`)}
        ${tool("Italic", "italic", html`<i style=${{ fontFamily: "Georgia, serif" }}>I</i>`)}
        ${tool("Heading", "heading", html`<b>H</b>`)}
        ${tool("Bulleted list", "list", html`<${ListIcon} />`)}
        ${uploadPath &&
        html`<button type="button" class="composer__tool" aria-label="Insert image" title="Insert image" disabled=${mode !== "write"} onClick=${() => fileInput.current?.click()}>
            <${ImageIcon} />
          </button>
          <input
            ref=${fileInput}
            type="file"
            accept="image/png,image/jpeg,image/gif,image/webp"
            multiple
            hidden
            onChange=${(e) => {
              upload(e.currentTarget.files);
              e.currentTarget.value = "";
            }}
          />`}
        ${uploading > 0 && html`<span class="field-hint">Uploading…</span>`}
      </div>
      ${mode === "write"
        ? html`<textarea
            ref=${area}
            rows=${rows}
            aria-label=${label}
            value=${value}
            onInput=${(e) => onChange(e.currentTarget.value)}
            onPaste=${(e) => {
              if (uploadPath && e.clipboardData?.files?.length) {
                e.preventDefault();
                upload(e.clipboardData.files);
              }
            }}
            onDrop=${(e) => {
              if (uploadPath && e.dataTransfer?.files?.length) {
                e.preventDefault();
                upload(e.dataTransfer.files);
              }
            }}
          ></textarea>`
        : html`<div class="composer__preview md" dangerouslySetInnerHTML=${{ __html: preview || "<p><em>Nothing to preview.</em></p>" }}></div>`}
    </div>
  `;
}
