/** Left navigation: views with counts, projects, the signed-in user, theme and collapse toggles. */
import { api } from "../api.js";
import { projectPath } from "../lib/routes.js";
import { findTeam, teamPath } from "../lib/teams.js";
import { href } from "../router.js";
import { refreshBoot } from "../store.js";
import { useTheme } from "../theme.js";
import { html } from "../ui.js";
import { holdWindowsSignIn } from "../windows-signin.js";
import { Avatar } from "./badges.js";
import { adminTabs } from "../views/admin/index.js";
import {
  AdminIcon,
  CollapseIcon,
  ExpandIcon,
  LoginIcon,
  LogoIcon,
  LogoutIcon,
  MoonIcon,
  PeopleIcon,
  PriorityIcon,
  ProjectsIcon,
  SunIcon,
} from "./icons.js";
import { showError, showToast } from "./toasts.js";

// "People" returns to the team shown last during this visit (like the filters; a reload forgets it).
let peopleLink = "people";

function NavItem({ path, label, icon, count, current }) {
  return html`
    <a class="nav-item" href=${href(path)} aria-current=${current ? "page" : undefined} title=${label}>
      <span class="nav-item__icon">${icon}</span>
      <span class="nav-item__label">${label}</span>
      ${count != null && html`<span class="nav-item__count">${count}</span>`}
    </a>
  `;
}

function UserBlock({ boot, lookup, onLogin, collapsed }) {
  const me = boot.me;
  if (me.is_anonymous) {
    return html`
      <button type="button" class="sidebar__login" onClick=${onLogin} title="Log in">
        <${LoginIcon} /><span class="sidebar__login-label">Log in</span>
      </button>
    `;
  }
  const person = lookup.personForUser;
  const section = person ? lookup.sections.get(person.section_id) : null;
  const department = section ? lookup.departments.get(section.department_id) : null;
  const meta = department ? `${department.code} · ${section.name}` : `@${me.username}`;
  const via = me.signed_in_by ? `Signed in through ${me.signed_in_by}` : null;
  const title = collapsed ? [`${me.display_name} (${meta})`, via].filter(Boolean).join("\n") : via;
  return html`
    <div class="sidebar__user" title=${title ?? undefined}>
      <${Avatar} person=${person} name=${me.display_name} />
      <div class="sidebar__user-text">
        <span class="sidebar__user-name">${me.display_name}</span>
        <span class="sidebar__user-meta">${meta}</span>
      </div>
    </div>
  `;
}

export function Sidebar({ boot, lookup, route, collapsed, onToggleCollapsed, onLogin }) {
  const [theme, toggleTheme] = useTheme();
  const selectedProject = route.name === "projects" ? route.params.key : null;

  const logout = async () => {
    try {
      await api.post("/auth/logout");
      holdWindowsSignIn();
      await refreshBoot();
      showToast("You are logged out.");
    } catch (error) {
      showError(error);
    }
  };

  const activePeople = boot.people.filter((p) => p.active).length;
  const team = route.name === "people" ? findTeam(boot.departments, route.params) : null;
  if (team) peopleLink = teamPath(team);
  return html`
    <nav class="sidebar" aria-label="Main">
      <div class="sidebar__brand">
        <a class="sidebar__logo" href=${href("priority")} aria-label="Team Tasks home"><${LogoIcon} /></a>
        <span class="sidebar__name">Team Tasks</span>
        <button
          type="button"
          class="rail-button collapse-toggle"
          aria-label=${collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-pressed=${collapsed ? "true" : "false"}
          title=${collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick=${onToggleCollapsed}
        >
          ${collapsed ? html`<${ExpandIcon} />` : html`<${CollapseIcon} />`}
        </button>
      </div>

      <div class="sidebar__group">
        <div class="sidebar__heading">Views</div>
        <${NavItem} path="priority" label="Priority" icon=${html`<${PriorityIcon} />`} count=${boot.task_total} current=${route.name === "priority"} />
        <${NavItem} path=${peopleLink} label="People" icon=${html`<${PeopleIcon} />`} count=${activePeople} current=${route.name === "people"} />
        <${NavItem}
          path="projects"
          label="Projects"
          icon=${html`<${ProjectsIcon} />`}
          count=${boot.projects.length}
          current=${route.name === "projects"}
        />
      </div>

      ${adminTabs(boot.me).length > 0 &&
      html`
        <div class="sidebar__group">
          <${NavItem}
            path=${`admin/${adminTabs(boot.me)[0].tab}`}
            label="Administration"
            icon=${html`<${AdminIcon} />`}
            current=${route.name === "admin"}
          />
        </div>
      `}

      ${boot.projects.length > 0 &&
      html`
        <div class="sidebar__group sidebar__group--projects">
          <div class="sidebar__heading">Projects</div>
          ${boot.projects
            .filter((p) => !p.archived)
            .map(
              (p) => html`
                <a
                  key=${p.id}
                  class="nav-item nav-item--project"
                  href=${href(projectPath(p.key))}
                  aria-current=${selectedProject === p.key ? "true" : undefined}
                  title=${p.name}
                  style=${{ "--project-color": p.color }}
                >
                  <span class="project-dot"></span>
                  <span class="nav-item__label">${p.name}</span>
                </a>
              `,
            )}
        </div>
      `}

      <div class="sidebar__footer">
        <${UserBlock} boot=${boot} lookup=${lookup} onLogin=${onLogin} collapsed=${collapsed} />
        <div class="sidebar__tools">
          <button
            type="button"
            class="rail-button"
            onClick=${toggleTheme}
            aria-label=${theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            title=${theme === "dark" ? "Light theme" : "Dark theme"}
            data-testid="theme-toggle"
          >
            ${theme === "dark" ? html`<${SunIcon} />` : html`<${MoonIcon} />`}
          </button>
          ${!boot.me.is_anonymous &&
          !boot.me.signed_in_by &&
          html`<button type="button" class="rail-button" onClick=${logout} aria-label="Log out" title="Log out">
            <${LogoutIcon} />
          </button>`}
        </div>
      </div>
    </nav>
  `;
}
