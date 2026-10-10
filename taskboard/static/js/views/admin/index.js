/** Administration: tabs for accounts, roles, organization, people, SSO groups, the audit log and backups. */
import { useTitle } from "../../hooks.js";
import { href } from "../../router.js";
import { html } from "../../ui.js";
import { AuditTab } from "./audit.js";
import { BackupsTab } from "./backups.js";
import { GroupsTab } from "./groups.js";
import { OrganizationTab } from "./organization.js";
import { PeopleTab } from "./people.js";
import { RolesTab } from "./roles.js";
import { UsersTab } from "./users.js";

const TABS = [
  { tab: "users", label: "Accounts", permission: "users.manage", view: UsersTab },
  { tab: "roles", label: "Roles", permission: "users.manage", view: RolesTab },
  { tab: "organization", label: "Organization", permission: "people.manage", view: OrganizationTab },
  { tab: "people", label: "People", permission: "people.manage", view: PeopleTab },
  { tab: "groups", label: "SSO groups", permission: "users.manage", view: GroupsTab },
  { tab: "audit", label: "Audit log", permission: "users.manage", view: AuditTab },
  { tab: "backups", label: "Backups", permission: "users.manage", view: BackupsTab },
];

/** Tabs the user may open (the manage permissions only count when granted everywhere). */
export function adminTabs(me) {
  return TABS.filter((t) => me.permissions[t.permission]?.everywhere);
}

export function AdminView({ boot, lookup, route }) {
  useTitle("Administration");
  const tabs = adminTabs(boot.me);
  const current = tabs.find((t) => t.tab === route.params.tab) ?? tabs[0];
  if (!current) {
    return html`<section class="page"><div class="panel empty-state">You have no administration rights.</div></section>`;
  }
  const View = current.view;
  return html`
    <section class="page" aria-labelledby="admin-title">
      <header class="view-head">
        <div class="view-head__text"><h1 id="admin-title">Administration</h1></div>
      </header>
      <nav class="admin-tabs" aria-label="Administration sections">
        ${tabs.map(
          (t) => html`<a key=${t.tab} href=${href(`admin/${t.tab}`)} aria-current=${t === current ? "page" : undefined}>${t.label}</a>`,
        )}
      </nav>
      <${View} boot=${boot} lookup=${lookup} />
    </section>
  `;
}
