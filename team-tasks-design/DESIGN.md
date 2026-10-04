# Team Tasks: design handoff

A browser app for a steel-plant team. It has four parts:

1. **Tasks**: a team-wide prioritised task list, with people lanes, projects, conversations.
2. **Process changes**: tests and permanent changes per process, with a timeline (Gantt).
3. **Process knowledge**: a knowledge graph per process, read as Knowledge, FMEA or CPL (control plan), with releases.
4. **Shared features**: global search and a shareable link for every object.

Frontend: plain JS (with small libraries at most). Backend: Python / Shiny.
This folder is the **design reference**. It is not code to ship.

> **How to read this document.** The screens and behaviour decisions marked *settled* are what the product owner agreed to. The **data model is a proposal**: it shows one way to support the screens and to keep future extensions open. The implementer is expected to refine or change it once the details are worked out, as long as the goals in "Design goals" still hold.

---

## Design goals

1. **One source of truth per fact.** Tasks, process changes and knowledge boxes are stored once and shown in several views (priority / people / projects; list / timeline; knowledge / FMEA / CPL).
2. **Open-ended where people need it.** Scope tags on process-change periods, box kinds, link types and extra fields are free-form or configurable, not hard-coded lists.
3. **Possible to grow into a full IATF 16949 / AIAG–VDA process FMEA and control plan later, without re-structuring.** This is an explicit goal, *but not part of the first implementation*. The first version stays lightweight. See "Extensibility toward a full FMEA + control plan".
4. **Everything has a stable link** so people can paste it into email or chat, and external dashboards can link back in.
5. **Roles and permissions** already exist in the earlier version of the app. Keep extending that model; this design phase does not specify it.

---

## Mockup files (`mockups/`)

Each `*.dc.html` file is one screen from the design canvas. They use a small template dialect
(`<x-dc>`, `<sc-for>`, `<sc-if>`, `{{holes}}`, a `class Component extends DCLogic` script) and **will not render on their own**.
Read them as the spec for layout, colors, fonts, spacing and copy. Rebuild them in the real stack; don't port the template syntax.
Sample data lives inside each file's `renderVals()`, and also in `sample-data.json`. Some screens contain working logic (drag-and-drop, tree layout, filtering) that is a useful reference.

All sample content (people, tasks, process figures, server names like `grafana.plant.local`) is **invented**. Values in square brackets such as `[LIMIT]` are placeholders.

### Tasks

| File | Screen |
|---|---|
| `Main.dc.html` | **Priority view**: every task in one team-wide ranked list. Drag rows to reorder (working drag-and-drop and filter logic inside). |
| `People.dc.html` | **People lanes**: one column per person, in team priority order. Solid card = person leads the task; dashed = helps. |
| `Projects.dc.html` | **Projects view**: project/section tree on the left; the selected project or section unfolds as a numbered outline (1, 1.1, 1.1.1) with its tasks. |
| `TaskDetail.dc.html` | **Task drawer, Details tab**: title, description, lifecycle, department/section, lead, helpers, project placements. |
| `ProjectPlacement.dc.html` | **Add to another project** dialog: pick a project (ones already used are disabled), then a node in its tree. |
| `TaskConversation.dc.html` | **Task drawer, Conversation tab**: Markdown comments, status updates, automatic events, image attachments. |

### Process changes

| File | Screen |
|---|---|
| `ChangesList.dc.html` | **List** per department/process: periods as chips and the current state (In effect / Test running / Planned / Tests ended). |
| `ChangesGantt.dc.html` | **Timeline (Gantt)**: last 6 months plus coming weeks. Tests = blue bars, process change = orange bar with arrow to the right edge, planned = dashed, line for today. Hover shows dates and scope. Filters: process, map box, range. |
| `ChangeDetail.dc.html` | **Change drawer, Details tab**: what, why, owner, process, **where in the knowledge map** (linked boxes), read-only summary of periods. |
| `ChangeConversation.dc.html` | **Change drawer, Conversation tab**: comments mixed with **period posts** (label, from/to, "no end date", scope tags, Markdown). |

### Process knowledge

| File | Screen |
|---|---|
| `ProcessMap.dc.html` | **Knowledge view**: the full map for one process as a collapsible tree. Box kinds can be shown or hidden. Side panel: description, key facts, typed links, controls, external links, process changes in this branch, owner/last reviewed, copy link. |
| `FmeaMap.dc.html` | **FMEA view**: the same map, showing only failure modes and the steps leading to them. Shows the **release bar** (current release, draft changes, version picker, PDF export, "Review & release"). Blue dots mark boxes changed since the last release. |
| `DefectView.dc.html` | **CPL view (control plan)**: pick a defect, see where in the process it comes from (defect → step → failure mode), then how each cause is controlled (Prevent/Detect) with links to dashboards and diagrams. Has the same release bar. Process tabs include "All processes". |
| `NodeEdit.dc.html` | **Edit a box**: kind, name, place in the tree, Markdown description, typed links to other boxes, controls, external links. |
| `MapSettings.dc.html` | **Kinds & link types** settings: configurable box kinds and link types (forward/backward names). |
| `Release.dc.html` | **Release FMEA & CPL**: changes since the last release (with revisions and which document each affects), warnings, release note, approver. |

### Shared features

| File | Screen |
|---|---|
| `GlobalSearch.dc.html` | **Search everything** (Ctrl K, also in every sidebar): results grouped by knowledge, process changes, tasks (including conversation text) and defects, each with its link. |

---

## Module 1 – Tasks (settled)

1. **One team-wide ranking.** No ranking per project or person. Store as an ordered list or integer rank.
2. **Filters never change the rank.** They only hide rows; the rank shown is always the global one. Dragging within a filtered list moves the task relative to the row it was dropped on.
3. **Keyword search** matches title + description, case-insensitive.
4. **Lifecycle**: `idea → started → done → archived`. By default Idea, Started and Done are shown; Archived is hidden.
5. People and Projects views use the same global rank order.
6. **Conversation posts are Markdown.** Images are uploaded files on the server; the Markdown only links to them. Posts marked as updates get a highlighted card and an "Updates only" filter.
7. **Projects are trees** of sections at any depth. A task sits in **at most one place per project** but can be in several projects. A task can sit on any node, including the project's top level. Counts include descendants.
8. **Keyboard reordering** is wanted **later**; drag-and-drop only for now.

## Module 2 – Process changes (settled)

1. A department has processes (e.g. STL: Convertor, Ladle metallurgy, Continuous casting).
2. A **change** belongs to one process and has what, why, owner, and a conversation.
3. Periods are posted **in the conversation** as special posts. **A period with an end date is a test; one without is a permanent process change.** The end date is inclusive.
4. **Scope is open-ended**: free tags (e.g. `CC2`, `IF-01`, `Heats 41230–41236`) plus Markdown. Suggest tags already used on the same process; never force a fixed list.
5. The **current state is derived, never stored**: an open period that has started → In effect; a test period containing today → Test running; a future period → Planned; otherwise → Tests ended.
6. Editing a period edits its post (shows "edited", history kept). "Set end date" on a process change ends it, which is how a change gets reverted.
7. **Timeline filter**: changes with any period starting in the range (default: last 6 months plus planned periods).
8. **A change can link to boxes in the knowledge map.** The change then appears on those boxes and on every box above them (the counts roll up). The timeline can be filtered by map box.

## Module 3 – Process knowledge (settled at screen level)

### The map

- One map per process. The **root is the same Process record** used by process changes.
- Each **box** has a **kind**: Process step, Knowledge, Reference (main URL), Rule (e.g. planning restrictions), Failure mode, Defect. Kinds are **configurable** (`MapSettings`).
- Each box has **one place in the tree** ("part of") and any number of **typed links** to other boxes ("leads to", "caused by", "restricts", "prevents", "explains", "documented in", "see also"…). Link types are configurable. Each has a forward and a backward name, so a link shows up on both boxes.
- Boxes have a Markdown description, optional key facts (key/value), external links (dashboards, graphs, calibration diagrams, documents, hosted on other servers and opened in a new tab), and an owner and last-reviewed date.
- **Failure modes** "lead to" **defects**. Defects are shared across processes (one catalogue).
- **Controls** (Prevent / Detect) belong to a failure mode (later also to a cause), each with its own external links.

### Three views of the same data

| View | Shows | Starts from |
|---|---|---|
| **Knowledge** | Everything | The process (tree) |
| **FMEA** | Failure modes and the steps leading to them | The process (tree), filtered |
| **CPL** (control plan) | Defect → where it comes from → how it is controlled | A defect |

All three share the same header: department, process tabs, view switch. CPL also offers "All processes", because a defect can come from several processes.

### Versioning (proposal, agreed in principle)

1. **Every box, link and control keeps its own revision history.** Each edit is a new revision storing the **full content** (all fields, as JSON) plus author and time. Deletions are revisions too. This is all the Knowledge view needs: per-box "History".
2. **A release is a frozen list** of `(object, revision)` for everything the FMEA and CPL show for one process. It gets a number (v1, v2…). Viewing an old version = drawing the view from that list.
3. **The draft is calculated, never stored**: comparing current revisions with the latest release gives "Draft: N changes since v3" and the "changed" markers on boxes.
4. **FMEA and CPL share one release and one number.** The release screen shows which document each change affects. Separate numbering could later be derived from the same releases if ever needed.
5. Releases can require **approval** (draft → pending → approved). Whether a second person is needed is still **open**.
6. Knowledge-only edits are outside the release scope and versioned per box only.

---

## Shared features

### Global search (planned for, not necessarily in the first release)

- One search over tasks (title, description, conversation text), process changes (incl. period scope), knowledge boxes (name, description, key facts) and defects.
- Opened with Ctrl K or from the sidebar. Results are grouped by type, each showing its link.
- PostgreSQL full-text search is probably enough; nothing in the design depends on a separate search engine.

### Stable links (planned for)

Every object gets a stable address, used by the app's own routing and safe to paste anywhere. Proposed pattern:

| Object | Link |
|---|---|
| Task | `/tasks/T-104` |
| Process change | `/changes/stl/cc/CC-31` |
| Knowledge box | `/knowledge/stl/cc/fm-level` |
| FMEA view (optionally a box, optionally a release) | `/fmea/stl/cc?box=fm-level&release=v3` |
| Control plan for a defect | `/cpl/stl/sliver-lines` |

External links can carry the box ID as a parameter (option in the edit screen) so dashboards open filtered.

---

## Data model (proposal)

> A proposal, not a contract. Names, splits and storage choices may change during implementation. What should survive are the **principles** in the next section.

### Tasks and projects

- **Person**: `code`, `name`, `color`, `department`, `section`.
- **Department / Section**: Section belongs to Department.
- **Task**: `id` (e.g. `T-104`), `title`, `description`, `rank`, `status`, `lead` (exactly one person), `helpers` (0..n), `department`, `section`.
- **Project**: `id`, `name`, `color`.
- **ProjectNode**: `id`, `project_id`, `parent_id` (null = top level), `position`, `name`. Display numbers (`2.2.1`) derive from positions.
- **Placement**: `task_id`, `project_id`, `node_id` (nullable). **Unique on (`task_id`, `project_id`).**
- **Post**: `parent_type` (`task` | `change`), `parent_id`, `author`, `created_at`, `body_md`, `is_update`, `attachments`.
- **Event**: automatic entries in a conversation (lifecycle changes, people added/removed).

### Process changes

- **Process**: `id`, `department`, `name`.
- **Change**: `id` (e.g. `LM-07`), `process_id`, `title`, `what_md`, `why_md`, `owner`.
- **ChangePeriod** (a special post): `change_id`, `author`, `created_at`, `start_date`, `end_date` (nullable), `label`, `scope_tags[]`, `body_md`.

### Process knowledge

- **BoxKind** (settings): `id`, `name`, `style`, `field_schema` (JSON: which extra fields this kind has).
- **LinkType** (settings): `id`, `forward_name`, `backward_name`, `field_schema`.
- **Box**: `id` (stable), `process_id`, `kind_id`, `parent_id` (place in the tree), `position`, `name`, `body_md`, `main_url` (references), `facts` (key/value), `fields` (JSON, validated by the kind's schema), `step_no` (optional, e.g. `OP20`), `owner`, `reviewed_at`.
- **Defects** can be Boxes of kind Defect in a shared, process-independent catalogue, or a separate table. The implementer can choose.
- **Link**: `id`, `from_box`, `to_box`, `type_id`, `note_md` (the "how"), `fields` (JSON, validated by the link type's schema).
- **Control**: `id`, `box_id` (failure mode now, cause later), `type` (`prevent` | `detect`), `text`, `fields` (JSON).
- **ExternalLink**: `id`, `owner_type` (`box` | `control` | …), `owner_id`, `kind` (dashboard, graph, calibration diagram, document), `label`, `url`, `pass_box_param`.
- **Reference** (one generic table linking other modules to boxes): `source_type` (`task` | `change`), `source_id`, `box_id`, `role` (e.g. `affects`; later `action`).

### Versioning

- **Revision**: `object_type`, `object_id`, `rev`, `content` (full JSON), `author`, `created_at`, `deleted` (bool).
- **Release**: `id`, `process_id`, `number`, `status` (`draft` | `pending` | `approved`), `note`, `created_by`, `approved_by`, `approved_at`, `team` (optional, list of people).
- **ReleaseItem**: `release_id`, `object_type`, `object_id`, `rev`.

---

## Extensibility toward a full FMEA + control plan

**Goal:** it should be possible to grow the FMEA and CPL views into an IATF 16949 / AIAG–VDA compliant process FMEA and control plan **later**, with additional implementation, *without restructuring the data*. The first implementation deliberately leaves these features out to keep the app light.

This is based on public summaries of IATF 16949 and the AIAG–VDA FMEA handbook, not on the standards themselves. Check against the official documents and your customers' specific requirements before building any of it.

### Principles that keep the door open (please keep these)

1. **Extensible fields per kind and per link type**, stored as JSON and described by a schema in settings. New FMEA/CPL fields become settings, not migrations.
2. **Links can carry fields**, because in an FMEA some values belong to a connection (severity on failure mode → effect, occurrence on cause → failure mode).
3. **Controls are their own records with stable IDs**, attachable to failure modes and later to causes. Never store controls as text inside a box.
4. **Causes are boxes**, connected with "caused by" links, never free text.
5. **One generic table for references from tasks/changes to boxes**, with a role. FMEA actions later become tasks with role `action`.
6. **Stable box IDs and an optional step number** (`OP10`, `OP20`…), so a flow diagram, FMEA table and control plan can line up.
7. **Revisions store the full content as JSON**, so releases automatically cover fields added later.
8. **The map is the storage; the standard tables are views/exports.** The FMEA and control-plan forms that auditors expect can be generated from the same data.

### How the full version would map onto this model

| AIAG–VDA / IATF concept | Where it would live |
|---|---|
| Structure analysis (process item, step, work element / 4M) | Step boxes in the tree; work elements as child boxes with a `4M` field |
| Function analysis (functions, requirements, characteristics) | `fields` on step boxes, or a "Function / Characteristic" box kind |
| Failure chain (effect – mode – cause) | Defect box ← "leads to" ← Failure mode ← "caused by" ← Cause box |
| Effect levels (own plant / customer plant / end user) | `level` field on defect boxes, or on the "leads to" link |
| Severity / Occurrence / Detection, Action Priority | `fields` on links and controls; AP computed |
| Optimisation actions (owner, due date, status, re-rating) | Tasks linked with role `action`; re-rating as new revisions |
| Special characteristics (CC/SC) | Field on characteristics and controls, shown in both views |
| Control plan row (characteristic, spec/tolerance, method, sample size & frequency, control method, reaction plan) | `fields` on Control |
| Control plan phases (prototype / pre-launch / production) | Field on Control, or separate releases per phase |
| Review triggers (changes, complaints, non-conformances) | Process changes and tasks linked to boxes → mark the release draft as "needs review" |
| Approvals and history | Releases and revisions |
| Standard FMEA / control plan forms | PDF / Excel export generated from a release |

---

## Open questions

1. Does a release need approval by a second person, or is that overkill for this team?
2. Defects: boxes of a special kind or their own table? (Either is fine.)
3. Per-box "last reviewed" reminders: what interval, and who gets notified?
4. Should the last chosen process be remembered across Process changes and Process knowledge? (Suggested: yes.)

## Suggested build order

1. Tasks module (priority, people, projects, conversations).
2. Process changes (list, conversation with period posts, timeline).
3. Process knowledge: boxes, links, kinds/link types, Knowledge view, edit screen.
4. FMEA and CPL views, then revisions and releases.
5. Global search and stable links (plan the URL scheme from step 1; the search screen can come last).

---

## Visual system

- Fonts: **IBM Plex Sans** (UI) and **IBM Plex Mono** (IDs, ranks, labels, counts, dates), both from Google Fonts.
- Ground `#F4F2EE`, surfaces `#FFFFFF`, ink `#1D2124`, secondary text `#5E5A54`, borders `#DDD8CF` / `#CFCAC1`.
- Sidebar `#1D2124`, active item `#30363A`.
- Primary action / accent `#B34A15` (top 3 ranks are shown in this color).
- Lifecycle pills: Idea = white with dashed `#948E84` border; Started = `#DCE6F7` / `#1E4686`; Done = `#DCEEE2` / `#1F5C37`; Archived = `#EEEBE5` / `#5E5A54`.
- Project colors: Action plan surface quality `#C4561C`, Projects 2026 `#2D5BA8`, Safety 2026 `#1F7A6E`.
- Process changes: test `#3A6FC4`, process change `#C4561C`, planned = dashed outline. These two colours were checked to stay distinguishable for colour-blind readers, and each also has its own shape.
- Box kinds: step = white with ink border; knowledge `#EFECE6`; reference `#E3EBF8`; rule `#EEE8F6`; failure mode `#FBEFE8`; defect = ink pill. Each kind also has an icon, so colour is never the only cue.
- Release/draft marker: blue dot `#2D5BA8`.
- Radii: 8px for controls, 10px for panels. Touch targets are at least 44px.
