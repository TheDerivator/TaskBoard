# TaskBoard: guide for AI agents

Team task board (FastAPI + SQLAlchemy backend, static Preact/htm frontend). Read in this order:

1. [`docs/PLAN2.md`](docs/PLAN2.md): the current plan (process changes, process knowledge,
   search; milestones M11–M20), what is done, what is next. **Keep its status table and
   checkboxes current** when you finish work. [`docs/PLAN.md`](docs/PLAN.md) is the original
   build (M0–M10, the Tasks module).
2. [`docs/CODEMAP.md`](docs/CODEMAP.md): generated tree of every file with a one-line summary.
   Use it to jump to the right file instead of searching.
3. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): layers, data model, access control,
   portability rules, and recipes ("add an endpoint", "change the schema", ...).
4. [`docs/DECISIONS.md`](docs/DECISIONS.md): why things are the way they are. Don't silently
   reverse a *Confirmed* decision; ask.

Design reference (not code): `team-tasks-design/` (DESIGN.md, mockups, sample data).

## Commands

```sh
uv run python scripts/check.py --fix   # format, lint, types, contracts, codemap, tests: run before finishing
uv run python scripts/check.py --e2e   # also browser tests (needs: uv run playwright install chromium)
uv run pytest tests/unit -q            # fast subset
uv run pytest -m e2e                   # only the browser tests
node --test tests/js/*.test.mjs        # only the JS unit tests
uv run python -m taskboard serve --reload   # dev server on http://127.0.0.1:8000
uv run python -m taskboard backup           # zip of database + uploads (restore: see docs/OPERATIONS.md)
```

Heredocs in the Bash tool mangle backslashes: write edit scripts with the Write tool, or use Edit.

`python` is not on the shell PATH: always go through `uv run`.

## Rules

- Layers: `cli → web → api → services → schemas → identity → db → domain`, imports only go rightwards
  (import-linter enforces it). Routers never touch the database; services enforce permissions.
- `app.py` stays a 3-line entrypoint.
- Every file starts with a one-line docstring/comment; it feeds the code map.
- Schema changes need an Alembic migration (a test compares models and migrations).
- Keep code portable to MS SQL (rules in ARCHITECTURE.md) and OS-neutral (Windows and Linux).
- What can be tested is tested: domain rules as unit tests, endpoints with their 401/403 cases,
  pure JS in `tests/js/`, flows in `tests/e2e/`.
- No external network resources at runtime: vendor JS libraries and fonts under `taskboard/static/`.

## Backslash-heavy content: avoid Bash heredocs

When writing files that contain backslashes (LaTeX-style `\section`, `\\`,
`\u` escapes, regex patterns, etc.), do NOT use `Bash` with a heredoc
(`<<'EOF' ... EOF`) to create or edit the file. Backslashes can get
collapsed or altered before the shell ever sees them, due to intermediate
JSON/string encoding of the command — even though the heredoc's quoting
itself is correct.

The failure is silent and two-stage: `\\binom` arrives as `\binom`, then the next
layer interprets that escape — Python turns `\b` into a literal backspace (U+0008)
and `\t` into a tab — so `\binom m3` ends up as a control character followed by
`inom m3`. Nothing raises an error, and the result still looks correct in terminal
output. This compounds with the AGENTS.md rule "Never write LaTeX through a
non-raw Python string": if such content must pass through Python at all, use
`r"..."`.

**Instead:** use the `Write` (new file) or `Edit` (existing file) tool to write such
content directly. These write the file content straight to disk without
an extra shell-interpretation step, so backslashes survive intact.

If a Bash step is still needed afterward (e.g. running a script), write
the file first with Edit, then invoke it separately:
`uv run python script.py` rather than piping content through Bash.