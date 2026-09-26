/** The Conversation tab: events and posts in time order, own-post editing, and the composer. */
import { api } from "../api.js";
import { useApi } from "../hooks.js";
import { describeEvent } from "../lib/events.js";
import { formatDate } from "../lib/format.js";
import { dataChanged } from "../store.js";
import { html, useEffect, useRef, useState } from "../ui.js";
import { Avatar } from "./badges.js";
import { Composer } from "./composer.js";
import { showError, showToast } from "./toasts.js";

const ArrowIcon = () => html`
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
`;

function EventLine({ event, lookup }) {
  const { actor, text } = describeEvent(event, lookup);
  return html`
    <div class="event-line">
      <${ArrowIcon} />
      <span><strong>${actor}</strong> ${text}</span>
      <time datetime=${event.created_at}>${formatDate(event.created_at)}</time>
    </div>
  `;
}

function PostItem({ post, lookup, taskKey, onChanged }) {
  const [editing, setEditing] = useState(false);
  const person = post.author.person_id != null ? lookup.people.get(post.author.person_id) : null;

  const save = async (body_md, is_update) => {
    await api.patch(`/posts/${post.id}`, { body_md, is_update });
    setEditing(false);
    onChanged();
  };
  const remove = async () => {
    if (!window.confirm("Delete this post?")) return;
    try {
      await api.delete(`/posts/${post.id}`);
      showToast("Post deleted.");
      onChanged();
    } catch (err) {
      showError(err);
    }
  };

  // Images open full size in a new tab.
  const onClick = (event) => {
    const image = event.target.closest?.("img");
    if (image) window.open(image.src, "_blank", "noopener");
  };

  return html`
    <article class=${`post${post.is_update ? " post--update" : ""}`} aria-label=${`Post by ${post.author.display_name}`}>
      <${Avatar} person=${person} name=${post.author.display_name} />
      <div class="post__main">
        <div class="post__head">
          <span class="post__author">${post.author.display_name}</span>
          ${post.is_update && html`<span class="update-badge">Update</span>`}
          <time class="post__time" datetime=${post.created_at} title=${post.edited_at ? `Edited ${formatDate(post.edited_at, { withTime: true })}` : undefined}>
            ${formatDate(post.created_at, { withTime: true })}${post.edited_at ? " · edited" : ""}
          </time>
          ${post.can_edit &&
          !editing &&
          html`<span class="post__actions">
            <button type="button" class="link-button" onClick=${() => setEditing(true)}>Edit</button>
            <button type="button" class="link-button" onClick=${remove}>Delete</button>
          </span>`}
        </div>
        ${editing
          ? html`<${Composer}
              taskKey=${taskKey}
              initial=${{ body_md: post.body_md, is_update: post.is_update }}
              submitLabel="Save"
              onSubmit=${save}
              onCancel=${() => setEditing(false)}
            />`
          : html`<div class="md" onClick=${onClick} dangerouslySetInnerHTML=${{ __html: post.html }}></div>`}
      </div>
    </article>
  `;
}

/**
 * @param {{taskKey: string, lookup: object, updatesOnly: boolean, onCount: (n: number) => void}} props
 */
export function ConversationPanel({ taskKey, lookup, updatesOnly, onCount }) {
  const { data, error, reload } = useApi(`/tasks/${encodeURIComponent(taskKey)}/conversation`, {
    updates_only: updatesOnly,
  });
  const bottom = useRef(null);

  useEffect(() => {
    if (!data) return;
    onCount?.(data.post_count);
    bottom.current?.scrollIntoView({ block: "end" });
  }, [data]);

  const changed = () => {
    reload();
    dataChanged();
  };
  const post = async (body_md, is_update) => {
    await api.post(`/tasks/${taskKey}/posts`, { body_md, is_update });
    changed();
  };

  if (error) return html`<div class="timeline"><p role="alert">${error.message}</p></div>`;
  if (!data) return html`<div class="timeline"><p class="muted">Loading…</p></div>`;
  return html`
    <div class="conversation">
      <div class="timeline" aria-label="Conversation" aria-live="polite">
        ${data.items.length === 0 &&
        html`<p class="timeline__empty">${updatesOnly ? "No status updates yet." : "Nothing here yet."}</p>`}
        ${data.items.map((item) =>
          item.type === "event"
            ? html`<${EventLine} key=${`e${item.id}`} event=${item} lookup=${lookup} />`
            : html`<${PostItem} key=${`p${item.id}`} post=${item} lookup=${lookup} taskKey=${taskKey} onChanged=${changed} />`,
        )}
        <div ref=${bottom}></div>
      </div>
      ${data.can_comment && html`<${Composer} taskKey=${taskKey} onSubmit=${post} />`}
    </div>
  `;
}
