/** Login form (dialog or full page) and the password-change dialog. */
import { api } from "../api.js";
import { windowsSignInMessage } from "../lib/signin.js";
import { refreshBoot, useAppState } from "../store.js";
import { html, useState } from "../ui.js";
import { windowsSignIn } from "../windows-signin.js";
import { Dialog } from "./dialog.js";
import { showToast } from "./toasts.js";

/**
 * "Sign in with Microsoft" etc.: a full-page redirect that returns to the current page.
 * "Sign in with Windows" stays on the page: the browser proves the Windows login in the background.
 */
function SsoButtons({ login, busy, onWindows }) {
  const providers = login?.providers ?? [];
  if (!providers.length && !login?.windows) return null;
  const next = location.pathname + location.search;
  return html`
    <div class="stack" style=${{ gap: "8px" }}>
      ${login.windows && html`<button type="button" class="btn" disabled=${busy} onClick=${onWindows}>Sign in with Windows</button>`}
      ${providers.map(
        (p) => html`<a
          key=${p.name}
          class="btn"
          href=${new URL(`api/auth/sso/${encodeURIComponent(p.name)}/start?next=${encodeURIComponent(next)}`, document.baseURI).href}
        >Sign in with ${p.display_name}</a>`,
      )}
      <p class="muted" style=${{ textAlign: "center", fontSize: "12px" }}>or with a TaskBoard account</p>
    </div>
  `;
}

/** Username + password form (plus SSO buttons when configured). Calls `onDone` after login. */
export function LoginForm({ onDone, autofocus = true }) {
  const { boot } = useAppState();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const attempt = async (signIn, describe = (err) => err.message) => {
    setBusy(true);
    setError(null);
    try {
      const me = await signIn();
      await refreshBoot();
      showToast(`Welcome, ${me.display_name}.`);
      onDone?.();
    } catch (err) {
      setError(describe(err));
    } finally {
      setBusy(false);
    }
  };

  const submit = (event) => {
    event.preventDefault();
    attempt(() => api.post("/auth/login", { username, password }));
  };

  return html`
    <form class="stack" onSubmit=${submit}>
      <${SsoButtons} login=${boot?.me.login} busy=${busy} onWindows=${() => attempt(windowsSignIn, windowsSignInMessage)} />
      ${error && html`<div class="form-error" role="alert">${error}</div>`}
      <label class="field">
        <span class="field__label">Username</span>
        <input
          class="input"
          name="username"
          autocomplete="username"
          required
          autofocus=${autofocus}
          value=${username}
          onInput=${(e) => setUsername(e.currentTarget.value)}
        />
      </label>
      <label class="field">
        <span class="field__label">Password</span>
        <input
          class="input"
          type="password"
          name="password"
          autocomplete="current-password"
          required
          value=${password}
          onInput=${(e) => setPassword(e.currentTarget.value)}
        />
      </label>
      <div class="dialog__actions">
        <button class="btn btn--primary" type="submit" disabled=${busy}>${busy ? "Logging in…" : "Log in"}</button>
      </div>
    </form>
  `;
}

export function LoginDialog({ open, onClose }) {
  return html`
    <${Dialog} open=${open} title="Log in" onClose=${onClose}>
      <${LoginForm} onDone=${onClose} />
    <//>
  `;
}

/** Shown (and not dismissible) while the account must set a new password. */
export function PasswordDialog({ open, required = false, onClose }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (next !== repeat) {
      setError("The new passwords are not the same.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/password", { current_password: current, new_password: next });
      await refreshBoot();
      showToast("Your password has been changed.");
      setCurrent("");
      setNext("");
      setRepeat("");
      onClose?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const field = (label, value, set, autocomplete) => html`
    <label class="field">
      <span class="field__label">${label}</span>
      <input
        class="input"
        type="password"
        autocomplete=${autocomplete}
        required
        value=${value}
        onInput=${(e) => set(e.currentTarget.value)}
      />
    </label>
  `;

  return html`
    <${Dialog} open=${open} title=${required ? "Choose a new password" : "Change password"} onClose=${onClose} dismissible=${!required}>
      <form class="stack" onSubmit=${submit}>
        ${required && html`<p class="muted">Your account needs a new password before you continue.</p>`}
        ${error && html`<div class="form-error" role="alert">${error}</div>`}
        ${field("Current password", current, setCurrent, "current-password")}
        ${field("New password (at least 10 characters)", next, setNext, "new-password")}
        ${field("New password again", repeat, setRepeat, "new-password")}
        <div class="dialog__actions">
          <button class="btn btn--primary" type="submit" disabled=${busy}>Save password</button>
        </div>
      </form>
    <//>
  `;
}
