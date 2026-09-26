# Team Tasks: design handoff

A browser app for tracking a team's tasks. Frontend: plain JS (with small libraries at most). Backend: Python / Shiny.
This folder is the **design reference**. It is not code to ship.

## Mockup files (`mockups/`)

Each `*.dc.html` file is one screen from the design canvas. They use a small template dialect
(`<x-dc>`, `<sc-for>`, `<sc-if>`, `{{holes}}`, a `class Component extends DCLogic` script) and **will not render on their own**.
Read them as the exact spec for layout, colors, fonts, spacing and copy. Rebuild them in the real stack; don't port the template syntax.
Sample data lives inside each file's `renderVals()`, and also in `sample-data.json`.

| File | Screen |
|---|---|
| `Main.dc.html` | **Priority view**: every task in one team-wide ranked list. Rows can be dragged to reorder; this file also contains working drag-and-drop and filter logic you can use as a reference. |
| `People.dc.html` | **People lanes**: one column per person, cards in team priority order. A solid card means the person leads the task; a dashed card means they help on it. Toggle: "Lead + helping" / "Lead only". |
| `Projects.dc.html` | **Projects view**: on the left, a tree of projects and their sections (the selected project expands; counts include sub-sections). On the right, the selected project or section unfolds as a numbered outline (1, 1.1, 1.1.1) with its tasks under each node, in global rank order. A breadcrumb lets you step back up. Archived tasks are hidden unless toggled on. |
| `TaskDetail.dc.html` | **Task drawer, Details tab**: title, description, lifecycle picker, department, section, lead, helpers, and project placements (one row per project showing the section path, with Move and Remove). |
| `ProjectPlacement.dc.html` | **Add to another project** dialog: step 1, pick a project (projects the task is already in are disabled); step 2, pick a node in that project's tree, or top level. |
| `TaskConversation.dc.html` | **Task drawer, Conversation tab**: Markdown comments, status updates, automatic lifecycle events, and a writing box with Write/Preview and image attachments. |

## Data model

- **Task**: `id` (e.g. `T-104`), `title`, `description`, `rank` (int), `status`, `lead` (exactly one person), `helpers` (0..n people), `department`, `section`. Project membership lives in **Placement** (below).
- **status** is one of `idea → started → done → archived`.
- **Person**: `code` (initials), `name`, `color` (avatar background), `department`, `section`.
- **Project**: `id`, `name`, `color`.
- **ProjectNode** (a section or subsection of a project; any depth, 3 levels in practice): `id`, `project_id`, `parent_id` (null = top-level section), `position` (order among siblings), `name`. The display number (e.g. `2.2.1`) is derived from the positions.
- **Placement**: `task_id`, `project_id`, `node_id` (null = top level of the project). **Unique on (`task_id`, `project_id`)**: a task sits in at most one place per project, but it can be in several projects. The node must belong to that project.
- **Department / Section**: Section belongs to Department (e.g. STL → Quality, Process, Maintenance; R&D → Coatings).
- **Post** (conversation): `task_id`, `author`, `created_at`, `body_md` (Markdown), `is_update` (bool), `attachments` (image files).
- **Event** (automatic, shown in the conversation): lifecycle changes, and people added or removed.

## Behaviour decisions (settled)

1. **One team-wide ranking.** There is no ranking per project or per person. Store it as an ordered list or an integer rank.
2. **Filters never change the rank.** Filters only hide rows; the rank number shown is always the global one. Dragging within a filtered list moves the task relative to the row it was dropped on.
3. **Keyword search** matches title + description, case-insensitive.
4. **Default lifecycle filter**: Idea, Started and Done are shown; Archived is hidden.
5. The People and Projects views both use the same global rank order.
6. **Conversation posts are Markdown.** Store images as uploaded files on the server and put only a link to each in the Markdown. Posts marked as updates get a highlighted card and their own "Updates only" filter.
7. **Projects unfold as trees.** Selecting a section shows that section's whole subtree. Counts on a node include its descendants. A task can be placed on any node, not only a leaf. The Priority view shows each placement as a chip: project name plus node number.
8. **Keyboard reordering** (e.g. move up/down) is wanted, but **later**. Drag-and-drop only for now.

## Visual system

- Fonts: **IBM Plex Sans** (UI) and **IBM Plex Mono** (IDs, ranks, labels, counts), both from Google Fonts.
- Ground `#F4F2EE`, surfaces `#FFFFFF`, ink `#1D2124`, secondary text `#5E5A54`, borders `#DDD8CF` / `#CFCAC1`.
- Sidebar `#1D2124`, active item `#30363A`.
- Primary action / accent `#B34A15` (top 3 ranks are shown in this color).
- Lifecycle pills: Idea = white with dashed `#948E84` border; Started = `#DCE6F7` / `#1E4686`; Done = `#DCEEE2` / `#1F5C37`; Archived = `#EEEBE5` / `#5E5A54`.
- Project colors: Action plan surface quality `#C4561C`, Projects 2026 `#2D5BA8`, Safety 2026 `#1F7A6E`.
- Radii: 8px for controls, 10px for panels. Touch targets are at least 44px.
