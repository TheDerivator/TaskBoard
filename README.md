# TaskBoard

A browser app for tracking a team's tasks: one team-wide priority list, a lane per person, and
projects that unfold as numbered trees. Built with FastAPI, SQLAlchemy (SQLite by default, MS SQL
ready) and a build-free Preact/htm frontend.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (it provides Python 3.14).

```sh
uv sync                                  # install dependencies
uv run python -m taskboard serve --reload
```

Open <http://127.0.0.1:8000>. API documentation: <http://127.0.0.1:8000/api/docs>.

In production, run `python -m taskboard serve` behind a TLS reverse proxy: see
[running TaskBoard](docs/OPERATIONS.md) (Linux with systemd and Caddy/nginx, Windows with a
service and IIS, backups, upgrades, MS SQL). `python -m taskboard backup` and `restore` handle
backups.

## Configuration

Environment variables prefixed `TASKBOARD_` (or a `.env` file; see [`.env.example`](.env.example)):

| Variable | Default | Meaning |
|---|---|---|
| `TASKBOARD_DATA_DIR` | `./var` | Database file and uploads. Use e.g. `C:\ProgramData\TaskBoard` or `/var/lib/taskboard` in production. |
| `TASKBOARD_DATABASE_URL` | SQLite in the data dir | Any SQLAlchemy URL (MS SQL via `mssql+pyodbc://...`). |
| `TASKBOARD_INITIAL_ADMIN_PASSWORD` | generated | Password of the built-in `admin` account on first start. |
| `TASKBOARD_COOKIE_SECURE` | auto | Force the Secure flag on session cookies. |
| `TASKBOARD_HOST`, `TASKBOARD_PORT` | `127.0.0.1`, `8000` | For `python -m taskboard serve`. |
| `TASKBOARD_ENVIRONMENT` | `development` | Set `production` on servers. |
| `TASKBOARD_BASE_PATH` | `/` | URL prefix when published under one, e.g. `/taskboard/`. |
| `TASKBOARD_TRUSTED_PROXIES` | `127.0.0.1,::1` | Reverse proxies whose `X-Forwarded-*` headers are believed. |

SSO (Microsoft Entra ID, Windows sign-in) is off unless configured: see
[accounts and SSO](docs/AUTH.md). Step-by-step guides for Windows servers:
[behind IIS](docs/IIS.md), and [with Windows sign-in, without IIS](docs/WINDOWS-SIGNIN.md).

## Development

```sh
uv run python scripts/check.py --fix    # format, lint, type-check, architecture contracts, tests
```

Project docs: [plan and progress](docs/PLAN.md) · [architecture](docs/ARCHITECTURE.md) ·
[decisions](docs/DECISIONS.md) · [code map](docs/CODEMAP.md) · [accounts and SSO](docs/AUTH.md) ·
[operations](docs/OPERATIONS.md).
