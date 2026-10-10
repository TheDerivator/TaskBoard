# TaskBoard 2: process changes, process knowledge, search

Second delivery plan. [`PLAN.md`](PLAN.md) tracked the original build (M0–M10, the Tasks module);
this file tracks the modules added by the design commit `14b1c1d "New design"`
([`team-tasks-design/DESIGN.md`](../team-tasks-design/DESIGN.md), parts 2–4). Milestone numbers
continue from PLAN.md, so `M13` means the same thing everywhere.

Each milestone lists deliverables (checkboxes) and an **acceptance gate**: the automated checks
that must pass before it counts as done (`uv run python scripts/check.py --fix --e2e`, plus the
gate's own tests). Keep the status table and the checkboxes current as work lands.

## Status

| #   | Milestone                                              | Status        |
|-----|--------------------------------------------------------|---------------|
| M11 | Foundations: processes, new rights, clock, navigation | ☑ done        |
| M12 | Process changes: data, conversation, API                | ☑ done        |
| M13 | Process changes: list, drawer, timeline                 | ☑ done        |
| M14 | Process knowledge: model, revisions, API                | ☑ done        |
| M15 | Knowledge view (reading the map)                        | ☑ done        |
| M16 | Knowledge editing and settings                          | ☑ done        |
| M17 | FMEA and control plan (CPL) views                       | ☑ done        |
| M18 | Releases                                                | ☑ done        |
| M19 | Global search and stable links                          | ☑ done        |
| M20 | Hardening of the new modules                            | ☑ done (live demo reseed: owner) |
| M21 | API tokens for AI agents (beyond the design)            | ☑ done        |
| M22 | Full-width drawers, image lightbox (beyond the design)  | ☑ done        |

Legend: ☐ not started · ◐ in progress · ☑ done

---

## What the design asks for

| Design part | Screens (mockups) | Milestones |
|---|---|---|
| Sidebar: "Search everything (Ctrl K)", "Process changes", "Process knowledge" | all sidebars | M11 (process entries), M19 (search) |
| Process changes: list per department/process, derived "Now" state | `ChangesList` | M12, M13 |
| Change drawer: details, linked map boxes, periods summary | `ChangeDetail` | M13 (boxes: M16) |
| Change conversation: comments + period posts, "Periods only" | `ChangeConversation` | M12, M13 |
| Timeline (Gantt) with range and map-box filters | `ChangesGantt` | M13 (box filter: M16) |
| Knowledge view: collapsible map, kind filters, side panel | `ProcessMap` | M15 |
| Edit a box: kind, place, Markdown, typed links, controls, external links | `NodeEdit` | M16 |
| Kinds & link types settings | `MapSettings` | M16 |
| FMEA view (+ release bar, draft markers) | `FmeaMap` | M17 (release bar: M18) |
| CPL view: defect → where → how → controls | `DefectView` | M17 (release bar: M18) |
| Release FMEA & CPL (changes since last release, approver) | `Release` | M18 |
| Global search | `GlobalSearch` | M19 |
| Stable links for every object | DESIGN "Stable links" | per milestone, checked in M19 |

The Tasks module itself is unchanged by the new design (only the three sidebar entries are new).

---

## Domain model (refined from DESIGN.md's proposal)

DESIGN.md calls its data model a proposal. What follows keeps its principles ("Extensibility
toward a full FMEA + control plan", 1–8) and adapts names and splits to this codebase and its
portability rules ([`ARCHITECTURE.md`](ARCHITECTURE.md)).

### Organization

- `processes(id, section_id, code, name, position)`. `code` (`CV`, `LM`, `CC`) is unique across
  the whole organization (it prefixes change keys) and immutable once created; the name can change.
  A process belongs to a department (DESIGN Module 2, rule 1) **through its owning section**
  (Q2): the section decides who may see and edit the process's changes and map, exactly as a
  task's section does (D-011: only the section is stored, the department follows from it).

### Process changes

- `changes(id, key, process_id, number, title, what_md, why_md, owner_person_id, created_at,
  updated_at, created_by_user_id, version)`. `key` = process code + number (`LM-07`), unique and
  immutable: it stays when the change is moved to another process (stable links).
- **Periods are posts** (DESIGN rule 3): `change_periods(id, post_id, change_id, kind, start_date,
  end_date?, label, scope_tags JSON)`, the Markdown body lives in the post. `kind` is `test` or
  `change`, chosen when posting ("No end date" = process change); a test needs an end date; a
  process change may get one later ("Set end date" = ended/reverted). End dates are inclusive.
- **Derived state** (never stored; one pure function in Python and one in JS, both tested against
  the same table of cases `tests/fixtures/change_states.json`), first match wins, as in the mockup:
  1. a process change that has started and has not ended → *In effect since …*
  2. a test containing today → *Test running until …*
  3. a period starting after today → *Planned from …*
  4. no periods at all → *No periods yet*
  5. otherwise → *Tests ended …* (or *Ended …* when the last period was a process change)
- Conversations are shared with tasks: `posts`, `attachments` get a nullable `change_id` beside
  the (now nullable) `task_id`, with a CHECK that exactly one is set. Post edits keep history in
  `post_revisions(post_id, rev, content JSON, editor, created_at)` (DESIGN rule 6: "history kept");
  this applies to task posts too.

### Process knowledge

- `box_kinds(id, key, name, description, role, style, has_facts, has_main_url, builtin, position,
  field_schema JSON)`. `role` gives a kind its behaviour: `step` (builds the tree, FMEA path),
  `knowledge`, `reference`, `rule`, `failure_mode` (controls, FMEA), `defect` (catalogue, CPL), or
  `plain` (custom kinds). The six built-in kinds are seeded like built-in roles: renamable and
  restylable, not deletable. `style` is a named palette entry (tokens with light and dark values,
  plus an icon), so colour is never the only cue and custom kinds stay readable in both themes.
- `link_types(id, key, forward_name, backward_name, description, role, builtin, position,
  field_schema JSON)`. `leads_to` (failure mode → defect or failure mode) drives FMEA chips and the
  CPL; the others are plain. "part of" is the tree itself, not a row.
- `boxes(id, key, process_id?, section_id?, parent_id?, position, kind_id, name, body_md,
  main_url?, facts JSON, fields JSON, step_no?, owner_person_id?, reviewed_at?, rev)`.
  - A **map box** has a process (and takes its section from it); its tree has exactly one root
    (the box without a parent), which *is* the process in the views ("Start the map" creates it).
    A composite foreign key keeps a parent in the same process.
  - A **defect** is a box of the defect kind without process or parent, in its department's shared
    catalogue (DESIGN open question 2: boxes, so links, revisions, references and search treat
    them like any other box). Having no process, a defect names its own **section** (Q2), which
    decides who may see and edit it; the catalogue it belongs to is that section's department.
  - `key` is a readable slug made from the name at creation (`mould-level-fluctuation`; the sample
    keeps `fm-level`), unique across all boxes and never changed: it is the box's link and the
    `?node=` parameter passed to dashboards, and it survives reorganizing sections.
- `box_links(id, from_box_id, to_box_id, type_id, note_md, fields JSON, rev)`: typed links in any
  direction, also across processes; each reads forward on one box and backward on the other.
- `controls(id, box_id, kind (prevent|detect), text, position, fields JSON, rev)`: own records with
  stable ids (principle 3), on failure modes now, on causes later.
- `external_links(id, box_id?, control_id?, kind, label, url, pass_box_param, position)`: part of
  their owner's content (an edit is a new revision of the box or control). Only http(s) URLs; they
  open in a new tab, with `?node=<box key>` added when asked.
- `references(id, task_id?, change_id?, box_id, role)`: the one generic table from tasks and
  changes to boxes (principle 5); roles `affects` (changes), `related` (tasks), later `action`.
- **Revisions** (DESIGN "Versioning" 1): `revisions(object_type, object_id, rev, content JSON,
  deleted, author_user_id, created_at)` for boxes, links and controls. Every save stores the full
  content; deletions are revisions too. The object rows hold the current state (and `rev` doubles
  as the optimistic-locking version → HTTP 409 on stale saves).
- **Releases** (Versioning 2–4): `releases(id, process_id, number, note, released_by_user_id,
  released_at)` and `release_items(release_id, object_type, object_id, rev)`. **No approval step**
  (Q3, DESIGN open question 1): releasing is one action by someone with `knowledge.release`, and
  the new version is current at once. The draft is computed (current revisions vs the latest
  release); an old version is drawn from its frozen items. FMEA and CPL share one number.
- **Release scope** (one tested domain function): steps on the path to a failure mode, failure
  modes, the defects they lead to, `leads_to` links between those, and the controls (with their
  external links) of those failure modes. Everything else is "knowledge" and versioned per box only.

### Views are derived, the map is the storage (principle 8)

The server returns a process's **graph** (boxes, links, controls, external links, reference
counts), either current or rebuilt from a release's revisions. Knowledge, FMEA and CPL are pure
functions of that graph in `static/js/lib/` (unit-tested with `node --test`); the server's domain
code owns what must be authoritative: tree rules, release scope, draft diffs, which document a
change affects, warnings.

---

## Roles and permissions

Every process names an **owning section** (Q2), and defects name one too. The new permissions are
therefore **scoped per section, exactly like `task.*`**: a grant applies if it is global, for the
section's department, or for that section. No new scope mechanism is needed: `GrantSet`,
`me.permissions` and the frontend's `canIn` work unchanged. The anonymous-floor rule (D-025) and
"routers never decide access" stay.

| Permission | Scope | Viewer | Editor | Admin | Allows |
|---|---|:-:|:-:|:-:|---|
| `task.view` / `.edit` / `.comment` / `.delete` | section | as today | as today | ✔ | unchanged; `task.edit` also links a task to map boxes |
| `change.view` | section | ✔ | ✔ | ✔ | process change list, timeline, drawer, conversation; changes shown on map boxes |
| `change.edit` | section | | ✔ | ✔ | new change, edit details, post/edit periods, set end date, link to map boxes |
| `change.comment` | section | | ✔ | ✔ | comments and images in a change's conversation |
| `change.delete` | section | | | ✔ | delete a change (mirrors `task.delete`, D-030) |
| `knowledge.view` | section | ✔ | ✔ | ✔ | Knowledge, FMEA and CPL views, history, released versions, print/PDF |
| `knowledge.edit` | section | | ✔ | ✔ | boxes, links, controls, external links, defects, "Start the map" |
| `knowledge.release` | section | | ✔ | ✔ | "Review & release": freeze a new FMEA/CPL version (no approval, Q3) |
| `knowledge.configure` | global | | | ✔ | Kinds & link types settings |
| `people.manage` | global | | | ✔ | now also processes (Administration › Organization) |

Viewer and Editor cover the new modules (Q1). Because anonymous visitors hold *Viewer* by default
and built-in roles are re-synced at start, **anonymous visitors see process changes and process
knowledge after the upgrade** unless an administrator narrows their rights. Built-in roles cannot
be edited (D-053): to keep releasing to fewer people, use a custom role without
`knowledge.release` instead of *Editor*.

Cross-module rules (tested in the API suites):
- A box lists linked changes only where the reader has `change.view`, and tasks only where they
  have `task.view`; a change lists linked boxes only where the reader has `knowledge.view`.
- Linking needs edit rights on the source (`change.edit` or `task.edit`) and view rights on the box.
- Moving a change to another process, or a defect to another section, needs edit rights on both
  sections (like D-014). Moving a process to another section is an organization change
  (`people.manage`) and moves its changes and map with it.
- Search results are filtered per type by the same rules (M19).
- Invisible objects answer 404, as tasks do (D-034).

---

## Links (routes)

Following DESIGN "Stable links"; department and process codes are matched ignoring case and shown
in the organization's spelling (like team views, D-078). A change or box URL whose process segment
is out of date redirects to the canonical one (the key decides).

| Object | Link |
|---|---|
| Process changes of a process | `/changes/STL/LM` (list), `/changes/STL/LM/timeline` |
| A process change | `/changes/STL/LM/LM-07` (drawer over the list, or its own page), `…/LM-07/conversation` |
| Knowledge map, a box | `/knowledge/STL/CC`, `/knowledge/STL/CC/fm-level` |
| FMEA (optionally a box and a release) | `/fmea/STL/CC?box=fm-level&release=v3` |
| Control plan for a defect (optionally a cause) | `/cpl/STL/sliver-lines`, `/cpl/STL/sliver-lines/fm-level?process=CC` |
| Task | `/t/K7Q2MX` (unchanged, D-005) |
| A box by its key alone (links from dashboards, M19) | `/box/fm-level` |

`/changes` and `/knowledge` alone open the process chosen last in this browser, shared by both
modules (DESIGN open question 4: yes).

---

## Milestones

### M11 · Foundations: processes, new rights, clock, navigation
- [x] `processes` table (with owning section) + migration; Administration › Organization lists
      and edits each department's processes (add, rename, change section, reorder, delete when
      unused); API with 401/403/422.
- [x] New permissions (`change.*`, `knowledge.*`, `knowledge.configure`) in `domain/access.py`,
      built-in Viewer/Editor/Administrator synced (table above), shown in the role editor and
      AUTH.md; `people.manage` described as covering processes.
- [x] Bootstrap: processes the caller may see (in either module), and `today` from the server
      (`TASKBOARD_TODAY` pins it for tests and demos), so browser and server agree on dates.
- [x] Sidebar: "Process changes", "Process knowledge" (task entries only for those who may see
      tasks; "Search everything" comes with the search itself in M19); routes for both modules
      and a shared header (department select + process tabs) that remembers the process per
      browser; placeholder pages until M13/M15.
- [x] Sample data: the design's three STL processes, owned by STL › Process.
- [x] Beyond plan: the views a visitor gets follow their rights (`lib/access.js`): task entries
      only with `task.view`, "home" opens the first module they may use, other modules say "No
      access yet"; someone with only process rights gets a working board (organization, people,
      processes) without any task data. A test keeps the loader's sample data identical to the
      design's `sample-data.json`.

**Acceptance gate**: the policy matrix covers the new permissions (admin / department editor /
section editor / viewer / anonymous / none × view / edit / release / configure); after the
upgrade sync, anonymous visitors hold `change.view` and `knowledge.view` and lose them when an
admin removes their assignment; process admin endpoints 401/403/422; migrations in sync; routes
parse and format (`tests/js/routes.test.mjs`); axe clean on Organization with processes and on
the new (empty) pages; the sidebar shows the new entries only to those who may use them.
Met (2026-10-04, 444 tests green with `--e2e`): `tests/unit/test_access_policy.py`,
`tests/api/test_processes.py`, `tests/integration/test_sample_data.py`,
`tests/js/routes.test.mjs`, `tests/js/processes.test.mjs`, `tests/e2e/test_processes.py`,
`tests/e2e/test_accessibility.py`.

### M12 · Process changes: data, conversation, API
- [x] Models + migration: `changes`, `change_periods`, `posts`/`attachments` generalized with
      `change_id`, `post_revisions`. Existing task conversations keep working (migration test with data).
- [x] Domain: change keys and numbering (per process, under a lock), period rules (kinds, end ≥ start,
      inclusive), derived state, scope-tag normalization.
- [x] API: changes per process (with periods, state inputs, owner, post count), get by key, create,
      edit (version → 409), move to another process, delete; conversation (comments + periods,
      `periods_only`), post/edit/delete periods, set end date, post history, scope-tag suggestions
      (tags used on the same process, most used first), attachments.
- [x] Sample data: processes, the 14 changes and 24 periods of `sample-data.json`, plus the LM-07
      comments from the mockup; `seed --sample` shifts the design's dates so its "today"
      (3 Oct 2026) becomes the seeding day.
- [x] Beyond plan: `posts.edited_by_user_id` (periods are edited by others than their author),
      `GET /api/posts/{id}/history` for every post (tasks too), a lock row for change numbers,
      deleting a process is refused while it has changes, external consumers get each change's
      state and URL in the API.

**Acceptance gate**: API tests for every endpoint including 401/403/404/409/422; the shared
state-table test passes in Python; for the sample at 3 Oct 2026 the LM list yields exactly the
mockup's chips and "Now" column (LM-12 *Planned from 13 Oct*, LM-11 *Test running until 3 Oct*,
LM-10 *In effect since 1 Aug*, LM-08 *Tests ended 13 Jun*, …); editing a period keeps the old
version; integration tests for the new constraints (exactly one owner of a post).
Met (2026-10-04, 497 tests green with `--e2e`): `tests/unit/test_changes.py` and
`tests/js/periods.test.mjs` (one shared table, `tests/fixtures/change_states.json`),
`tests/api/test_changes.py`, `tests/integration/test_constraints.py`,
`tests/integration/test_migration_data.py`, `tests/integration/test_sample_data.py`.

### M13 · Process changes: list, drawer, timeline
- [x] List view (`ChangesList`): process tabs, search on what/why, period chips, Now pill, owner,
      post count; cards on narrow screens; "New change".
- [x] Change drawer and page (`ChangeDetail`, `ChangeConversation`): details form, periods summary
      with "View post", "At a glance" bar; conversation with Comment / Period composer (label,
      from/to, "No end date", scope tags with suggestions, Markdown, live sentence "Appears on the
      timeline as …"), "Edit period", "Set end date", "edited" with history, "Periods only".
- [x] Timeline (`ChangesGantt`): range (3/6/12 months + planned), month grid, today line, test /
      process-change / planned bars, hover and focus tooltips, legend and summary, horizontal
      scroll with a sticky first column on narrow screens.
- [x] Beyond plan: a change link opened with a moved process or loose spelling corrects itself;
      the server now serves every first path segment the browser router knows (a test keeps the
      two in step; found when pasted `/changes/...` links answered 404); a period's "Delete";
      the timeline has the mockup's range filter but no search (the map-box filter is M16's).

**Acceptance gate**: `node --test` for `lib/periods.js` (the same state table) and
`lib/timeline.js` (axis, bar geometry, clipping, which changes a range includes); Playwright:
create a change, post a test period → chip in the list and a bar in the timeline; set an end date
on a process change; edit a period → "edited" and history; a viewer sees no edit controls; axe
clean (list, timeline, drawer, both composers) in light and dark.
Met (2026-10-04, 510 tests green with `--e2e`): `tests/js/periods.test.mjs`,
`tests/js/timeline.test.mjs`, `tests/e2e/test_changes.py`, `tests/e2e/test_accessibility.py`
(list, timeline, drawer, conversation with the period form, editing a period, new change, in
both themes), `tests/api/test_frontend.py`.

### M14 · Process knowledge: model, revisions, API
- [x] Models + migration: `box_kinds`, `link_types` (built-ins seeded), `boxes`, `box_links`,
      `controls`, `external_links`, `references`, `revisions`.
- [x] Domain: slugs, tree rules (one root per process, parent in the same process, no cycles,
      defects outside trees, kind changes allowed), revision snapshots and readable diffs.
- [x] API: a process's graph (current), the department's defect catalogue, box create / edit (box,
      its links, controls and external links saved together → revisions) / move / reorder /
      delete (only without children), history, references from changes and tasks (link, unlink),
      changes per box with roll-up, kinds & link types CRUD with field-schema validation.
- [x] Sample data: kinds, link types, the CC map (37 boxes incl. 7 defects), links, controls,
      external links, references.
- [x] Beyond plan: `stable_positions` (spread-out positions that change as little as possible,
      property-tested) so moving a box does not write revisions for its siblings; revisions carry
      the box whose history shows them; deleting a task or change drops its references; a process
      with a map and a section owning defects cannot be deleted; the box texts and defect groups
      the mockups show are loaded with the sample.

**Acceptance gate**: API tests incl. 401/403/404/409/422; integration tests for the database-level
guarantees (second root refused, parent from another process refused); every save writes exactly
one revision per changed object, with full content; deleting writes a deletion revision; the
sample map's tree equals the mockup's.
Met (2026-10-04, 548 tests green with `--e2e`): `tests/unit/test_knowledge.py`,
`tests/api/test_knowledge.py` (incl. the revision invariant after edits, moves and deletes),
`tests/integration/test_constraints.py`, `tests/integration/test_sample_data.py`.

### M15 · Knowledge view (reading the map)
- [x] `ProcessMap`: department/process header, Knowledge / FMEA / CPL switch, horizontal tree
      layout (ported from the mockup into `lib/maplayout.js`), collapse/expand, expand all,
      kind chips (show/hide), "Find in map", change counts rolled up, "No map yet".
- [x] Side panel: kind, path, owner/last reviewed, Markdown description, main URL card, key facts,
      typed links both ways, controls, external links, process changes in this branch (with state
      and "Show on timeline"), related tasks, copy link, History (revisions).
- [x] The map is usable by keyboard (boxes are buttons; arrows move between them) and scrolls on
      narrow screens with the panel below it.
- [x] Beyond plan: the map opens as an overview (only the selected box's branch open); while
      finding, matching branches open and the rest dims; a link chip opens the way to its box;
      change badges count what a closed branch hides; step numbers and extra fields (a defect's
      group) show in the panel; browser tests ignore only the Windows test server's socket
      finalizer warnings (a dropped connection), everything else stays an error.

**Acceptance gate**: `node --test` for the layout (no overlaps, parents centred on their children,
collapsed subtrees take no room) and for derivations (roll-up counts, typed links both ways);
Playwright: open `/knowledge/STL/CC/fm-level` → panel shows the mockup's controls, links, external
links and T-104; collapsing hides descendants; axe clean in both themes.
Met (2026-10-04, 554 tests green with `--e2e`): `tests/js/maplayout.test.mjs` (on the design's
sample map), `tests/e2e/test_knowledge.py`, `tests/e2e/test_accessibility.py` (the map, a
selected box, finding, the history, "no map yet", both themes).

### M16 · Knowledge editing and settings
- [x] Box editor drawer (`NodeEdit`): kind, name, "Sits under" + Move (tree picker), Markdown
      (Write/Preview, toolbar, images), typed links (type, target picker over maps and defects,
      "how" note, "or create one"), controls with their external links, external links with
      `?node=`, key facts / main URL / step number / owner by kind; "Mark reviewed"; add box,
      reorder siblings, delete; "Start the map".
- [x] Kinds & link types dialog (`MapSettings`), incl. simple extra fields per kind / link type.
- [x] "Where in the knowledge map" in the change drawer, a "Knowledge map" field in the task
      drawer, and the timeline's map-box filter.
- [x] Beyond plan: links are edited from either end (the editor sends every link of the box with
      its direction); images in a description belong to the box (D-090); a box search endpoint
      (`GET /api/boxes?q=`) serves every picker; the change list carries its boxes (`box_keys`)
      so the timeline filters without extra requests; sibling order is set in the move dialog.

**Acceptance gate**: Playwright: edit fm-level (description, a control, an external link) → panel
and History show the new revision; two editors saving the same box → the second gets the
conflict message; link LM-07 to a box → it shows on that box and every box above it and in the
timeline filtered by an ancestor; settings rename a link type → both directions update; API and
axe as usual.
Met (2026-10-04, 565 tests green with `--e2e`): `tests/e2e/test_knowledge_editing.py`,
`tests/api/test_knowledge.py` (box search, images, links from either end, `box_keys`),
`tests/e2e/test_accessibility.py` (editor, box picker, move dialog, kinds & link types while
editing a kind, both themes).

### M17 · FMEA and control plan (CPL) views
- [x] FMEA (`FmeaMap`): the map limited to failure modes and the steps leading to them, defect
      chips, same panel.
- [x] CPL (`DefectView`): defect list grouped (a "Group" field on the defect kind), causes per
      defect (failure modes that lead to it), Defect → Where → How diagram, "How it leads to …",
      controls with their links, "Show in knowledge map", process tabs incl. "All processes";
      "New defect" for editors.
- [x] Print views for FMEA and control plan ("Export PDF" uses the browser's Save as PDF).
- [x] Beyond plan: `GET /api/control-plan?department=` (the department's defects, what leads to
      them in any map the reader sees, the boxes above those causes, their controls); editors
      edit a defect (description, group, links) in the box editor from the CPL; the cause panel
      lists the tasks and changes about that cause; "All processes" is the CPL's default (D-091).

**Acceptance gate**: `node --test` for FMEA filtering and CPL causes on the sample graph (Sliver
lines has the mockup's 4 causes ~~in its order~~ in map order, D-091; Blisters 1; Transverse
cracks 2); Playwright: pick a defect, pick a cause, controls and links shown; print view renders;
axe clean.
Met (2026-10-04, 573 tests green with `--e2e`): `tests/js/controlplan.test.mjs`,
`tests/js/maplayout.test.mjs` (the FMEA), `tests/api/test_knowledge.py` (the control plan, who
may read it), `tests/e2e/test_fmea_cpl.py` (FMEA, CPL, one process, new defect, both print
sheets), `tests/e2e/test_accessibility.py` (FMEA, CPL, new defect, defect editor, phone).

### M18 · Releases
- [x] Domain: release scope, draft diff (added / changed / removed, revision a → b), which document
      each change affects (FMEA, CPL), warnings ("no controls yet", …), version numbering.
- [x] API + UI: release bar (current release, who released it and when, "Draft: N changes since
      v3", version picker, Export PDF, "Review & release vN"), blue dots, Release dialog
      (`Release`, without approver and notification: Q3, A17) that releases at once, views and
      print of an old version.
- [x] Sample data: v1, v2, v3 as real releases (v2 adds oscillation and cutting), and the four
      draft changes of the mockup made after v3.
- [x] Beyond plan: the sample's knowledge has a dated history (who changed what when), and its
      releases are made by the same rules from that history; a release names the version it was
      reviewed against (409 if someone released meanwhile, 422 if nothing changed); the draft
      groups changes per box and leaves out steps that only follow a new failure mode (D-093);
      a process with releases cannot be deleted.

**Acceptance gate**: unit and property tests: right after a release the draft is empty; an
in-scope edit appears in the draft, a knowledge-only edit does not; an old version stays exactly as
frozen after later edits and deletions; two releases at the same time get different numbers;
API 401/403; Playwright: release v4 → v4 is current and the draft is 0, v3 still viewable; the
sample shows "Draft: 4 changes since v3" with the mockup's markers.
Met (2026-10-05, 592 tests green with `--e2e`): `tests/unit/test_releases.py` (incl. Hypothesis
properties), `tests/api/test_releases.py`, `tests/integration/test_constraints.py` (one number
per process), `tests/js/releases.test.mjs`, `tests/e2e/test_releases.py`,
`tests/e2e/test_accessibility.py` (old versions, release dialog).

### M19 · Global search and stable links
- [x] `GET /api/search`: tasks (title, description, conversation), changes (title, what, why,
      period labels, scope tags, conversation), boxes (name, description, key facts, key, step
      number), defects; Unicode case-insensitive on every backend; grouped, ranked, with context
      snippets; filtered by permissions.
- [x] Search dialog (`GlobalSearch`): Ctrl K anywhere, sidebar entry, type filters with counts,
      arrow keys / Enter / Ctrl Enter, each result's link shown.
- [x] Every object has a working link and "Copy link"; external dashboards can link in.
- [x] Beyond plan: a box is also found by where it sits (the mockup finds "Powder entrapment" for
      "mould powder" through Mould › Mould powder); `/box/{key}` opens any box by its key alone
      (for dashboards), and a map link naming the wrong process forwards to the right one; the
      FMEA's "Copy link" keeps the box and the version; T-117's description carries the
      GlobalSearch mockup's text (D-094).

**Acceptance gate**: API tests: each type is found, nothing invisible is ever returned (per type),
"é" matches "É"; Playwright: Ctrl K, "mould powder" → the mockup's groups, Enter opens the box;
every route in the links table opens the right object in a fresh browser; axe clean.
Met (2026-10-05, 622 tests green with `--e2e`): `tests/unit/test_search.py` (incl. Hypothesis),
`tests/api/test_search.py` (each type, invisible per type, "é"/"É", "ß"/"SS"),
`tests/js/search.test.mjs`, `tests/js/routes.test.mjs` (box links), `tests/e2e/test_search.py`
(Ctrl K, filters, keys, Ctrl Enter, every link of the table in a fresh browser),
`tests/e2e/test_accessibility.py` (the search dialog with results, both themes).

### M20 · Hardening of the new modules
- [x] Scale: 2,000 changes and a 2,000-box map (API and browser time limits, like M10). Found and
      fixed on the way: the draft asked for revisions one by one (1.5 s → 0.25 s).
- [x] MS SQL DDL review of the new tables (filtered indexes, no multiple cascade paths, NVARCHAR),
      kept by `tests/unit/test_mssql_schema.py`. Found and fixed on the way: big maps sent more
      than MS SQL's 2,100 parameters in one statement (D-095); a test-wide guard now catches that
      on SQLite too.
- [x] Backup/restore covers everything new (releases, revisions, box images: a test); strict CSP
      holds (the new browser tests assert no console errors); docs (ARCHITECTURE, AUTH,
      OPERATIONS, DECISIONS) complete.
- [ ] Demo seeding on the Linux server: the sample now brings process changes, the knowledge map
      and releases v1-v3 (OPERATIONS.md); reseeding the live demo is left to its owner.

**Acceptance gate**: full suite green; scale tests within limits; axe clean on every new view and
dialog; no console errors under the CSP.
Met (2026-10-05, 670 tests green with `--e2e`): `tests/api/test_scale_processes.py`,
`tests/e2e/test_scale_processes.py` (every view ~1.4 s or less on the big data),
`tests/unit/test_mssql_schema.py`, `tests/integration/test_session.py` (any number of ids),
`tests/integration/test_backup.py` (releases and box images come back), the parameter guard in
`tests/conftest.py`. Still open from M10: a run of the suites against a real SQL Server.

### M21 · API tokens for AI agents (beyond the design)
Asked for on 2026-10-06: let people control the board through their AI assistant (D-097).
- [x] `api_tokens` table and migration; Bearer authentication that never falls back to cookies or
      anonymous access; CSRF exemption for Bearer requests; read and write scopes, never
      administration; expiry by choice; at most 25 live tokens; "last used" kept.
- [x] Token endpoints (`/api/auth/tokens`, `/api/admin/users/{id}/tokens`), audit entries, tokens
      cannot manage tokens or passwords; `GET /api/auth/me` names the token.
- [x] "via <token name>" on task events, posts and their edits and history, knowledge revisions,
      releases (`services/actors.py`, `ViaBadge`, `actorName`).
- [x] Profile page (the sidebar's user block links to it): tokens, new token, the token shown once
      with the commands for `TASKBOARD_TOKEN`; the agent guide (`GET /api/agent-guide`), its
      endpoint list generated from OpenAPI; tokens in the admin's account dialog.

**Acceptance gate**: API tests for every refusal (read scope, administration, bad/revoked/expired
token, suspended owner, managing tokens through a token, a Bearer header borrowing a session) and
for the "via" marks; unit tests for scopes and the guide; JS tests; a browser test from creating a
token to an agent's post marked "via" and revoking; axe clean on the profile page and its dialogs.
Met (2026-10-06): `tests/api/test_tokens.py`, `tests/unit/test_agent_guide.py`,
`tests/unit/test_access_policy.py`, `tests/js/tokens.test.mjs`, `tests/e2e/test_tokens.py`,
`tests/e2e/test_accessibility.py` (profile, new token, the token shown once).

### M22 · Full-width drawers and an image lightbox (beyond the design)
Asked for on 2026-10-10: a focused conversation instead of a side panel, and images that open
over the page (D-098, D-099).
- [x] "Full width" toggle in every drawer's header (`components/drawer.js`): everything but the
      sidebar (full or rail), the content in a readable middle column, remembered per browser; no
      toggle on phones or on the task and change pages.
- [x] Lightbox (`components/lightbox.js`): any image in rendered Markdown opens full size (never
      larger than the screen) over the page; a click anywhere or Escape closes it and leaves a
      drawer below open; Ctrl/⌘ click opens the image in a new tab.

**Acceptance gate**: browser tests for the widths (side panel, full width, collapsed sidebar,
remembered, tabs keep it) and for opening and closing the lightbox; axe clean on both, both themes.
Met (2026-10-10): `tests/e2e/test_tasks.py` (full width), `tests/e2e/test_conversation.py`
(lightbox), `tests/e2e/test_accessibility.py` (the full-width drawer and the lightbox).

---

## Risks and how the plan handles them

1. **Generalizing conversations** (posts and attachments get a second owner). Done first in M12
   with a migration-with-data test; task conversation tests must stay green unchanged.
2. **Revisions drifting from the rows.** All writes to boxes, links and controls go through one
   service method that also writes the revision; a test compares every object's current row with
   its latest revision's content.
3. **Release correctness** (an auditor will rely on old versions). Views are pure functions of a
   graph; the same function draws current and released graphs; property tests check that releases
   never change after the fact.
4. **Dates and "today".** States depend on the date. The server supplies `today`; tests pin it;
   the sample's dates are shifted when seeding demos.
5. **Map layout and accessibility.** The tree layout is absolute positioning (as in the mockup); it
   is a pure, tested function, and the boxes are real buttons in reading order.
6. **Scope creep toward full IATF/AIAG-VDA FMEA.** Out of scope (DESIGN goal 3). The model keeps
   the doors open (fields JSON + schemas, links with fields, controls as records, causes as boxes,
   references with roles), and nothing more is built.

## Assumptions (say if any is wrong)

- A10. Processes are managed under Administration › Organization with `people.manage`.
- A11. The defect catalogue is **per department** (shared by its processes), as the CPL link
  `/cpl/stl/…` suggests; each defect names a section of that department for its rights (Q2).
- A12. Change keys: process code + two-digit number, next free per process; kept when a change moves.
- A13. Box keys: slug from the name at creation, unique across all boxes, never changed.
- A14. Period posts are structured change data: anyone with `change.edit` may edit them or set an
  end date; plain comments stay editable by their author only (D-049).
- A15. Ending a permanent process change keeps it a process change ("Ended …"), it does not turn
  into a test; a planned process change is drawn as a dashed orange bar.
- A16. "Export PDF" is a print view saved as PDF by the browser (no PDF library on the server).
- A17. No notifications (D-017 stands): the release dialog's "Notify everyone…" checkbox and
  per-box review reminders (DESIGN open question 3) are left out; boxes show "last reviewed" and
  get a "Mark reviewed" action.
- A18. In CPL "All processes", the release bar is hidden (each process has its own releases).
- A19. "Compare v3 and draft side by side" is replaced by the per-change summaries in the release
  dialog (a later addition if wanted).
- A20. Tasks link to map boxes from a new "Knowledge map" field in the task drawer (no mockup shows
  where; the change drawer's pattern is reused).
- A21. Search uses the existing case-insensitive matching (no full-text engine), fine at this scale.
- A22. Changes have no automatic events in their conversation (the mockup shows none).

## Decisions (session of 2026-10-04)

Recorded in detail in [`DECISIONS.md`](DECISIONS.md) (D-079 to D-082).

- Q1 → **Viewer and Editor cover the new modules.** Viewer: `change.view`, `knowledge.view`.
  Editor: also `change.edit`, `change.comment`, `knowledge.edit`, `knowledge.release`.
  Administrators: everything. Anonymous visitors (Viewer) therefore see the new modules by default.
- Q2 → **Each process names its owning section**, and section-scoped rights apply to it exactly as
  to tasks (defects, which have no process, name a section too).
- Q3 → **No approval step**: a release is made at once by someone with `knowledge.release`
  (DESIGN open question 1).
- Q4 → **Images only**, as today (D-047); documents are referred to by link.
