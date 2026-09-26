/** The application: loads the bootstrap document, lays out sidebar + view, routes, dialogs. */
import { LoginDialog, PasswordDialog } from "./components/auth-dialogs.js";
import { MenuIcon } from "./components/icons.js";
import { Sidebar } from "./components/sidebar.js";
import { Toasts, showError } from "./components/toasts.js";
import { canSomewhere } from "./lib/lookup.js";
import { readPref, writePref } from "./prefs.js";
import { navigate, useRoute } from "./router.js";
import { refreshBoot, useAppState } from "./store.js";
import { html, useEffect, useState } from "./ui.js";
import { AdminView } from "./views/admin/index.js";
import { PeopleView } from "./views/people.js";
import { PriorityView } from "./views/priority.js";
import { ProjectsView } from "./views/projects.js";
import { ComingSoonView, ErrorView, LoginRequiredView, NotFoundView } from "./views/simple.js";
import { TaskDrawer, TaskPage } from "./views/task.js";

/** A task opened from a list shows as a drawer over that list; opened directly, as its own page. */
function TaskRoute({ route, background, boot, lookup }) {
  const { key, tab } = route.params;
  if (!background) return html`<${TaskPage} key=${key} taskKey=${key} tab=${tab} />`;
  return html`
    <${View} route=${background} boot=${boot} lookup=${lookup} />
    <${TaskDrawer} key=${key} taskKey=${key} tab=${tab} onClose=${() => history.back()} />
  `;
}

function View({ route, boot, lookup, background = null }) {
  if (!boot.me.is_anonymous && boot.me.must_change_password) {
    return html`<section class="page"></section>`;
  }
  if (!canSomewhere(boot.me, "task.view")) {
    return boot.me.is_anonymous
      ? html`<${LoginRequiredView} />`
      : html`<${ComingSoonView} title="No access yet" milestone="M8 (ask an administrator for access)" />`;
  }
  switch (route.name) {
    case "priority":
      return html`<${PriorityView} boot=${boot} lookup=${lookup} />`;
    case "people":
      return html`<${PeopleView} boot=${boot} lookup=${lookup} />`;
    case "projects":
      return html`<${ProjectsView} boot=${boot} lookup=${lookup} route=${route} />`;
    case "admin":
      return html`<${AdminView} boot=${boot} lookup=${lookup} route=${route} />`;
    case "task":
      return html`<${TaskRoute} route=${route} background=${background} boot=${boot} lookup=${lookup} />`;
    case "home":
      return null;
    default:
      return html`<${NotFoundView} />`;
  }
}

export function App() {
  const { status, boot, lookup, error } = useAppState();
  const route = useRoute();
  const [collapsed, setCollapsed] = useState(() => readPref("sidebar.collapsed", false));
  const [navOpen, setNavOpen] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [background, setBackground] = useState(null); // the list view a task drawer opens over

  useEffect(() => {
    refreshBoot();
    // A failed SSO sign-in comes back as ?sso_error=...: show it once, then tidy the address.
    const url = new URL(location.href);
    const ssoError = url.searchParams.get("sso_error");
    if (ssoError) {
      showError(new Error(`Sign-in failed: ${ssoError}`));
      url.searchParams.delete("sso_error");
      history.replaceState(null, "", url.pathname + url.search);
    }
  }, []);

  useEffect(() => {
    if (route.name === "home") navigate("priority", { replace: true });
    else if (route.name !== "task") setBackground(route.name === "notFound" ? null : route);
    setNavOpen(false);
  }, [route]);

  useEffect(() => {
    if (!navOpen) return undefined;
    const onKey = (event) => event.key === "Escape" && setNavOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navOpen]);

  const toggleCollapsed = () => {
    writePref("sidebar.collapsed", !collapsed);
    setCollapsed(!collapsed);
  };

  if (status === "loading") return html`<div class="center-page muted">Loading…</div>`;
  if (status === "error" && !boot) return html`<${ErrorView} error=${error} onRetry=${refreshBoot} />`;

  const mustChangePassword = !boot.me.is_anonymous && boot.me.must_change_password;
  const classes = ["app", collapsed && "is-collapsed", navOpen && "nav-open"].filter(Boolean).join(" ");
  return html`
    <div class=${classes}>
      <${Sidebar}
        boot=${boot}
        lookup=${lookup}
        route=${route}
        collapsed=${collapsed}
        onToggleCollapsed=${toggleCollapsed}
        onLogin=${() => setLoginOpen(true)}
      />
      ${navOpen && html`<div class="scrim" onClick=${() => setNavOpen(false)}></div>`}
      <div class="main">
        <header class="topbar">
          <button type="button" class="icon-btn" aria-label="Open navigation" onClick=${() => setNavOpen(true)}>
            <${MenuIcon} />
          </button>
          <span class="topbar__title">Team Tasks</span>
        </header>
        <main id="content" class="content">
          <${View} route=${route} boot=${boot} lookup=${lookup} background=${background} />
        </main>
      </div>
      <${LoginDialog} open=${loginOpen} onClose=${() => setLoginOpen(false)} />
      <${PasswordDialog}
        open=${mustChangePassword || passwordOpen}
        required=${mustChangePassword}
        onClose=${() => setPasswordOpen(false)}
      />
      <${Toasts} />
    </div>
  `;
}
