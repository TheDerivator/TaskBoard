/** Small full-page views: not found, login required, error, and views still to be built. */
import { LoginForm } from "../components/auth-dialogs.js";
import { useTitle } from "../hooks.js";
import { href } from "../router.js";
import { html } from "../ui.js";

export function NotFoundView() {
  useTitle("Not found");
  return html`
    <section class="center-page">
      <div class="center-card">
        <h1>Page not found</h1>
        <p class="muted">This address doesn't lead anywhere on the board.</p>
        <a class="btn" href=${href("priority")}>Go to the priority list</a>
      </div>
    </section>
  `;
}

export function LoginRequiredView() {
  useTitle("Log in");
  return html`
    <section class="center-page">
      <div class="center-card">
        <h1>Log in to see the board</h1>
        <p class="muted">This board is only visible to signed-in users.</p>
        <${LoginForm} />
      </div>
    </section>
  `;
}

export function ErrorView({ error, onRetry }) {
  useTitle("Error");
  return html`
    <section class="center-page">
      <div class="center-card" role="alert">
        <h1>Something went wrong</h1>
        <p class="muted">${error?.message ?? String(error)}</p>
        <button type="button" class="btn" onClick=${onRetry}>Try again</button>
      </div>
    </section>
  `;
}

export function ComingSoonView({ title, milestone }) {
  useTitle(title);
  return html`
    <section class="page">
      <header class="view-head">
        <div class="view-head__text"><h1>${title}</h1></div>
      </header>
      <div class="panel coming-soon">This view is built in milestone ${milestone}.</div>
    </section>
  `;
}
