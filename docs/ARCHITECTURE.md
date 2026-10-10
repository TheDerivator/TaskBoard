# Architecture

How TaskBoard is put together, and the rules that keep it that way. Progress and milestones are in
[`PLAN2.md`](PLAN2.md) (current: process changes, process knowledge, search) and
[`PLAN.md`](PLAN.md) (the original build); the reasons behind choices are in
[`DECISIONS.md`](DECISIONS.md); a file-by-file map is in [`CODEMAP.md`](CODEMAP.md) (generated).

## Stack

| Concern | Choice | Why |
|---|---|---|
| Web framework | FastAPI on Uvicorn (ASGI) | Typed request/response models, OpenAPI docs for free, easy testing. |
| ORM + migrations | SQLAlchemy 2.1 (typed `Mapped[]`, sync) + Alembic | Mature MS SQL support via `pyodbc`; sync code is simpler and FastAPI runs sync endpoints in a thread pool. |
| Config | `pydantic-settings`, env vars prefixed `TASKBOARD_` | One typed settings object; `.env` for development. |
| Passwords | argon2 (`argon2-cffi`) | Current best practice. |
| Markdown | Server-side `markdown-it-py` + `nh3` sanitizer | One renderer, tested in Python; the browser only receives sanitized HTML. The editor's Preview uses the same endpoint. |
| Frontend | Static ES modules, **no build step**; Preact + htm (vendored, ~5 KB gz) | Readable components that escape output by default, no toolchain. |
| Fonts | IBM Plex Sans / Mono, vendored woff2 | Nothing is loaded from external providers at runtime. |
| Tests | pytest (unit, integration, API via `TestClient` + `httpx2`), `node --test` for pure JS modules, Playwright for Python (E2E) | Test dependencies live in the `dev` group only. |
| Quality | ruff (lint + format), pyright (strict on `taskboard/`), import-linter | Architecture rules are enforced by tests, not by convention. |

## Layout

Flat layout, so `import taskboard` works from `app.py` without installing the project.

```text
app.py                  ASGI entrypoint: `app = create_app()`; nothing else (a test enforces it)
taskboard/
  config.py             Settings
  domain/               Pure rules: lifecycle, ranking, outline numbering, task keys, errors
  db/                   SQLAlchemy base + portable types, models/, session, migrations/ (Alembic)
  identity/             Permissions, roles, principals, policy, passwords, sessions, providers/
  services/             Use cases; own the transaction; enforce the access policy
  schemas/              Pydantic models in and out of use cases; the API exposes them as-is
  api/                  FastAPI routers (thin), dependencies, error mapping
  web/                  App factory: mounts /api, static files, SPA fallback, middleware
  cli.py, __main__.py   python -m taskboard serve | db upgrade | seed | create-admin
  static/               index.html, css/, js/ (views/, components/, lib/), vendor/, fonts/
tests/                  unit/, integration/, api/, architecture/, e2e/, js/
docs/                   PLAN2, PLAN, ARCHITECTURE (this), DECISIONS, AUTH, OPERATIONS, CODEMAP (generated),
                        walkthroughs: IIS, WINDOWS-SIGNIN
scripts/                check.py (quality gate), gen_codemap.py
```

## Layers

```text
cli ─► web ─► api ─► services ─► schemas ─► identity ─► db ─► domain
```

Each layer may import only the layers to its right. Enforced by import-linter
(`[tool.importlinter]` in `pyproject.toml`, run by `lint-imports` and by
`tests/architecture/test_structure.py`). Two extra contracts:

- `taskboard.domain` imports no framework, persistence or config code. It is plain Python.
- `taskboard.api.routers` never imports `taskboard.db` or `sqlalchemy`: routers call services,
  which receive their session and principal from dependencies in `taskboard/api/deps.py`.

Request flow: router parses input (Pydantic schema) → dependency builds a service with the DB
session and the current principal → the service checks the policy, applies domain rules, commits →
the router maps the result to a response schema. Domain errors (`taskboard.domain.errors`) are
translated to HTTP status codes in one place in the API layer.

The frontend (`taskboard/static/`) talks to the server only through `/api`.

## Frontend

No build step: the browser loads ES modules directly. `index.html` holds an import map that
names the vendored libraries (`preact`, `preact/hooks`, `htm`); `js/ui.js` re-exports `html` and
the hooks, so components import from one place.

```text
static/js/
  main.js, app.js     mount; shell (sidebar + view) and route switch; login/password dialogs
  router.js           history-API router; href()/navigate() add the base path
  store.js            bootstrap document (me, people, projects), lookups, data revision
  api.js              fetch wrapper: JSON, CSRF header, ApiError
  hooks.js            useApi (GET + reload on revision), useTitle
  theme*.js, prefs.js theme and per-browser preferences
  lib/                pure logic, unit-tested with `node --test tests/js/*.test.mjs`
  components/         shared UI (sidebar, badges, dialog, drawer, lightbox, toasts, icons)
  views/              one module per screen
```

- **Routes** (`lib/routes.js`): `/priority`, `/people`, `/people/{department}[/{section}]` (team
  views, D-078), `/projects/{key}?node={id}`, `/t/{key}`, `/t/{key}/conversation`; process
  changes `/changes/{department}/{process}[/timeline | /{KEY}[/conversation]]`; process knowledge
  `/knowledge/{department}/{process}[/{box}]`, `/fmea/{department}/{process}?box=&release=`,
  `/cpl/{department}[/{defect}[/{cause}]]?process=&release=`, `/box/{key}` (the full table is in
  PLAN2.md). The
  server returns index.html for these paths (`web/frontend.py`).
- **Views by right** (`lib/access.js`): each view needs its module's view permission somewhere;
  "home" opens the first module the visitor may use. The two process modules share a header
  (`components/process-header.js`: department, process tabs) and remember the process chosen last.
- **Process changes** (`views/changes/`): the list and the timeline of a process (`index.js`,
  `list.js`, `timeline.js`) and a change as a drawer over them or as its own page (`change.js`,
  like tasks, D-040). The conversation (`components/change-conversation.js`) mixes comments and
  period posts and has the Comment / Period composer. Wording and states come from
  `lib/periods.js`, timeline geometry from `lib/timeline.js` (both pure and unit-tested). The
  server lists every first path segment of `lib/routes.js` as an app route (a test keeps them in
  step), so pasted links answer 200.
- **Process knowledge** (`views/knowledge/`): the map of a process (`index.js`: header, find in map,
  kind chips, expand/collapse) drawn by `map.js` from `lib/maplayout.js` (pure, unit-tested on the
  design's sample: tree, the mockup's horizontal layout, typed links both ways, defect chips,
  rolled-up change badges, search, arrow keys), and the selected box's panel (`panel.js`). Boxes
  are buttons in reading order with a roving tab stop; their colours come from the kind's palette
  entry (`kind--<style>` in `css/knowledge.css`, tokens for both themes) plus a shape per role.
  Editors get the box editor drawer (`editor.js`: the box, its links in both directions, its
  controls and external links saved in one request; a 409 shows "Someone else changed this box";
  the move dialog also reorders siblings) and admins the kinds & link types dialog
  (`settings.js`). `components/box-picker.js` finds a box by name (`GET /api/boxes?q=`, maps and
  defects) for links, changes and tasks; `components/box-links-field.js` shows and edits the
  boxes a change or task refers to. The FMEA is the same map with a `keep` filter
  (`fmeaBoxes`: failure modes and the boxes on the way to them). The control plan (`cpl.js`)
  works on `GET /api/control-plan?department=` through `lib/controlplan.js` (pure, unit-tested:
  defect groups, causes in map order, where they sit, the diagram's layout); it is a department
  page (`useDepartmentPage`: "All processes" or one). "Export PDF" prints a sheet (`print.js`);
  `css/print.css` shows only that sheet when printing. The FMEA and a process's control plan have
  the release bar and dialog (`release.js`, wording in `lib/releases.js`): the version shown,
  the draft (blue dots on the boxes), a version picker (`?release=v3`, read only) and "Review &
  release".
- **Search everything** (`components/search-dialog.js`, wording in `lib/search.js`): Ctrl K anywhere
  or the sidebar entry opens it; `GET /api/search` (`services/search.py`, rules in
  `domain/search.py`, D-094) returns the best hits per type with their stable links. The input is
  a combobox over a listbox whose options are the links themselves (Enter, Ctrl Enter for a new
  tab). `/box/{key}` (`views/knowledge/box-link.js`) opens a box where it lives.
- **Base path**: `<base href>` is filled in from `TASKBOARD_BASE_PATH`; all URLs are relative to it.
- **Styling**: `css/tokens.css` defines every colour/size as a custom property; the dark theme
  only overrides tokens (`[data-theme="dark"]`). Components never hard-code colours.
- **Permissions in the UI** come from `me.permissions` (`lib/lookup.js: canIn/canSomewhere`) and only
  hide controls; the server enforces everything.

## Data model

From `team-tasks-design/DESIGN.md`, plus access control.

- `departments(id, code, name)`, `sections(id, department_id, name)`.
- `processes(id, code, name, section_id, position)`: a production process (STL › Continuous
  casting). `code` is unique and fixed (`CC`, the prefix of change keys); the **owning section**
  decides who may see and edit the process's changes and map (D-080), and gives its department.
- `people(id, code, name, color, email?, section_id, active)`. The department follows from the section.
- `projects(id, key, name, color, position, archived)`.
- `project_nodes(id, project_id, parent_id?, position, name)`, unique `(id, project_id)`. Display
  numbers such as `2.2.1` are derived from positions, never stored.
- `tasks(id, key, title, description, rank, status, lead_person_id, section_id, created_at,
  updated_at, version)`.
  - `key` is the task's **public short id**: 6 random Crockford-base32 characters (no I/L/O/U),
    unique, immutable, case-insensitive, displayed as `T-K7Q2MX`. The integer `id` never leaves the
    server. Imported data may keep its own keys (the sample data keeps `T-104`).
  - `rank` is dense `1..N` over all tasks, archived ones included: one team-wide order.
  - `version` implements optimistic locking: a stale update gets HTTP 409.
- **Permalink**: `/t/{key}` opens the task on its own page (`/t/{key}/conversation` for that tab).
- `task_helpers(task_id, person_id)`. The lead is never also a helper.
- `placements(task_id, project_id, node_id?)`, unique `(task_id, project_id)`. The composite FK
  `(node_id, project_id) → project_nodes(id, project_id)` makes "the node belongs to that project"
  a database guarantee. A NULL node means top level of the project.
- `posts(id, task_id?, change_id?, author_user_id, created_at, edited_at?, edited_by_user_id?,
  body_md, is_update)`; `attachments(id, task_id?, change_id?, box_id?, post_id?,
  uploader_user_id, filename, content_type, size, storage_key)`. A post belongs to **exactly one**
  conversation, a task's or a process change's; an image to exactly one task, change or knowledge
  box (images in a box's description, kept as long as the box: CHECK `one_owner`). `post_revisions(post_id, rev,
  content JSON, written_by, written_at)` keeps every earlier version of an edited post.
- `changes(id, key, number, process_id, title, what_md, why_md, owner_person_id, created_at,
  updated_at, version)`: a process change. `key` is the process code and a number per code
  (`LM-07`), fixed even when the change moves to another process.
- `change_periods(id, post_id, change_id, kind, start_date, end_date?, label, scope_tags JSON)`:
  a test (`kind = test`, with an end date) or a permanent process change (`kind = change`, no end
  date until it is ended), **posted in the change's conversation**: the composite FK
  `(post_id, change_id) → posts(id, change_id)` keeps it on a post of the same change. The state
  ("In effect", "Test running", ...) is derived, never stored (`domain/changes.py`, mirrored by
  `static/js/lib/periods.js`, both tested against `tests/fixtures/change_states.json`).
- **Process knowledge** (DESIGN Module 3; `db/models/knowledge.py`, `services/knowledge.py`):
  - `box_kinds(key, name, role, style, has_facts, has_main_url, builtin, field_schema JSON)` and
    `link_types(key, forward_name, backward_name, role, builtin, field_schema JSON)`: built-in
    rows are seeded at start (renamable, not deletable) and carry the behaviour (`role`: step,
    failure mode, defect, `leads_to`, ...); custom ones are plain.
  - `boxes(id, key, process_id?, section_id?, parent_id?, position, kind_id, name, body_md,
    main_url, facts JSON, fields JSON, step_no, owner_person_id, reviewed_at, rev, version)`. A
    map box has a process (one root per process: a filtered unique index; a parent in the same
    process: a composite FK); a defect has no process and names its own section (CHECK). `key`
    is a readable slug, unique and fixed.
  - `box_links(from_box_id, to_box_id, type_id, note_md, fields JSON, rev)`, `controls(box_id,
    kind, text, position, fields JSON, rev)`, `external_links(box_id? | control_id?, kind, label,
    url, pass_box_param, position)` (part of their owner's content), `box_references(task_id? |
    change_id?, box_id, role)`.
  - `revisions(object_type, object_id, box_id, rev, content JSON, deleted, author_user_id)`:
    every save of a box, link or control whose content changed writes its full content; deletions
    too. `box_id` is the box whose history shows it. A test checks that every object's latest
    revision equals its row. Positions are spread out (1024, 2048, ...) and `stable_positions`
    changes as few as possible, so reordering rarely touches other boxes' revisions.
  - Saving a box (`PATCH /api/boxes/{key}`) sends **all** of its links, each with a `direction`
    (`forward`: this box is the link's from-box; `backward`: it is the to-box), so a link can be
    edited from either end; a link's revision goes to its from-box's history.
  - `releases(process_id, number, note, released_by_user_id, released_at)`, unique
    `(process_id, number)`, and `release_items(release_id, object_type, object_id, rev)`: a
    version of the process's FMEA and control plan (one number for both, no approval: D-081)
    freezes the revision of every object in its scope (`domain/releases.py`, D-093). The draft is
    computed (`services/releases.py`), and an old version is rebuilt from its frozen revisions as
    unsaved objects (`services/frozen.py`): `?release=N` on the map and the control plan.
- `events(id, task_id, actor_user_id?, api_token_id?, created_at, kind, data JSON)`: lifecycle
  changes, lead changes, helpers added or removed, placement changes.
- Identity: `users`, `external_identities(provider, subject)`, `roles`, `role_permissions`,
  `role_assignments(user_id, role_id, department_id?, section_id?)` (both NULL = global scope),
  `sessions` (server-side, so suspending a user takes effect immediately), `audit_log`,
  `api_tokens(user_id, name, token_hash, prefix, scope, expires_at?, last_used_at?, revoked_at?)`
  (D-097). What a token writes names it: `api_token_id` on events, posts (and
  `edited_api_token_id`), post revisions, knowledge revisions and releases.

A **Person** (someone on the board) and a **User** (a login account) are separate and optionally
linked 1:1. People who never log in can still lead tasks; built-in accounts are not people.

## Access control

- **Permissions** are strings defined in code (`domain/access.py`): `task.*`, `change.*`
  (`view`, `edit`, `comment`, `delete`) and `knowledge.*` (`view`, `edit`, `release`), all scoped
  to sections; `knowledge.configure`, `project.manage`, `people.manage`, `users.manage` (global).
  Table with the built-in roles: [`AUTH.md`](AUTH.md#permissions-and-built-in-roles).
- **Roles** are database rows bundling permissions. Built-in and non-deletable: *Viewer* (the
  three `*.view`), *Editor* (Viewer plus editing, commenting and releasing), *Administrator* (all).
  Custom roles need no code changes.
- **Assignments** give a user a role at a **scope**: global, one department (covering all its
  sections), or one section. A task's organizational section decides which assignments apply; for
  process changes and maps, the process's owning section does.
- **Anonymous** is a built-in user that cannot log in; by default it holds *Viewer* globally.
  Admins edit its assignments like anyone else's; removing them makes the board login-only.
- **Built-in users**: `admin` and `anonymous`.
- **One policy object** answers `can(principal, permission, section)` and builds the query
  filter for visible sections. Services call it; routers never decide access.
- Lists only contain tasks the principal may see. Ranks stay global (DESIGN rule 2), so a
  restricted viewer can see gaps (#1, #4, #5). Counts only include visible tasks.
- **The board** (departments, people, processes in the bootstrap) is open to anyone who may view
  something in any module (`services/visibility.py: can_view_anything`); task data only to those
  with `task.view` somewhere.
- **Today** comes from the server (`bootstrap.today`; `TASKBOARD_TODAY` pins it for tests and
  demos), so process-change states ("Test running", "Planned") are the same in browser and server.

- **API tokens** (D-097) let an AI agent or a script act as their owner:
  `Authorization: Bearer tb_…`, checked on every request like a session. The principal keeps the
  owner's grants narrowed to the token's scope (read: the `*.view` permissions; write: everything
  but `users.manage` and `people.manage`) and carries the token's id, so services stamp
  `api_token_id` on what they write and the views show "via <token name>". A Bearer request is
  judged by its token alone (never cookies, never anonymous: a bad token is 401), which is why
  the CSRF middleware lets it through. `GET /api/agent-guide` is the Markdown guide for agents,
  its endpoint list generated from the OpenAPI document (`services/agent_guide.py`).

Details, including SSO configuration: [`AUTH.md`](AUTH.md).

### SSO

- `IdentityProvider` protocol in three shapes: *redirect* (OIDC: login URL + callback; Microsoft
  Entra ID, `identity/providers/oidc.py`), *negotiate* (Windows sign-in: the browser proves the
  Windows login to the app itself in a Kerberos or NTLM handshake on `POST /api/auth/windows`,
  verified by Windows SSPI; `identity/providers/negotiate.py`) and *ambient* (a trusted reverse
  proxy passes the authenticated user in a header, `identity/providers/header.py`).
  All produce an `ExternalIdentity(provider, subject, email, name, groups, username)`. The first
  two end in an ordinary session; an ambient identity is read from every request.
- **Pre-provisioning**: an admin creates a user in advance (email/UPN, status *pending*) and
  assigns roles. At first external login the identity `(provider, subject)` is linked to that
  user, who becomes active with exactly the rights prepared for them. Unknown identities are
  rejected or created without roles, per configuration.
- Suspended users are refused whatever the provider says. Local accounts keep working beside SSO
  (the built-in admin is the break-glass account).
- **SSO is opt-in by configuration**: with no provider configured, only built-in accounts exist
  and the SSO routes are not mounted.
- **Group mappings** (IdP group → role at a scope) add rights for the groups the provider last
  reported; they are rows, managed under Administration.
- **Reverse proxies**: the app reads `X-Forwarded-For/-Proto` itself, only from
  `TASKBOARD_TRUSTED_PROXIES` (`api/client.py`), so it knows both the client's address and that
  the request came through the proxy (which is what makes identity headers believable).

## Deployments

| Target | Auth | Database | Hosting |
|---|---|---|---|
| Windows server, corporate | Built-in accounts + Entra ID SSO and/or Windows sign-in | SQLite, later MS SQL | Windows service behind IIS; with Windows sign-in: the service alone, reached directly |
| Linux server, demo | Built-in accounts only | SQLite | systemd service behind nginx/Caddy; internet-facing |

Code stays OS-neutral: `pathlib` everywhere, all locations come from settings, no OS-specific
calls. The one exception is opt-in: Windows sign-in asks Windows (SSPI, through pyspnego) to
verify tokens, and refuses to start elsewhere.

## Portability rules (SQLite now, MS SQL later)

1. Text columns use `Unicode`/`UnicodeText` (NVARCHAR on MS SQL); `String` would silently lose
   characters like "é" under some collations.
2. Every indexed or unique string column has an explicit length.
3. No database-level `ON DELETE CASCADE` on self-references or on paths that can form multiple
   cascade routes (MS SQL rejects them). Services delete children explicitly.
4. Uniqueness that must be case-insensitive (task keys, codes, emails, usernames) is normalized in
   code before storing, because default collations differ (SQLite: case-sensitive; MS SQL: not).
5. Constraint names come from a naming convention on the metadata, so Alembic migrations are
   deterministic on every backend.
6. No backend-specific SQL in services; anything unavoidable lives in `taskboard/db/`.
7. Nullable unique columns (emails, `users.person_id`) use **filtered unique indexes**
   (`WHERE col IS NOT NULL`): a plain UNIQUE on MS SQL allows only one NULL.
8. Enum columns store the value as VARCHAR without a CHECK constraint; Python validates values.
   Adding a member (e.g. a new event kind) needs no migration.
9. Long text is `NVARCHAR(max)` and timestamps are `DATETIME2` on MS SQL (explicit type variants
   in `taskboard/db/base.py`; the defaults would be the deprecated `NTEXT` and `DATETIME`).
   Timestamps are naive UTC in the database and timezone-aware UTC in Python (`UTCDateTime`).
10. To see the MS SQL DDL without a server: compile `CreateTable(table)` with
    `sqlalchemy.dialects.mssql.dialect()`. `tests/unit/test_mssql_schema.py` does so for every
    table: NVARCHAR text, no cascades, filtered unique indexes keep their WHERE (`mssql_where`
    next to `sqlite_where`), reserved words such as KEY quoted.
11. The API and integration suites run against any database named in
    `TASKBOARD_TEST_DATABASE_URL` (migrated once, emptied before every test; tests about SQLite
    itself are marked `requires_sqlite`). The MS SQL driver is the optional extra `mssql`. See
    [`OPERATIONS.md`](OPERATIONS.md#ms-sql-later).
12. A statement takes at most **2,100 parameters** on MS SQL (SQLite: 32,766). Lists of ids that
    grow with the data (a map's boxes, a release's objects) go through `db/ids.py: in_ids`, which
    writes integer ids into the SQL; `tests/conftest.py` fails any statement with more
    parameters on every backend, and the scale tests (5,000 tasks, 2,000 changes, a 2,000-box
    map) exercise the big lists.

## Transactions and concurrency

- One session per request. Requests with unsafe HTTP methods get a **write session**
  (`Database.new_session(write=True)`); on SQLite that starts with `BEGIN IMMEDIATE`, so writers
  queue (busy timeout 15 s) while readers continue (WAL). The Python sqlite3 driver's own
  transaction handling is disabled because it delays `BEGIN` until the first write.
- Critical sections that read and then rewrite many rows (re-ranking) first call
  `acquire_lock(session, TASK_RANKING_LOCK)`: an UPDATE on a row in `app_locks` that holds a
  row lock until commit. That serializes them on MS SQL as well.
- Tasks carry a `version` column (SQLAlchemy `version_id_col`): a stale update raises, which the
  API turns into HTTP 409.

## Recipes

**Add an endpoint**: request/response models in `taskboard/schemas/`, use case in `taskboard/services/`,
route in `taskboard/api/routers/` (register it in `taskboard/api/__init__.py`), tests in
`tests/api/` including the 401/403 cases.

**Change the schema**: edit `taskboard/db/models/`, then
`uv run alembic revision --autogenerate -m "..."`, review the migration, run the tests (one
checks that models and migrations agree).

**Add a permission**: add it to the catalog in `taskboard/identity/permissions.py`, decide which
built-in roles get it (the seed updates them), extend the policy matrix test.

**Add a screen**: `taskboard/static/js/views/<name>.js`, register the route in
`taskboard/static/js/router.js`; pure logic goes in `taskboard/static/js/lib/` with a test in
`tests/js/`.

**Always**: give new files a one-line module docstring or header comment, then run
`uv run python scripts/check.py --fix` (regenerates `docs/CODEMAP.md`, lints, type-checks, tests).
