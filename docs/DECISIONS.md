# Decision log

Short records of choices that shape the code. Newest last. "Confirmed" means the product owner
decided; "Assumed" means a reasonable default that is easy to revisit. Change an entry by adding
a new one that supersedes it.

| ID | Decision | Status |
|---|---|---|
| D-001 | Backend is **FastAPI** + a static frontend, not Shiny (DESIGN.md mentions Shiny). | Confirmed, session 1 |
| D-002 | Permission scopes are **organizational sections** (Department › Section); grants can also be department-wide or global. Project nodes are not permission scopes. | Confirmed, session 1 |
| D-003 | Frontend: **JSON API + Preact/htm** ES modules, vendored, no build step. | Confirmed, session 1 |
| D-004 | Two deployments: **Windows server** (corporate; built-in accounts + Entra ID SSO later) and **Linux demo server** (built-in accounts only). SSO is opt-in configuration. | Confirmed, session 1 |
| D-005 | Every task has a **short unique key** (6 random Crockford-base32 characters, shown `T-K7Q2MX`) and a **permalink** `/t/{key}` that opens its own page. | Confirmed, session 1 (requirement) |
| D-006 | SQLAlchemy 2.x **sync** ORM + Alembic; portability rules in ARCHITECTURE.md. | Assumed |
| D-007 | **Flat package layout** (`taskboard/` next to `app.py`), so deployments don't need to install the project. | Assumed |
| D-008 | **Server-side sessions** stored in the database (not signed JWT cookies), so suspension and logout take effect immediately. CSRF: SameSite cookies + double-submit header. | Assumed |
| D-009 | **Markdown rendered server-side** (markdown-it-py + nh3); the browser never renders raw Markdown. | Assumed |
| D-010 | **Person ≠ User**: board members and login accounts are separate, optionally linked 1:1 (matched by email when SSO links accounts). | Assumed (A1) |
| D-011 | Task and person store only the **section**; department is derived. | Assumed (A2) |
| D-012 | Creating/editing projects and their section trees needs **`project.manage`** (admins by default). | Assumed (A3) |
| D-013 | Posting in a conversation needs **`task.comment`** (part of *Editor*); viewers only read. | Assumed (A4) |
| D-014 | Changing a task's section needs edit rights on **both** the old and the new section. | Assumed (A5) |
| D-015 | People view: dragging reorders **within a lane** (changes the global rank); no drag across lanes. | Assumed (A6) |
| D-016 | Deleting a project node moves its tasks' placements to the **parent node**, after confirmation. | Assumed (A7) |
| D-017 | `@mentions` are highlighted only; **no notifications**. English-only UI. | Assumed (A8, A9) |
| D-018 | Global rank is **dense 1..N including archived tasks**; a move shifts a contiguous range in one transaction. | Assumed |
| D-019 | Tests use **`httpx2`** with Starlette's TestClient (Starlette 1.7 deprecates `httpx` there). Dev-only. | Assumed |
| D-020 | **Write transactions**: SQLite write sessions start with `BEGIN IMMEDIATE`; re-ranking also takes a lock row (`app_locks`) so it is serialized on every backend. | Assumed |
| D-021 | **Migrations run at startup** by default (`TASKBOARD_AUTO_MIGRATE=true`), plus built-in data seeding. Can be turned off for manual `python -m taskboard db upgrade`. | Assumed |
| D-022 | The generated initial **admin password is printed once** (log/CLI) and must be changed at first login; `TASKBOARD_INITIAL_ADMIN_PASSWORD` avoids that. | Assumed |
| D-023 | Sample people get accounts (`anna.claes`, ...) with **Editor on their own department**, which demonstrates scoped rights; they can log in only when `seed --sample --demo-password ...` is used. | Assumed |
| D-024 | Enum values are validated in Python, **no CHECK constraints** on enum columns (keeps new values migration-free). | Assumed |
| D-025 | **Anonymous rights are a floor**: every logged-in user also holds what `anonymous` holds, so logging in never shows less. | Assumed |
| D-026 | SSO matching: first on `(provider, subject)`, then on **email** to a pre-provisioned account; built-in accounts are never linked by email; unknown people are **rejected** by default (`TASKBOARD_SSO_UNKNOWN_USERS=create` makes rightless accounts instead). | Assumed |
| D-027 | Services **commit explicitly**; the per-request session only rolls back what is left uncommitted. | Assumed |
| D-028 | Login throttling: 5 failures per account (since last success) / 50 per client address in 15 minutes → HTTP 429. | Assumed |
| D-029 | Request/response models live in **`taskboard/schemas/`**, a layer below services, so services return exactly what the API sends (no duplicate DTOs). | Assumed |
| D-030 | Deleting tasks needs **`task.delete`**, which only *Administrator* has by default (archiving is the normal way out). | Assumed |
| D-031 | Placement changes (add/move/remove) are **immediate** API calls, not part of the task form's save; they bump the task version and the response carries the new one. | Assumed |
| D-032 | **Re-ranking is not an edit**: it changes neither `version` nor `updated_at`, so reordering never conflicts with someone's open edit form. | Assumed |
| D-033 | **New tasks start at the bottom** of the ranking (rank N+1); people drag them up. | Assumed |
| D-034 | The API identifies tasks by **key** (`K7Q2MX`; `T-K7Q2MX` and any case accepted) and projects by **key** (`ASQ`); nodes by id. Invisible tasks answer 404, not 403. | Assumed |
| D-035 | The frontend works under a **URL prefix**: `<base href>` comes from `TASKBOARD_BASE_PATH`, and every URL in the page and in `api.js`/`router.js` is relative to it. | Assumed |
| D-036 | Current **Preact 10 + hooks + htm** are wired with an **import map** in index.html (htm's all-in-one bundle ships an old Preact). The inline import map will need a CSP hash in M10. | Assumed |
| D-037 | The Priority view loads all visible tasks once and **filters in the browser** (instant); `lib/filters.js` mirrors the server's filter rules and is unit-tested. | Assumed |
| D-038 | Browser tests are marked `e2e` and **excluded from plain `pytest`** (`-m e2e`, or `scripts/check.py --e2e`). | Assumed |
| D-039 | Theme: follows the OS until the user toggles, then the choice is remembered per browser. The sidebar collapse state is remembered per browser. | Assumed |
| D-040 | A task opened **from a list shows as a drawer** over that list (URL `/t/{key}`, closing = Back); the same URL **opened directly shows the task page**. | Assumed |
| D-041 | In the drawer, title/description/lifecycle/section/lead/helpers are saved together with **Save task**; placement changes apply immediately (D-031). New tasks collect placements before creation. | Assumed |
| D-042 | Mouse drags start anywhere on a row (not on links/controls) after 5 px; **touch drags start on the grip** so pages still scroll. Keyboard reordering remains for M10. | Assumed |
| D-043 | People view: lanes for **active people only**; counts ("2 lead · 2 helping") ignore the "Lead only" toggle but follow search and "Show archived". Cards are dragged by mouse; touch users reorder in the Priority view (grip). | Assumed |
| D-044 | Projects: `/projects` opens the **first non-archived project**; a section is selected with `?node={id}`. Archived projects stay in the tree, in italics. | Assumed |
| D-045 | Section editing uses explicit buttons (up, down, indent, outdent, add, delete) rather than drag-and-drop in the tree: precise, accessible, and testable. | Assumed |
| D-046 | Posts: **CommonMark + tables + strikethrough**, single newlines are line breaks; raw HTML is not interpreted; output sanitized with **nh3**. `@name` is highlighted; `T-KEY` links to the task. | Assumed |
| D-047 | Post images may only come from **this app's attachments** (no external images, so no tracking pixels). Accepted: PNG, JPEG, GIF, WebP up to 10 MB, recognised by their bytes. | Assumed |
| D-048 | Images are uploaded first as **drafts** and attached to the post whose Markdown refers to them; drafts nobody posted are removed after a day. Attachment access follows the task's visibility. | Assumed |
| D-049 | Authors edit and delete their own posts; users with `users.manage` may delete (not edit) any post. Posting needs `task.comment`. | Assumed |
| D-050 | "Updates only" shows only posts marked as status updates (events hidden). | Assumed |
| D-051 | **Lockout guard**: any change that would leave no active account with `users.manage` everywhere is refused (you also cannot suspend yourself or the anonymous visitor). | Assumed |
| D-052 | Passwords set or generated by an administrator **must be changed at first login**; generated ones are shown once and never stored in clear. Resetting a password logs the account out everywhere. | Assumed |
| D-053 | Built-in roles are read-only (their permissions come from code); **custom roles** are free, but cannot be deleted while assigned. | Assumed |
| D-054 | People are **deactivated, not deleted** (tasks and history refer to them); someone who still leads tasks must hand them over first. Departments/sections are deleted only when unused. | Assumed |
| D-055 | Email addresses get a light format check only; for SSO the identity provider is the authority. | Assumed |
| D-056 | OIDC is built on **PyJWT + the standard library's HTTP client** instead of Authlib: the flow is small (code + PKCE + ID token), every check is visible and tested, and no framework-specific session middleware is needed. | Assumed |
| D-057 | A sign-in's state is stored **hashed and single-use** for 10 minutes and bound to the browser with a cookie; the nonce must come back inside the ID token. Only RS/PS/ES signatures are accepted. | Assumed |
| D-058 | The SSO sign-in routes are **mounted only when a redirect provider is configured**; without SSO the demo server exposes nothing SSO-related. | Assumed |
| D-059 | Pre-provisioned accounts are matched on email, then on the **login name** (`CORP\jdoe` → `jdoe`; keep the domain with `TASKBOARD_TRUSTED_HEADER_STRIP_DOMAIN=false`), so Windows sign-in works without emails. Usernames may therefore contain `\`. An account's existing display name is kept. | Assumed |
| D-060 | **Group mappings are database rows** managed in the admin UI (not configuration); the groups a provider reports are stored with the identity link and add rights on top of the account's own. Names compare exactly. | Assumed |
| D-061 | The app reads **`X-Forwarded-For/-Proto` itself**, only from `TASKBOARD_TRUSTED_PROXIES`, and `taskboard serve` turns Uvicorn's proxy handling off: Uvicorn would replace IIS's address with the client's, and identity headers could then never be trusted. | Assumed |
| D-062 | Visitors signed in by a trusted proxy header get **no "Log out"** (the next request would sign them in again); the built-in admin is reached on the server itself, bypassing the proxy. | Assumed |
| D-063 | **Strict CSP** on every response: only this site, no inline styles; the inline import map is allowed by its hash, computed from the page. `/api/docs` (Swagger UI from a CDN) is exempt from the CSP only. Also nosniff, no framing, same-origin referrer/opener/resource policies. **HSTS is the proxy's job.** | Assumed |
| D-064 | Responses over 1 kB are **gzip-compressed** by the app (the 5,000-task list is 2.4 MB of JSON). | Assumed |
| D-065 | Long lists stay fully rendered (no virtual scrolling, which would complicate drag-and-drop and find-in-page); rows and cards use CSS `content-visibility: auto`, which halves the render time of 5,000 tasks. | Assumed |
| D-066 | **Keyboard reordering** on the Priority view's grip button: Arrow Up/Down one place, Home/End to the ends of the visible list; focus follows the task. Moves are saved one at a time, in order. The People view stays mouse-only (like touch, keyboard users reorder in Priority). | Assumed |
| D-067 | The task's Details/Conversation switch is **links marked `aria-current`**, not an ARIA tab widget (they change the URL); the composer's Write/Preview is a pair of toggle buttons. The task page's heading is the task key plus its title (the title only for screen readers). | Assumed |
| D-068 | **Backups** are one zip: manifest, a SQLite snapshot through SQLite's backup API (safe while running) and the uploads. A restore needs `--replace` when data exists and keeps what it replaces (`*.before-restore-<time>`); older backups are upgraded, newer ones refused, unexpected zip entries rejected. MS SQL databases are backed up with their own tools. | Assumed |
| D-069 | Settings read the **app folder's `.env`**, whatever the working directory (services and scheduled tasks start elsewhere). | Assumed |
| D-070 | The MS SQL driver is the optional extra **`mssql`** (pyodbc). The test suites run against any database via `TASKBOARD_TEST_DATABASE_URL`, which they empty before every test. | Assumed |
| D-071 | Dark theme: the primary button orange is **#BC521A** (was #C4561C) so white text meets WCAG AA (4.8:1); top-rank numbers on dashed "helping" cards use the darker accent ink. | Assumed |
| D-072 | **Windows sign-in is done by the app itself**, without IIS: HTTP Negotiate (Kerberos or NTLM) verified by Windows SSPI through pyspnego, with Uvicorn reached directly. IIS cannot hand the Windows user to a proxied app with its own modules: URL Rewrite runs before authentication, so `{LOGON_USER}` is empty (found on a real IIS). The trusted-header provider (D-061, D-062) stays for proxies that authenticate first. | Confirmed, 2026-09-30 |
| D-073 | The Negotiate handshake lives on **one endpoint** (`POST /api/auth/windows`) and ends in an ordinary session (D-008), instead of challenging every request: anonymous reading, the built-in admin and "Log out" keep working, and Windows is asked once per session. The page tries it by itself for visitors, once per browser tab and not after a logout (`TASKBOARD_WINDOWS_AUTH_AUTOMATIC`); only refusals of an identified person are shown. | Assumed |
| D-074 | NTLM's half-finished handshakes are kept **in memory per connection** (peer address and port; 30 seconds, at most 1024), which fits the one-process deployment; a refused token is challenged again so browsers can prompt. `serve` raises Uvicorn's request-header limit from 16 kB to 128 kB when Windows sign-in is on (Kerberos tickets reach 64 kB). Windows reports no groups and no email: accounts match on the login name (D-059). | Assumed |
| D-075 | **pyspnego is a regular dependency** (pure Python; its SSPI binding installs on Windows only), not an optional extra: nothing to remember at install time. The provider itself refuses to start off Windows. | Assumed |
| D-076 | `serve` can **terminate TLS itself** (`TASKBOARD_TLS_CERTFILE`, `TASKBOARD_TLS_KEYFILE`), for the deployment without a proxy. HSTS stays out of the app (D-063). The handshake is not bound to the TLS channel (no Extended Protection) yet. | Assumed |
| D-077 | **Team views** in People: a Team dropdown shows everyone, one department, or one section; each team has its **own URL** to bookmark or share. | Confirmed, 2026-09-30 (requirement) |
| D-078 | Team URLs are **readable**: `/people/{department code}/{section name}` (`/people/STL/Quality`), matched ignoring case and then shown in the organization's spelling. A renamed department or section breaks old bookmarks; the view then says the team does not exist. The team picks the **people only**: a lane still shows all of that person's tasks, whatever their section. The sidebar's People link returns to the team shown last during the visit (like D-043's filters, a reload forgets it); `/people` alone is everyone. | Assumed |

