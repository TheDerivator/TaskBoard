/** The application: loads the bootstrap document, lays out sidebar + view, routes, dialogs. */
import { LoginDialog, PasswordDialog } from "./components/auth-dialogs.js";
import { MenuIcon } from "./components/icons.js";
import { SearchDialog } from "./components/search-dialog.js";
import { Sidebar } from "./components/sidebar.js";
import { Toasts, showError } from "./components/toasts.js";
import { homeRoute, routeAllowed } from "./lib/access.js";
import { readPref, writePref } from "./prefs.js";
import { navigate, useRoute } from "./router.js";
import { refreshBoot, startUp, useAppState } from "./store.js";
import { html, useEffect, useState } from "./ui.js";
import { AdminView } from "./views/admin/index.js";
import { ChangeDrawer, ChangePage } from "./views/changes/change.js";
import { ChangesView } from "./views/changes/index.js";
import { BoxLinkView } from "./views/knowledge/box-link.js";
import { KnowledgeView } from "./views/knowledge/index.js";
import { PeopleView } from "./views/people.js";
import { PriorityView } from "./views/priority.js";
import { ProjectsView } from "./views/projects.js";
import { ErrorView, LoginRequiredView, NoAccessView, NotFoundView } from "./views/simple.js";
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

/** The same for a process change: a drawer over the list it was opened from, else its own page. */
function ChangeRoute({ route, background, boot, lookup }) {
  const { key, tab } = route.params;
  if (!background) return html`<${ChangePage} key=${key} changeKey=${key} tab=${tab} route=${route} />`;
  return html`
    <${View} route=${background} boot=${boot} lookup=${lookup} />
    <${ChangeDrawer} key=${key} changeKey=${key} tab=${tab} route=${route} onClose=${() => history.back()} />
  `;
}

const DETAIL_ROUTES = new Set(["task", "change"]); // drawers over the list view they came from

function View({ route, boot, lookup, background = null }) {
  if (!boot.me.is_anonymous && boot.me.must_change_password) {
    return html`<section class="page"></section>`;
  }
  if (!routeAllowed(boot.me, route.name)) {
    return boot.me.is_anonymous
      ? html`<${LoginRequiredView} />`
      : html`<${NoAccessView} />`;
  }
  switch (route.name) {
    case "priority":
      return html`<${PriorityView} boot=${boot} lookup=${lookup} />`;
    case "people":
      return html`<${PeopleView} boot=${boot} lookup=${lookup} route=${route} />`;
    case "projects":
      return html`<${ProjectsView} boot=${boot} lookup=${lookup} route=${route} />`;
    case "admin":
      return html`<${AdminView} boot=${boot} lookup=${lookup} route=${route} />`;
    case "changes":
      return html`<${ChangesView} boot=${boot} lookup=${lookup} route=${route} />`;
    case "change":
      return html`<${ChangeRoute} route=${route} background=${background} boot=${boot} lookup=${lookup} />`;
    case "knowledge":
    case "fmea":
    case "cpl":
      return html`<${KnowledgeView} boot=${boot} lookup=${lookup} route=${route} />`;
    case "box":
      return html`<${BoxLinkView} lookup=${lookup} route=${route} />`;
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
  const [searchOpen, setSearchOpen] = useState(false);
  const [background, setBackground] = useState(null); // the list view a task drawer opens over

  useEffect(() => {
    startUp().then((refusal) => refusal && showError(new Error(`Windows sign-in: ${refusal.message}`)));
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
    if (route.name === "home" && boot) navigate(homeRoute(boot.me), { replace: true });
    else if (!DETAIL_ROUTES.has(route.name)) setBackground(route.name === "notFound" ? null : route);
    setNavOpen(false);
  }, [route, boot]);

  // Ctrl K (Cmd K on a Mac) opens "Search everything" from anywhere (DESIGN "Global search").
  useEffect(() => {
    const onKey = (event) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setNavOpen(false);
        setSearchOpen(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

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
        onSearch=${() => {
          setNavOpen(false);
          setSearchOpen(true);
        }}
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
      <${SearchDialog} open=${searchOpen} onClose=${() => setSearchOpen(false)} />
      <${PasswordDialog}
        open=${mustChangePassword || passwordOpen}
        required=${mustChangePassword}
        onClose=${() => setPasswordOpen(false)}
      />
      <${Toasts} />
    </div>
  `;
}
