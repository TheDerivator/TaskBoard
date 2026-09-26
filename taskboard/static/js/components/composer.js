/** Markdown composer: Write/Preview, formatting toolbar, images by button, paste or drop. */
import { api } from "../api.js";
import { insertBlock, lineEnd, prefixLines, removeFragment, wrap } from "../lib/editor.js";
import { html, useRef, useState } from "../ui.js";
import { CloseIcon } from "./icons.js";
import { showError } from "./toasts.js";

const ImageIcon = () => html`
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="2" /><path d="M21 16l-5-5-9 9" />
  </svg>
`;

/**
 * @param {{
 *   taskKey: string,
 *   initial?: {body_md: string, is_update: boolean},  // editing an existing post
 *   submitLabel?: string,
 *   onSubmit: (body_md: string, is_update: boolean) => Promise<void>,
 *   onCancel?: () => void,
 * }} props
 */
export function Composer({ taskKey, initial = null, submitLabel = "Post", onSubmit, onCancel }) {
  const [body, setBody] = useState(initial?.body_md ?? "");
  const [isUpdate, setIsUpdate] = useState(initial?.is_update ?? false);
  const [mode, setMode] = useState("write");
  const [preview, setPreview] = useState("");
  const [files, setFiles] = useState([]); // {id, filename, markdown}
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const area = useRef(null);
  const fileInput = useRef(null);

  const apply = ({ text, start, end }) => {
    setBody(text);
    requestAnimationFrame(() => {
      const el = area.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(start, end);
    });
  };
  const selection = () => {
    const el = area.current;
    return el ? [el.selectionStart, el.selectionEnd] : [body.length, body.length];
  };
  const format = (kind) => {
    const [start, end] = selection();
    if (kind === "bold") apply(wrap(body, start, end, "**", "**", "bold text"));
    if (kind === "italic") apply(wrap(body, start, end, "_", "_", "italic text"));
    if (kind === "code") apply(wrap(body, start, end, "`", "`", "code"));
    if (kind === "link") apply(wrap(body, start, end, "[", "](https://)", "link text"));
    if (kind === "list") apply(prefixLines(body, start, end, "- "));
  };

  const uploadFiles = async (list) => {
    const images = [...list].filter((f) => f.type.startsWith("image/"));
    for (const file of images) {
      setUploading((n) => n + 1);
      try {
        const form = new FormData();
        form.append("file", file, file.name || "pasted-image.png");
        const uploaded = await api.upload(`/tasks/${taskKey}/attachments`, form);
        setFiles((current) => [...current, uploaded]);
        // On its own line after the caret's line, so it never splits formatted text.
        setBody((current) => {
          const caret = Math.min(area.current?.selectionEnd ?? current.length, current.length);
          return insertBlock(current, lineEnd(current, caret), uploaded.markdown).text;
        });
      } catch (err) {
        showError(err);
      } finally {
        setUploading((n) => n - 1);
      }
    }
  };

  const onPaste = (event) => {
    const pasted = event.clipboardData?.files;
    if (pasted && pasted.length) {
      event.preventDefault();
      uploadFiles(pasted);
    }
  };
  const onDrop = (event) => {
    event.preventDefault();
    setDragOver(false);
    if (event.dataTransfer?.files?.length) uploadFiles(event.dataTransfer.files);
  };

  const showPreview = async () => {
    setMode("preview");
    try {
      setPreview((await api.post("/markdown/preview", { body_md: body })).html);
    } catch (err) {
      setPreview("");
      showError(err);
    }
  };

  const submit = async (event) => {
    event?.preventDefault();
    if (!body.trim() || busy || uploading) return;
    setBusy(true);
    try {
      await onSubmit(body, isUpdate);
      setBody("");
      setFiles([]);
      setIsUpdate(false);
      setMode("write");
    } catch (err) {
      showError(err);
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) submit(event);
  };

  const tool = (label, kind, content) => html`
    <button type="button" class="composer__tool" aria-label=${label} title=${label} disabled=${mode !== "write"} onClick=${() => format(kind)}>
      ${content}
    </button>
  `;

  return html`
    <form class=${`composer${initial ? " composer--inline" : ""}`} onSubmit=${submit}>
      <div
        class=${`composer__box${dragOver ? " composer__box--dragover" : ""}`}
        onDragOver=${(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave=${() => setDragOver(false)}
        onDrop=${onDrop}
      >
        <div class="composer__toolbar">
          <div class="composer__modes" role="group" aria-label="Editor mode">
            <button type="button" aria-pressed=${mode === "write" ? "true" : "false"} onClick=${() => setMode("write")}>Write</button>
            <button type="button" aria-pressed=${mode === "preview" ? "true" : "false"} onClick=${showPreview}>Preview</button>
          </div>
          ${tool("Bold", "bold", html`<b>B</b>`)}
          ${tool("Italic", "italic", html`<i style=${{ fontFamily: "Georgia, serif" }}>I</i>`)}
          ${tool(
            "Bulleted list",
            "list",
            html`<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" /></svg>`,
          )}
          ${tool(
            "Code",
            "code",
            html`<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 7l-5 5 5 5M16 7l5 5-5 5" /></svg>`,
          )}
          ${tool(
            "Link",
            "link",
            html`<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></svg>`,
          )}
          <button type="button" class="composer__tool" aria-label="Attach image" title="Attach image" onClick=${() => fileInput.current?.click()}>
            <${ImageIcon} />
          </button>
          <input
            ref=${fileInput}
            type="file"
            accept="image/png,image/jpeg,image/gif,image/webp"
            multiple
            hidden
            onChange=${(e) => {
              uploadFiles(e.currentTarget.files);
              e.currentTarget.value = "";
            }}
          />
        </div>
        ${mode === "write"
          ? html`<textarea
              ref=${area}
              rows="3"
              aria-label="Write a comment"
              placeholder="Write a comment… Markdown works; paste or drop images."
              value=${body}
              onInput=${(e) => setBody(e.currentTarget.value)}
              onPaste=${onPaste}
              onKeyDown=${onKeyDown}
            ></textarea>`
          : html`<div class="composer__preview md" dangerouslySetInnerHTML=${{ __html: preview || "<p><em>Nothing to preview.</em></p>" }}></div>`}
        ${(files.length > 0 || uploading > 0) &&
        html`<div class="composer__files">
          ${files.map(
            (f) => html`
              <span key=${f.id} class="file-chip">
                <${ImageIcon} />${f.filename}
                <button
                  type="button"
                  aria-label=${`Remove ${f.filename}`}
                  onClick=${() => {
                    setFiles(files.filter((x) => x.id !== f.id));
                    setBody(removeFragment(body, f.markdown));
                  }}
                >
                  <${CloseIcon} size=${12} />
                </button>
              </span>
            `,
          )}
          ${uploading > 0 && html`<span class="file-chip">Uploading…</span>`}
        </div>`}
      </div>
      <div class="composer__foot">
        <label><input type="checkbox" checked=${isUpdate} onChange=${(e) => setIsUpdate(e.currentTarget.checked)} />Post as status update</label>
        <span class="composer__hint">Markdown · paste or drop images · Ctrl+Enter to send</span>
        ${onCancel && html`<button type="button" class="btn" onClick=${onCancel}>Cancel</button>`}
        <button type="submit" class="btn btn--primary" disabled=${busy || uploading > 0 || !body.trim()}>${submitLabel}</button>
      </div>
    </form>
  `;
}
