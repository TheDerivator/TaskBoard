# Running TaskBoard

How to install, run, back up and upgrade TaskBoard on the two targets: a **Linux demo server**
(built-in accounts only, internet-facing) and a **corporate Windows server** (built-in accounts,
optionally Microsoft Entra ID or Windows sign-in, SQLite now and MS SQL later). SSO configuration
itself is in [`AUTH.md`](AUTH.md).

> The commands and configuration files below follow each product's documentation. The Python
> side (serve, backup, restore, migrations, proxy headers) is covered by the test suite, but the
> systemd, Caddy/nginx, WinSW and IIS parts have not been tried on a real server yet. Please
> report what needed changing.

## The shape of a deployment

```
browser ──HTTPS──> reverse proxy (Caddy / nginx / IIS) ──HTTP──> TaskBoard on 127.0.0.1:8000
                   TLS, HSTS, upload size limit                   one process: python -m taskboard serve
                                                                  data folder: database + uploads
```

- **One process.** `python -m taskboard serve` runs Uvicorn with one worker, which is plenty for a
  team. SQLite serializes writes anyway (D-020).
- **Only the proxy reaches the app.** TaskBoard listens on `127.0.0.1` (the default
  `TASKBOARD_HOST`). The proxy is listed in `TASKBOARD_TRUSTED_PROXIES` (default `127.0.0.1,::1`),
  so the client's address and scheme come from its `X-Forwarded-*` headers.
- **One data folder** (`TASKBOARD_DATA_DIR`): `taskboard.sqlite3` (plus `-wal`/`-shm` files while
  running), `uploads/` (post images) and, by default, `backups/`. Only the service account needs
  access to it: it holds password and session hashes.
- **Settings** come from environment variables, or from a `.env` file in the app folder (see
  [`.env.example`](../.env.example)). Environment variables win.
- **Migrations run at start** (`TASKBOARD_AUTO_MIGRATE=true`), and so does seeding of the
  built-in roles and accounts. On first start without `TASKBOARD_INITIAL_ADMIN_PASSWORD`, a
  generated `admin` password is printed once in the log; it must be changed at first login.

Settings that matter in production:

| Setting | Why |
|---|---|
| `TASKBOARD_ENVIRONMENT=production` | Serves the page from memory (development re-reads it per request). |
| `TASKBOARD_DATA_DIR` | Outside the app folder, e.g. `/var/lib/taskboard` or `C:\ProgramData\TaskBoard`. |
| `TASKBOARD_INITIAL_ADMIN_PASSWORD` | Optional: choose the first `admin` password instead of reading it from the log. |
| `TASKBOARD_BASE_PATH` | When published under a prefix, e.g. `/taskboard/` (the proxy strips it). |
| `TASKBOARD_TRUSTED_PROXIES` | If the proxy runs on another machine: its address. |
| `TASKBOARD_PUBLIC_URL` | For SSO redirect URIs (see AUTH.md). |

Do not start Uvicorn with its own `--proxy-headers` (its default when you run `uvicorn app:app`):
the app handles forwarded headers itself (D-061). `python -m taskboard serve` gets this right;
with `uvicorn app:app`, add `--no-proxy-headers`.

## Linux demo server

Built-in accounts only: leave every `TASKBOARD_OIDC_*` and `TASKBOARD_TRUSTED_HEADER` unset.

### Install

```sh
sudo useradd --system --home /var/lib/taskboard --shell /usr/sbin/nologin taskboard
sudo mkdir -p /opt/taskboard /var/lib/taskboard /etc/taskboard
sudo chown taskboard:taskboard /var/lib/taskboard && sudo chmod 700 /var/lib/taskboard
# Put the code in /opt/taskboard (git clone or copy), then, with uv installed:
cd /opt/taskboard
sudo env UV_PYTHON_INSTALL_DIR=/opt/taskboard/.python uv sync --frozen --no-dev
```

`UV_PYTHON_INSTALL_DIR` keeps the Python that uv downloads inside the app folder; by default it
would land in root's home, where the service account cannot run it.

`/etc/taskboard/taskboard.env` (readable by root and the service only, `chmod 640`, group
`taskboard`):

```ini
TASKBOARD_ENVIRONMENT=production
TASKBOARD_DATA_DIR=/var/lib/taskboard
TASKBOARD_INITIAL_ADMIN_PASSWORD=<a long password>
```

Demo content (optional): the design's sample board, with the sample people able to log in:

```sh
sudo -u taskboard sh -c 'set -a; . /etc/taskboard/taskboard.env; exec /opt/taskboard/.venv/bin/python -m taskboard seed --sample --demo-password "<demo password>"'
```

### systemd

`/etc/systemd/system/taskboard.service`:

```ini
[Unit]
Description=TaskBoard
After=network.target

[Service]
User=taskboard
Group=taskboard
WorkingDirectory=/opt/taskboard
EnvironmentFile=/etc/taskboard/taskboard.env
ExecStart=/opt/taskboard/.venv/bin/python -m taskboard serve
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/taskboard

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload && sudo systemctl enable --now taskboard
journalctl -u taskboard -f        # the log, including a generated admin password
```

### Reverse proxy with TLS

Caddy (gets and renews the certificate itself; sends `X-Forwarded-For` and `-Proto` by default):

```
tasks.example.org {
    reverse_proxy 127.0.0.1:8000
    request_body {
        max_size 12MB
    }
    header Strict-Transport-Security "max-age=31536000"
}
```

Or nginx:

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name tasks.example.org;
    ssl_certificate     /etc/letsencrypt/live/tasks.example.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tasks.example.org/privkey.pem;
    client_max_body_size 12m;      # post images are up to 10 MB
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Before opening it to the internet

- Log in as `admin` and change the password (or set it through the env file, above).
- Everyone can read the board without logging in (the anonymous visitor is *Viewer*). For a
  public demo that is usually the point; *Administration › Accounts › anonymous* changes it.
- Demo passwords are shared secrets: use them on the demo only.
- Failed logins are throttled per account and per address (AUTH.md); the addresses are real ones
  because the proxy is trusted.

## Windows server

### Install

1. Install [uv](https://docs.astral.sh/uv/) for all users, and put the code in e.g.
   `C:\TaskBoard\app`.
2. In PowerShell: `cd C:\TaskBoard\app`, `$env:UV_PYTHON_INSTALL_DIR = "C:\TaskBoard\python"`,
   then `uv sync --frozen --no-dev` (add `--extra mssql` for MS SQL). The install directory keeps
   the Python that uv downloads out of your own profile, where the service could not run it.
3. Create `C:\ProgramData\TaskBoard` and give the service account (below) *Modify* rights on it
   and *Read & execute* on `C:\TaskBoard`.
4. `C:\TaskBoard\app\.env`:

   ```ini
   TASKBOARD_ENVIRONMENT=production
   TASKBOARD_DATA_DIR=C:\ProgramData\TaskBoard
   TASKBOARD_INITIAL_ADMIN_PASSWORD=<a long password>
   TASKBOARD_PUBLIC_URL=https://tasks.corp.example/
   ```

### Windows service (WinSW)

[WinSW](https://github.com/winsw/winsw) is a small, MIT-licensed service wrapper. Copy
`WinSW-x64.exe` to `C:\TaskBoard\TaskBoard.exe` and put `C:\TaskBoard\TaskBoard.xml` next to it:

```xml
<service>
  <id>TaskBoard</id>
  <name>TaskBoard</name>
  <description>Team task board (python -m taskboard serve)</description>
  <executable>C:\TaskBoard\app\.venv\Scripts\python.exe</executable>
  <arguments>-m taskboard serve</arguments>
  <workingdirectory>C:\TaskBoard\app</workingdirectory>
  <onfailure action="restart" delay="10 sec" />
  <log mode="roll-by-size" />
</service>
```

```bat
C:\TaskBoard\TaskBoard.exe install
C:\TaskBoard\TaskBoard.exe start
```

Run the service under a dedicated account with only the rights listed above (*Services ›
TaskBoard › Log On*). WinSW writes the service's output to log files next to `TaskBoard.exe`;
a generated `admin` password would appear there (Uvicorn logs to the error stream).

### IIS as reverse proxy

Install the IIS modules *URL Rewrite* and *Application Request Routing* (ARR). In IIS Manager:
server node › *Application Request Routing Cache* › *Server Proxy Settings* › *Enable proxy*. Keep
"Preserve client IP in the following header: X-Forwarded-For" on. In *URL Rewrite › View Server
Variables*, allow `HTTP_X_FORWARDED_PROTO` (and `HTTP_X_REMOTE_USER` for Windows sign-in).

The site (HTTPS binding with the corporate certificate) gets this `web.config`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="TaskBoard" stopProcessing="true">
          <match url="(.*)" />
          <serverVariables>
            <set name="HTTP_X_FORWARDED_PROTO" value="https" />
          </serverVariables>
          <action type="Rewrite" url="http://127.0.0.1:8000/{R:1}" />
        </rule>
      </rules>
    </rewrite>
    <security>
      <requestFiltering>
        <requestLimits maxAllowedContentLength="12582912" />
      </requestFiltering>
    </security>
    <httpProtocol>
      <customHeaders>
        <add name="Strict-Transport-Security" value="max-age=31536000" />
      </customHeaders>
    </httpProtocol>
  </system.webServer>
</configuration>
```

Under a prefix (`https://intranet.corp.example/taskboard/`): match `^taskboard/(.*)`, keep the
action, and set `TASKBOARD_BASE_PATH=/taskboard/` and
`TASKBOARD_PUBLIC_URL=https://intranet.corp.example/taskboard/`.

Windows sign-in (IIS Windows authentication passing the user to TaskBoard) and Microsoft Entra
ID: see [`AUTH.md`](AUTH.md).

### MS SQL (later)

1. Install *Microsoft ODBC Driver 18 for SQL Server* and run `uv sync --frozen --no-dev --extra mssql`.
2. The DBA creates an empty database and a login that may create tables in it
   (`db_ddladmin`, `db_datareader`, `db_datawriter`): the schema is created by the migrations at
   the first start. Any case-insensitive default collation works.
3. `TASKBOARD_DATABASE_URL`, for example (URL-encode special characters in the password):

   ```ini
   # SQL login
   TASKBOARD_DATABASE_URL=mssql+pyodbc://taskboard:<password>@sqlserver.corp.example/TaskBoard?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes
   # or the service account's Windows login
   TASKBOARD_DATABASE_URL=mssql+pyodbc://@sqlserver.corp.example/TaskBoard?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&Trusted_Connection=yes
   ```

**Prove it first on a scratch database.** The test suite runs against any database named in
`TASKBOARD_TEST_DATABASE_URL`. It **empties that database before every test**, so never point it
at a database with real data:

```powershell
$env:TASKBOARD_TEST_DATABASE_URL = "mssql+pyodbc://...@sqlserver/TaskBoardTest?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes"
uv run --extra mssql pytest tests/api tests/integration
```

There is no tool yet to move an existing SQLite board to MS SQL; start MS SQL with a fresh board
or ask for one.

## Backups

`python -m taskboard backup` writes one zip file with a consistent snapshot of the SQLite
database (taken while the app keeps running) and every uploaded image, to
`<data dir>/backups/` or `--output <folder or .zip>`. Copy backups off the machine.

With MS SQL, the database is backed up by the DBA's own tooling (`BACKUP DATABASE`); the
command then archives the uploads only, which still need backing up.

Daily on Linux, `/etc/systemd/system/taskboard-backup.service` plus a `.timer`:

```ini
# taskboard-backup.service
[Service]
Type=oneshot
User=taskboard
WorkingDirectory=/opt/taskboard
EnvironmentFile=/etc/taskboard/taskboard.env
ExecStart=/opt/taskboard/.venv/bin/python -m taskboard backup
ExecStartPost=/usr/bin/find /var/lib/taskboard/backups -name 'taskboard-backup-*.zip' -mtime +30 -delete

# taskboard-backup.timer
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
```

Daily on Windows (Task Scheduler, as the service account):

```bat
schtasks /Create /TN "TaskBoard backup" /SC DAILY /ST 02:00 /RU CORP\svc-taskboard /RP * ^
  /TR "C:\TaskBoard\app\.venv\Scripts\python.exe -m taskboard backup --output D:\Backups\TaskBoard"
```

### Restore

Stop the service first. Then, as the service account:

```sh
python -m taskboard restore <backup.zip> --replace
```

Nothing is deleted: the database and uploads it replaces are kept next to the originals as
`*.before-restore-<time>`. A backup made by an older TaskBoard is upgraded as it is restored; one
made by a newer version is refused. Start the service again afterwards.

## Upgrading

1. Take a backup (above).
2. Stop the service, replace the code, run `uv sync --frozen --no-dev` (plus `--extra mssql` if
   used).
3. Start the service: migrations run automatically.

With more than one process on the same database (not the default), set
`TASKBOARD_AUTO_MIGRATE=false` and run `python -m taskboard db upgrade` once during step 2, so
two processes never migrate at the same time.

## Security checklist

- TLS and HSTS at the proxy; the app only on `127.0.0.1`.
- `TASKBOARD_TRUSTED_PROXIES` lists the proxy and nothing else.
- The `admin` password is changed (it is the break-glass account).
- The data folder and the `.env` file are readable by the service account only.
- The proxy accepts uploads of at least 10 MB (post images); the app enforces the real limit.
- The app sends its own security headers (strict CSP, no framing, no sniffing; D-063); keep the
  proxy from overriding them.
- Backups run, and a restore has been tried once.
