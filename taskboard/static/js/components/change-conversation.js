/** A process change's conversation: comments and period posts in time order, the Comment / Period
 * composer, editing a period (also "Set end date"), and the earlier versions of edited posts. */
import { api } from "../api.js";
import { useApi } from "../hooks.js";
import { formatDate } from "../lib/format.js";
import { formatDay, periodDuration, periodSentence } from "../lib/periods.js";
import { dataChanged } from "../store.js";
import { html, useEffect, useRef, useState } from "../ui.js";
import { Avatar } from "./badges.js";
import { Composer } from "./composer.js";
import { Dialog } from "./dialog.js";
import { CloseIcon } from "./icons.js";
import { showError, showToast } from "./toasts.js";

/** "Anna Claes · 10 Apr, 15:20 · edited" with a button that shows the earlier versions. */
function Byline({ post, onHistory }) {
  return html`
    <span class="post-byline">
      ${post.author.display_name} · <time datetime=${post.created_at}>${formatDate(post.created_at, { withTime: true })}</time>
      ${post.versions > 1 &&
      html` · <button type="button" class="link-button" onClick=${onHistory} title=${post.edited_by ? `Edited by ${post.edited_by.display_name}` : undefined}>
          edited
        </button>`}
    </span>
  `;
}

export function ScopeTags({ tags }) {
  if (!tags.length) return null;
  return html`<ul class="scope-tags" aria-label="Scope">${tags.map((t) => html`<li key=${t} class="scope-tag">${t}</li>`)}</ul>`;
}

/** Scope tags: free text (DESIGN rule 4). Enter or comma adds; tags used on the process are offered. */
function TagInput({ tags, onChange, suggestions, id }) {
  const [text, setText] = useState("");
  const add = (value) => {
    const tag = value.trim().replace(/\s+/g, " ");
    if (tag && !tags.some((t) => t.toLowerCase() === tag.toLowerCase())) onChange([...tags, tag]);
    setText("");
  };
  const offered = suggestions.filter((s) => !tags.some((t) => t.toLowerCase() === s.toLowerCase()));
  return html`
    <div class="tag-input">
      ${tags.map(
        (t) => html`
          <span key=${t} class="scope-tag scope-tag--removable">
            ${t}
            <button type="button" aria-label=${`Remove ${t}`} onClick=${() => onChange(tags.filter((x) => x !== t))}><${CloseIcon} size=${10} /></button>
          </span>
        `,
      )}
      <input
        id=${id}
        list=${`${id}-suggestions`}
        aria-label="Add scope tag"
        placeholder="Caster, grade, heats… Enter adds"
        value=${text}
        onInput=${(e) => setText(e.currentTarget.value)}
        onKeyDown=${(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            add(text);
          } else if (e.key === "Backspace" && !text && tags.length) {
            onChange(tags.slice(0, -1));
          }
        }}
        onBlur=${() => text.trim() && add(text)}
      />
      <datalist id=${`${id}-suggestions`}>${offered.map((s) => html`<option key=${s} value=${s}></option>`)}</datalist>
    </div>
    ${offered.length > 0 && html`<span class="field-hint">Used before: ${offered.slice(0, 8).join(" · ")}</span>`}
  `;
}

function emptyPeriod(today) {
  return { kind: "test", label: "", start_date: today, end_date: today, scope_tags: [], body_md: "" };
}

/** Post or edit a period: label, from/to, "No end date", scope, details (Markdown). */
export function PeriodForm({ initial = null, today, suggestions, submitLabel = "Post period", onSubmit, onCancel }) {
  const [form, setForm] = useState(() =>
    initial
      ? { ...initial, scope_tags: [...initial.scope_tags], body_md: initial.body_md ?? "" }
      : emptyPeriod(today),
  );
  const [busy, setBusy] = useState(false);
  const idBase = useRef(`period-${Math.random().toString(36).slice(2, 8)}`).current;
  const set = (patch) => setForm({ ...form, ...patch });
  const permanent = form.kind === "change";
  const invalid = !form.start_date || (!permanent && !form.end_date) || (form.end_date && form.end_date < form.start_date);

  const submit = async (event) => {
    event.preventDefault();
    if (invalid || busy) return;
    setBusy(true);
    try {
      await onSubmit({ ...form, label: form.label.trim() || null, end_date: form.end_date || null });
      if (!initial) setForm(emptyPeriod(today));
    } catch (err) {
      showError(err);
    } finally {
      setBusy(false);
    }
  };

  return html`
    <form class="period-form" onSubmit=${submit} aria-label=${initial ? "Edit period" : "New period"}>
      <div class="period-form__box">
        <div class="period-form__dates">
          <label class="field field--compact">
            <span class="field__label">Label</span>
            <input class="input" maxlength="100" placeholder=${permanent ? "Process change" : "Test"} value=${form.label} onInput=${(e) => set({ label: e.currentTarget.value })} />
          </label>
          <label class="field field--compact">
            <span class="field__label">From</span>
            <input class="input input--date" type="date" required value=${form.start_date} onInput=${(e) => set({ start_date: e.currentTarget.value })} />
          </label>
          <label class="field field--compact">
            <span class="field__label">To</span>
            <input
              class="input input--date"
              type="date"
              required=${!permanent}
              disabled=${permanent && !initial?.end_date}
              min=${form.start_date}
              value=${form.end_date ?? ""}
              onInput=${(e) => set({ end_date: e.currentTarget.value })}
            />
          </label>
        </div>
        <label class="check-line">
          <input
            type="checkbox"
            checked=${permanent}
            onChange=${(e) => set({ kind: e.currentTarget.checked ? "change" : "test", end_date: e.currentTarget.checked ? null : form.end_date || form.start_date })}
          />
          No end date: this is a permanent process change
        </label>
        <div class="field field--compact">
          <label class="field__label" for=${`${idBase}-tags`}>Scope · optional, anything goes</label>
          <${TagInput} id=${`${idBase}-tags`} tags=${form.scope_tags} suggestions=${suggestions} onChange=${(scope_tags) => set({ scope_tags })} />
        </div>
        <label class="field field--compact">
          <span class="field__label">Details · Markdown</span>
          <textarea class="textarea textarea--mono" rows="2" value=${form.body_md} onInput=${(e) => set({ body_md: e.currentTarget.value })}></textarea>
        </label>
      </div>
      <div class="period-form__foot">
        <span class="field-hint" aria-live="polite">${invalid ? "A test needs an end date on or after its start." : periodSentence(form, today)}</span>
        ${onCancel && html`<button type="button" class="btn" onClick=${onCancel}>Cancel</button>`}
        <button type="submit" class="btn btn--primary" disabled=${invalid || busy}>${submitLabel}</button>
      </div>
    </form>
  `;
}

/** "Set end date" on a process change: ends (reverts) it. */
function EndDateForm({ period, onSubmit, onCancel }) {
  const [end, setEnd] = useState(period.start_date > new Date().toISOString().slice(0, 10) ? period.start_date : new Date().toISOString().slice(0, 10));
  return html`
    <form
      class="end-date-form"
      onSubmit=${async (e) => {
        e.preventDefault();
        await onSubmit(end);
      }}
    >
      <label class="field field--compact">
        <span class="field__label">Last day in effect</span>
        <input class="input input--date" type="date" required min=${period.start_date} value=${end} onInput=${(e) => setEnd(e.currentTarget.value)} />
      </label>
      <button type="button" class="btn" onClick=${onCancel}>Cancel</button>
      <button type="submit" class="btn btn--primary">Set end date</button>
    </form>
  `;
}

function PeriodPost({ post, lookup, today, suggestions, onChanged, onHistory }) {
  const [mode, setMode] = useState(null); // null | "edit" | "end"
  const period = post.period;
  const person = post.author.person_id != null ? lookup.people.get(post.author.person_id) : null;
  const tone = period.kind === "change" ? "change" : "test";
  const update = async (patch, message) => {
    try {
      await api.patch(`/periods/${period.id}`, patch);
      setMode(null);
      showToast(message);
      onChanged();
    } catch (err) {
      showError(err);
    }
  };
  const remove = async () => {
    if (!window.confirm(`Delete the period "${period.label}"? It disappears from the timeline.`)) return;
    try {
      await api.delete(`/posts/${post.id}`);
      showToast("Period deleted.");
      onChanged();
    } catch (err) {
      showError(err);
    }
  };
  return html`
    <article id=${`post-${post.id}`} class=${`post period-post period-post--${tone}`} aria-label=${`${period.label}, ${periodDuration(period)}`}>
      <${Avatar} person=${person} name=${post.author.display_name} />
      <div class="period-post__card">
        <div class="period-post__head">
          <span class=${`period-swatch period-swatch--${tone}${period.kind === "change" && !period.end_date ? " period-swatch--open" : ""}`} aria-hidden="true"></span>
          <span class="period-post__label">${period.label}</span>
          <span class="period-post__dates">${periodDuration(period)}</span>
          ${post.can_edit &&
          !mode &&
          html`<span class="period-post__actions">
            ${period.kind === "change" && !period.end_date && html`<button type="button" class="link-button" onClick=${() => setMode("end")}>Set end date</button>`}
            <button type="button" class="link-button" onClick=${() => setMode("edit")}>Edit period</button>
            <button type="button" class="link-button" onClick=${remove}>Delete</button>
          </span>`}
        </div>
        <div class="period-post__body">
          ${mode === "end"
            ? html`<${EndDateForm} period=${period} onCancel=${() => setMode(null)} onSubmit=${(end_date) => update({ end_date }, `Ended on ${formatDay(end_date)}.`)} />`
            : mode === "edit"
              ? html`<${PeriodForm}
                  initial=${{ ...period, body_md: post.body_md }}
                  today=${today}
                  suggestions=${suggestions}
                  submitLabel="Save period"
                  onCancel=${() => setMode(null)}
                  onSubmit=${(data) => update(data, "Period saved.")}
                />`
              : html`
                  <${ScopeTags} tags=${period.scope_tags} />
                  ${post.body_md && html`<div class="md" dangerouslySetInnerHTML=${{ __html: post.html }}></div>`}
                  <${Byline} post=${post} onHistory=${onHistory} />
                `}
        </div>
      </div>
    </article>
  `;
}

function CommentPost({ post, lookup, uploadPath, onChanged, onHistory }) {
  const [editing, setEditing] = useState(false);
  const person = post.author.person_id != null ? lookup.people.get(post.author.person_id) : null;
  const save = async (body_md) => {
    await api.patch(`/posts/${post.id}`, { body_md, is_update: false });
    setEditing(false);
    onChanged();
  };
  const remove = async () => {
    if (!window.confirm("Delete this comment?")) return;
    try {
      await api.delete(`/posts/${post.id}`);
      showToast("Comment deleted.");
      onChanged();
    } catch (err) {
      showError(err);
    }
  };
  return html`
    <article id=${`post-${post.id}`} class="post" aria-label=${`Comment by ${post.author.display_name}`}>
      <${Avatar} person=${person} name=${post.author.display_name} />
      <div class="post__main">
        <div class="post__head">
          <span class="post__author">${post.author.display_name}</span>
          <time class="post__time" datetime=${post.created_at}>${formatDate(post.created_at, { withTime: true })}</time>
          ${post.versions > 1 && html`<button type="button" class="link-button" onClick=${onHistory}>edited</button>`}
          ${post.can_edit &&
          !editing &&
          html`<span class="post__actions">
            <button type="button" class="link-button" onClick=${() => setEditing(true)}>Edit</button>
            <button type="button" class="link-button" onClick=${remove}>Delete</button>
          </span>`}
        </div>
        ${editing
          ? html`<${Composer}
              uploadPath=${uploadPath}
              allowUpdate=${false}
              initial=${{ body_md: post.body_md, is_update: false }}
              submitLabel="Save"
              onSubmit=${save}
              onCancel=${() => setEditing(false)}
            />`
          : html`<div class="md" dangerouslySetInnerHTML=${{ __html: post.html }}></div>`}
      </div>
    </article>
  `;
}

/** Every version of an edited post, oldest first. */
function HistoryDialog({ postId, onClose }) {
  const { data, error } = useApi(postId == null ? null : `/posts/${postId}/history`);
  return html`
    <${Dialog} open=${postId != null} title="Earlier versions" onClose=${onClose} wide>
      <div class="dialog__body history">
        ${error && html`<p role="alert">${error.message}</p>`}
        ${!data && !error && html`<p class="muted">Loading…</p>`}
        ${data?.map(
          (v, index) => html`
            <section key=${v.rev} class="history__version" aria-label=${`Version ${v.rev}`}>
              <p class="history__meta">
                ${index === data.length - 1 ? "Now" : `Version ${v.rev}`} · ${v.written_by.display_name} ·
                ${" "}${formatDate(v.written_at, { withTime: true })}
              </p>
              ${v.period && html`<p class="history__period"><strong>${v.period.label}</strong> · ${periodDuration(v.period)}</p>`}
              ${v.period && html`<${ScopeTags} tags=${v.period.scope_tags} />`}
              ${v.body_md && html`<div class="md" dangerouslySetInnerHTML=${{ __html: v.html }}></div>`}
            </section>
          `,
        )}
      </div>
    <//>
  `;
}

/**
 * @param {{change: object, processCode: string, lookup: object, today: string, periodsOnly: boolean,
 *   startWith?: "comment" | "period", onCount?: (n: number) => void}} props
 */
export function ChangeConversation({ change, processCode, lookup, today, periodsOnly, startWith = "comment", onCount }) {
  const { data, error, reload } = useApi(`/changes/${encodeURIComponent(change.key)}/conversation`, { periods_only: periodsOnly });
  const tags = useApi(`/processes/${encodeURIComponent(processCode)}/scope-tags`);
  const [mode, setMode] = useState(startWith);
  const [historyOf, setHistoryOf] = useState(null);
  const bottom = useRef(null);
  const uploadPath = `/changes/${encodeURIComponent(change.key)}/attachments`;

  useEffect(() => {
    if (!data) return;
    onCount?.(data.post_count);
    const target = location.hash ? document.getElementById(location.hash.slice(1)) : null;
    (target ?? bottom.current)?.scrollIntoView({ block: target ? "center" : "end" });
  }, [data]);

  const changed = () => {
    reload();
    tags.reload();
    dataChanged();
  };
  const comment = async (body_md) => {
    await api.post(`/changes/${encodeURIComponent(change.key)}/posts`, { body_md });
    changed();
  };
  const postPeriod = async (period) => {
    await api.post(`/changes/${encodeURIComponent(change.key)}/periods`, period);
    showToast("Period posted.");
    changed();
  };

  if (error) return html`<div class="timeline"><p role="alert">${error.message}</p></div>`;
  if (!data) return html`<div class="timeline"><p class="muted">Loading…</p></div>`;
  const canWrite = data.can_comment || data.can_post_periods;
  const writeMode = data.can_post_periods ? (data.can_comment ? mode : "period") : "comment";
  const suggestions = tags.data ?? [];
  return html`
    <div class="conversation">
      <div class="timeline" aria-label="Conversation" aria-live="polite">
        ${data.items.length === 0 && html`<p class="timeline__empty">${periodsOnly ? "No periods yet." : "Nothing here yet."}</p>`}
        ${data.items.map((post) =>
          post.period
            ? html`<${PeriodPost} key=${post.id} post=${post} lookup=${lookup} today=${today} suggestions=${suggestions} onChanged=${changed} onHistory=${() => setHistoryOf(post.id)} />`
            : html`<${CommentPost} key=${post.id} post=${post} lookup=${lookup} uploadPath=${uploadPath} onChanged=${changed} onHistory=${() => setHistoryOf(post.id)} />`,
        )}
        <div ref=${bottom}></div>
      </div>
      ${canWrite &&
      html`<div class="change-composer">
        ${data.can_comment &&
        data.can_post_periods &&
        html`<div class="segmented segmented--small" role="group" aria-label="Post type">
          <button type="button" aria-pressed=${writeMode === "comment" ? "true" : "false"} onClick=${() => setMode("comment")}>Comment</button>
          <button type="button" aria-pressed=${writeMode === "period" ? "true" : "false"} onClick=${() => setMode("period")}>
            <span class="period-swatch period-swatch--test" aria-hidden="true"></span>Period
          </button>
        </div>`}
        ${writeMode === "period"
          ? html`<${PeriodForm} today=${today} suggestions=${suggestions} onSubmit=${postPeriod} />`
          : html`<${Composer} uploadPath=${uploadPath} allowUpdate=${false} onSubmit=${comment} />`}
      </div>`}
      <${HistoryDialog} postId=${historyOf} onClose=${() => setHistoryOf(null)} />
    </div>
  `;
}
