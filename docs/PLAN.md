# TaskBoard: delivery plan

This file tracks the whole project. Each milestone lists deliverables (checkboxes) and an
**acceptance gate**: the automated checks that must pass before it counts as done. Update the
status table and the checkboxes as work lands. A new session starts by reading this file,
then [`CLAUDE.md`](../CLAUDE.md).

Design reference: [`team-tasks-design/`](../team-tasks-design/) (DESIGN.md + mockups + sample data).

## Status

| #   | Milestone                                   | Status        |
|-----|---------------------------------------------|---------------|
| M0  | Foundations and guardrails                  | ☑ done        |
| M1  | Domain model and persistence                | ☑ done        |
| M2  | Identity and access control core            | ☑ done        |
| M3  | Task and project API                        | ☑ done        |
| M4  | Frontend shell, design system, Priority (read) | ☑ done        |
| M5  | Priority interactions and task drawer       | ☑ done        |
| M6  | People and Projects views                   | ☑ done        |
| M7  | Conversation (posts, events, images)        | ☑ done        |
| M8  | Administration UI                           | ☑ done        |
| M9  | External identity provider (SSO)            | ☑ done        |
| M10 | Hardening, portability, release             | ◐ in progress (MS SQL run waiting for a database) |

Legend: ☐ not started · ◐ in progress · ☑ done

---

## Architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md) (stack, layers, data model, access control, SSO,
deployments, portability rules, recipes) and [`DECISIONS.md`](DECISIONS.md) (why).

---

## Milestones

### M0 · Foundations and guardrails
- [x] Dependencies via `uv add` (runtime) and `uv add --dev` (test/tooling).
- [x] Package skeleton with the layers above; `app.py` entrypoint; `python -m taskboard serve`.
- [x] Settings (`TASKBOARD_DATABASE_URL`, `TASKBOARD_DATA_DIR`, ...) with `.env.example`.
- [x] `GET /api/health`.
- [x] `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/CODEMAP.md` + generator.
- [x] `scripts/check.py`: ruff, format check, pyright, import-linter, pytest, node tests.

**Acceptance gate**: `uv run python scripts/check.py` is green; `uv run uvicorn app:app` answers
`/api/health` with 200; the CODEMAP staleness test and the layer contract pass.

### M1 · Domain model and persistence
- [x] SQLAlchemy models for everything in the data model, portable to MS SQL (see risks).
- [x] SQLite engine setup: `foreign_keys=ON`, WAL, busy timeout.
- [x] Alembic initial migration; `python -m taskboard db upgrade`.
- [x] Pure domain modules: ranking moves ("drop on row X" semantics from the mockup), outline
      numbering and subtree membership, lifecycle transitions, task-key generation/normalization.
- [x] `python -m taskboard seed` (built-in roles/users) and `seed --sample` (loads sample-data.json).

- [x] Beyond plan: write transactions (`BEGIN IMMEDIATE` on SQLite) and portable lock rows
      (`app_locks`) so concurrent re-ranking cannot corrupt the dense ranking.
- [x] Beyond plan: `UTCDateTime` type (aware UTC in Python, DATETIME2 on MS SQL), MS SQL DDL
      verified offline (NVARCHAR(max), filtered unique indexes).

**Acceptance gate**: unit tests for ranking (incl. property-based tests: a move always yields a
permutation, only the moved task changes relative order), numbering (`ASQ:2.2.1` → `2.2.1`),
subtree counts, task keys (alphabet, normalization, retry on collision); integration tests proving the DB rejects a second placement in the same project and
a node from another project; `alembic check` reports models and migrations in sync; seeding twice is
idempotent; sample data round-trips.

### M2 · Identity and access control core
- [x] Permission catalog, built-in roles, scoped assignments, anonymous and admin users.
- [x] Principal resolution: session cookie → user, else anonymous.
- [x] `AccessPolicy` (`can`, visible-section filter).
- [x] Local login/logout/me endpoints, argon2 hashing, server-side sessions, CSRF protection
      (SameSite cookies + double-submit header on unsafe methods).
- [x] Internet-ready basics (the demo server): login throttling per account and IP, `Secure`
      cookies when served over HTTPS, change-own-password, forced password change for the
      generated initial admin password.
- [x] `IdentityProvider` protocol, local provider, provisioning service, audit log.
- [x] `docs/AUTH.md`.

- [x] Beyond plan: emails/usernames normalized in the models (every entry path), the anonymous
      rights act as a floor for logged-in users, built-in accounts are never linked by SSO email.

**Acceptance gate**: a policy matrix test (admin / section editor / department editor / viewer /
anonymous / suspended × view / edit / comment / manage) passes; anonymous can view by default and
cannot after an admin removes its assignment; a suspended user's existing session is refused on
the next request; a state-changing request without the CSRF header gets 403; repeated failed
logins are throttled; a fake external provider logs in a pre-provisioned email and receives exactly
the pre-assigned rights; with no provider configured, no SSO route exists.

### M3 · Task and project API
- [x] `GET /api/bootstrap` (me, permissions, departments/sections, people, projects + trees).
- [x] Tasks: list with filters (`q`, statuses, department, section, project, person + role),
      get by key (`/api/tasks/T-K7Q2MX`, case-insensitive, prefix optional), create, update
      (optimistic `version` → 409 on conflict), move (`before`/`after` a target).
- [x] Lifecycle, lead and helper changes write events.
- [x] Placements: add, move, remove. Projects and nodes: CRUD, reorder, re-parent (no cycles).
- [x] Project outline endpoint (subtree, counts incl. descendants, archived toggle).
- [x] People list. OpenAPI UI at `/api/docs`.

- [x] Beyond plan: `task.delete` permission (Administrators only by default), Unicode-aware
      case-insensitive search on every backend, concurrent re-ranking test (4 clients × 15 moves),
      `taskboard/schemas/` layer shared by services and API.

**Acceptance gate**: API tests for every endpoint, including 401/403 for each permission, 422 for
invalid input, 409 for stale versions; "filters never change rank" and "search matches title +
description, case-insensitive" tested explicitly; outline for the sample data matches the mockup.

### M4 · Frontend shell, design system, Priority view (read-only)
- [x] Vendored fonts and libraries; design tokens as CSS custom properties.
- [x] Light/dark theme toggle (follows the OS by default, choice remembered).
- [x] Collapsible sidebar (icon rail when collapsed, choice remembered); layout works on narrow screens.
- [x] History-API router (`/priority`, `/people`, `/projects/ASQ/2.1`, `/t/K7Q2MX`) with a server
      fallback that serves the app for those paths; API client
      with CSRF header, error toasts, login dialog, current user in the sidebar.
- [x] Priority view: ranked list, search, lifecycle chips (default hides Archived), department /
      section / project filters, placement chips.

- [x] Beyond plan: `TASKBOARD_BASE_PATH` for publishing under a URL prefix (IIS/nginx), static
      files revalidated on every load, JS/CSS/HTML files must describe themselves (code map test),
      phone layout with an off-canvas menu.

**Acceptance gate**: `node --test` for pure JS modules (filtering, formatting, routing);
Playwright: page loads, filters work, theme and sidebar state survive a reload, and **the page makes
no request to any other origin**.

### M5 · Priority interactions and task drawer
- [x] Drag-and-drop reordering in filtered lists (pointer events: mouse and touch).
- [x] New task; drawer Details tab: title, description, lifecycle picker, department/section,
      lead picker, helpers add/remove, placements with Move/Remove.
- [x] "Add to another project" dialog (step 1 project, already-used ones disabled; step 2 node or top level).
- [x] Task page at `/t/{key}` (the permalink; same content as the drawer, full width), "Copy link"
      in the drawer, login returns to the requested URL, friendly "not found / no access" page.
- [x] Read-only drawer for users without edit rights; stale-edit (409) handling.

- [x] Beyond plan: optimistic reordering (rolled back on error), unsaved-changes guard on every
      way of closing the drawer, Delete for users with `task.delete`, lifecycle picker marks the
      stages already passed.

**Acceptance gate**: Playwright: drag a row, reload, the order persists; edit and save a task;
the placement dialog disables projects the task is already in; a viewer cannot edit; opening
`/t/{key}` in a fresh browser shows that task (after login if anonymous access is off).

### M6 · People and Projects views
- [x] People lanes: lead (solid) / helping (dashed), "Lead + helping" / "Lead only", search,
      drag within a lane reorders globally.
- [x] Projects: tree with counts, outline with numbering, breadcrumb, header summary and lead
      avatars, "also in …", Show archived, Add task here, New project, Edit sections
      (add, rename, reorder, indent/outdent, delete).

- [x] Beyond plan: project settings in the section editor (rename, colour, archive, delete),
      "Show archived" on the People view, lanes scroll horizontally when there are many people.

**Acceptance gate**: API and Playwright tests reproduce the counts and numbering from the mockups
for the sample data; editing sections renumbers the outline.

### M7 · Conversation
- [x] Posts in Markdown, rendered and sanitized server-side; `@mentions` highlighted; task keys
      (`T-K7Q2MX`) linked to their permalink; update posts highlighted; "Updates only" filter.
- [x] Events interleaved with posts in time order.
- [x] Composer: Write/Preview, toolbar (bold, italic, list, code, link), image attach by button,
      paste or drop; uploads stored under the data dir, served only to users who can view the task.
- [x] Edit/delete own posts.
- [x] Deleting a task also removes its attachment files from disk (the rows already go in M3).

- [x] Beyond plan: the sample's defect map is a generated image attachment, images verified by
      their bytes (SVG refused), unposted draft uploads cleaned up after a day, a draft's unsaved
      edits survive background reloads, Ctrl+Enter posts.

**Acceptance gate**: sanitizer tests with XSS vectors; upload type and size limits; attachment
access follows task visibility; Playwright: post an update with an image, it renders.

### M8 · Administration UI
- [x] Users: list, create local user, suspend/reactivate, reset password, pre-provision external user.
- [x] Role assignments per scope, anonymous access settings.
- [x] Reference data: departments/sections, people (incl. link to user), projects.
- [x] Audit log viewer.

- [x] Beyond plan: custom roles with a permission picker, a guard that keeps at least one active
      administrator, generated passwords shown once, people deactivated rather than deleted.

**Acceptance gate**: API + Playwright: an admin suspends a user and that user's open session stops
working; revoking anonymous view makes the board require login; a non-admin cannot reach admin APIs.

### M9 · External identity provider (SSO)
- [x] Microsoft Entra ID via OIDC as the first concrete provider (Windows server target). Built on
      PyJWT + the standard library instead of Authlib (D-056).
- [x] Trusted-header provider (IIS / reverse proxy passing the authenticated user) as a fallback.
- [x] Optional IdP-group → role mappings (Administration › SSO groups).
- [x] Configuration guide for Entra ID and IIS in [`AUTH.md`](AUTH.md).

- [x] Beyond plan: the app reads `X-Forwarded-For/-Proto` itself from `TASKBOARD_TRUSTED_PROXIES`
      (Uvicorn's default proxy handling would have hidden IIS's address and silently disabled
      Windows sign-in; D-061). Windows-signed-in visitors see no "Log out" (D-062).
- [x] Beyond plan: pre-provisioned accounts also match on the Windows login name (no email
      needed); SSO sign-in returns to the page it started from.

**Acceptance gate**: tests against an in-process mock IdP: a pre-provisioned account logs in and
gets its rights; an unknown account is handled per config; a suspended account is refused.
Met: `tests/api/test_oidc.py` (real PKCE, signed tokens, key rotation, replay, open redirects),
`test_trusted_header.py`, `test_sso_provisioning.py`, `tests/unit/test_forwarded_headers.py`, and
`tests/e2e/test_sso.py` (a real browser round trip through a local fake provider). Not tried
against a real Entra ID tenant or IIS: that needs your environment (M10 deployment guide).

### M10 · Hardening, portability, release
- [ ] Run the integration suite against MS SQL. **Waiting for a SQL Server database** (none here,
      no Docker). Ready: `TASKBOARD_TEST_DATABASE_URL` points the API + integration suites at any
      database (proved with a second SQLite database: 203 pass), and the driver is the optional
      extra `mssql` (pyodbc 5.3). Command in [`OPERATIONS.md`](OPERATIONS.md#ms-sql-later).
- [x] Keyboard reordering (DESIGN rule 8: "later") on the Priority grip; accessibility pass
      with axe-core in Playwright: every view, dialog and drawer, light and dark (D-066, D-067).
- [x] Strict CSP (no inline scripts except the import map, by hash), security headers (D-063).
- [x] Performance check with 5,000 tasks (API and browser tests with time limits; D-064, D-065);
      backup/restore command (D-068).
- [x] Deployment guides in [`OPERATIONS.md`](OPERATIONS.md): (a) Windows server: WinSW service,
      IIS reverse proxy, `C:\ProgramData\TaskBoard`, MS SQL; (b) Linux demo: systemd, Caddy or
      nginx, `/var/lib/taskboard`, demo-data seeding; backups, restore, upgrades. Not yet tried
      on real servers. Step-by-step IIS walkthrough for IIS beginners in [`IIS.md`](IIS.md)
      (also IIS starting TaskBoard through HttpPlatformHandler, without a service).
- [ ] Optional: live refresh when others change the board (polling or SSE). Not started: the
      board refreshes on your own changes and on reload.

**Acceptance gate**: the full suite passes on SQLite (✔) and on MS SQL (waiting for a database);
axe finds no violations (✔); the app runs under a strict CSP with no console errors (✔).

---

## Plan evaluation

**Ordering.** Access control (M2) comes before the API (M3) on purpose: retrofitting authorization
into existing endpoints is where permission bugs come from. The cost is that nothing is visible in
a browser until M4; `/api/docs` gives an interactive surface from M3 on.

**Risks and mitigations**

1. *MS SQL portability.* Known traps: `VARCHAR` loses non-Latin characters (use `Unicode` types:
   "Chloé"); MS SQL refuses multiple/cyclic cascade paths (no DB-level `ON DELETE CASCADE` on
   `project_nodes.parent_id`; deletes happen in services); indexed strings need explicit lengths;
   default collation is case-insensitive (uniqueness of codes and emails is normalized in code);
   explicit identity inserts (avoided: public task keys are separate from the surrogate PK). The suite is written to run
   against any URL, but it cannot be *proved* without a SQL Server instance (M10).
2. *Concurrent reordering.* A move is one transaction that shifts a contiguous rank range. Rank is
   dense `1..N` over all tasks including archived ones, which matches the mockup ("Rank 01 of 11").
3. *Restricted viewers and global ranks.* Gaps in visible rank numbers are expected, not a bug.
4. *Drag-and-drop on touch.* Native HTML5 drag-and-drop does not work on touch screens, so it's
   built on pointer events. Keyboard reordering follows in M10.
5. *Scope creep in admin screens.* The mockups don't cover admin UI; it reuses the same visual
   language with plain forms and tables.

**Assumptions I'm making (flagged; say if any is wrong)**

- A1. *Person* (someone on the board) and *User* (a login account) are separate, optionally
  linked 1:1, matched by email. The built-in admin and anonymous accounts are not people, and
  people who never log in can still lead tasks.
- A2. Task and person store only the section; the department follows from it.
- A3. Creating/editing projects and their section trees needs `project.manage`: admins by default,
  and admins can grant it through a custom role.
- A4. Posting in a conversation needs `task.comment` (in *Editor*); pure viewers read only.
- A5. Changing a task's section requires edit rights on both the old and the new section.
- A6. In the People view, dragging reorders within a lane (global rank); dragging across lanes
  (reassigning) is not supported.
- A7. Deleting a project node moves its tasks' placements to the parent node (confirmed in the UI).
- A8. `@mentions` are highlighted only: no notifications in scope.
- A9. English-only UI.

## Decisions (session 1)

Recorded in detail in `docs/DECISIONS.md`.

- Q1 → Permission scopes are **organizational sections** (Department › Section), with department
  and global scope as shortcuts.
- Q2 → **FastAPI** (not Shiny, although DESIGN.md mentions it).
- Q3 → **Two deployments**: a corporate Windows server (built-in accounts + SSO later, first
  provider Microsoft Entra ID via OIDC) and a Linux demo server (built-in accounts only, no SSO).
- Q4 → **JSON API + Preact/htm** static frontend, no build step.
- New requirement → every task has a **short unique key** and a **permalink** `/t/{key}`.
