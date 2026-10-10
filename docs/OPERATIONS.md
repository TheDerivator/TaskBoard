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
- **The exception: Windows sign-in.** There, browsers reach TaskBoard directly
  (`TASKBOARD_HOST=0.0.0.0`, no proxy) and it can serve HTTPS itself: see
  [*Windows sign-in, without IIS*](#windows-sign-in-without-iis).
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
| `TASKBOARD_BACKUP_DIR` | Where backups go, e.g. a network share as `\\fileserver\backups\TaskBoard` ([Backups](#backups)). |
| `TASKBOARD_INITIAL_ADMIN_PASSWORD` | Optional: choose the first `admin` password instead of reading it from the log. |
| `TASKBOARD_BASE_PATH` | When published under a prefix, e.g. `/taskboard/` (the proxy strips it). |
| `TASKBOARD_TRUSTED_PROXIES` | If the proxy runs on another machine: its address. |
| `TASKBOARD_PUBLIC_URL` | For SSO redirect URIs (see AUTH.md). |
| `TASKBOARD_TLS_CERTFILE`, `TASKBOARD_TLS_KEYFILE` | Only without a proxy: HTTPS by the app itself (PEM files). |

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

Demo content (optional): the design's sample board, with the sample people able to log in. It
holds the tasks and projects, the process changes of Ladle metallurgy and Continuous casting,
the Continuous casting knowledge map with its defects, and the FMEA and control plan releases
v1-v3 with four draft changes after v3. Its dates move so that the sample's "today" (3 Oct 2026)
is the day you seed; seeding only fills an empty board:

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

New to IIS? [`IIS.md`](IIS.md) walks through all of this step by step, including a simpler
variant in which IIS starts TaskBoard itself (no Windows service), and what tends to go wrong.
Want people signed in with their Windows account? That works without IIS:
[`WINDOWS-SIGNIN.md`](WINDOWS-SIGNIN.md), also step by step.

### Install

1. Install [uv](https://docs.astral.sh/uv/) for all users, and put the code in e.g.
   `C:\TaskBoard\app`.
2. In PowerShell: `cd C:\TaskBoard\app`, `$env:UV_PYTHON_INSTALL_DIR = "C:\TaskBoard\python"`,
   `$env:UV_LINK_MODE = "copy"`, then `uv sync --frozen --no-dev` (add `--extra mssql` for MS
   SQL). The install directory keeps the Python that uv downloads out of your own profile, where
   the service could not run it. Copying (instead of uv's default hard links into its cache in
   your profile) gives the packages the app folder's permissions. Set both again before every
   later `uv sync`.
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
Variables*, allow `HTTP_X_FORWARDED_PROTO`.

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

Microsoft Entra ID sign-in: see [`AUTH.md`](AUTH.md).

### Windows sign-in, without IIS

People are signed in as their Windows account (Kerberos or NTLM) by TaskBoard itself. IIS cannot
pass the Windows user on to TaskBoard with its own modules (URL Rewrite runs before IIS
authenticates: [`AUTH.md`](AUTH.md#configuring-a-trusted-header-an-authenticating-proxy)), so in
this setup no proxy is in front. Walkthrough: [`WINDOWS-SIGNIN.md`](WINDOWS-SIGNIN.md).

```
browser ──HTTP or HTTPS──> TaskBoard (the Windows service above) on 0.0.0.0:<port>
                           Negotiate handshake on /api/auth/windows, checked by Windows (SSPI)
```

```ini
TASKBOARD_HOST=0.0.0.0
TASKBOARD_PORT=8080
TASKBOARD_WINDOWS_AUTH=true
# HTTPS (PEM files; the certificate first, then its intermediates; the key without a password):
TASKBOARD_TLS_CERTFILE=C:\TaskBoard\tls\cert.pem
TASKBOARD_TLS_KEYFILE=C:\TaskBoard\tls\key.pem
```

- Run the service as its own account (`sc.exe config TaskBoard obj= "NT SERVICE\TaskBoard"`):
  it acts as the computer on the network, which Kerberos needs, and no SPN has to be registered.
- TaskBoard needs a port of its own (no URL prefix, no sharing of 80/443 with IIS sites), opened
  in the firewall.
- No proxy means no HSTS header and no upload size limit in front; the app enforces its own
  limits.
- Accounts, browsers' intranet zone and troubleshooting: the walkthrough.

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

`python -m taskboard backup` writes one zip file: a consistent snapshot of the SQLite database
(taken while the app keeps running, and checked with SQLite's integrity check) and every
uploaded image. It writes into the **backup folder**, `TASKBOARD_BACKUP_DIR` (default
`<data dir>/backups/`), and then deletes the backups there that are no longer kept. Other files in
that folder are never touched. With `--output <folder or .zip>` it writes an extra backup
elsewhere, before an upgrade for example, and deletes nothing. A failed backup deletes nothing
either, and leaves no half-written file.

**Which backups are kept** is set under *Administration › Backups* (user administrators; D-100):

| Kept | Default | Allowed |
|---|---|---|
| The newest backups | 2 | 2 to 30 |
| The first backup of each of the last weeks that have one (Monday to Sunday) | 1 | 1 to 26 |
| The first backup of each of the last months that have one | 2 | 1 to 24 |

"First" is the earliest backup of that week or month, so a night missed on the 1st still leaves
one. With one backup a night, the defaults keep five at most: the last two nights, Monday's, and
the 1st of this month and of the month before. Every zip holds all the images, so the folder takes
up to five times the size of `uploads/`. A change to these numbers applies at the next backup.

The same page shows the backup folder and every backup in it, with its size and why it is kept,
and warns when the newest backup is more than two days old or the folder cannot be read. The
folder itself is deliberately a server setting, shown but not editable there: the backup runs as
`SYSTEM` and holds the whole database, so where it goes is decided by whoever runs the server
(D-101). The app never makes, restores or hands out backups itself.

**Copy backups off the machine**: put the backup folder on a network share, or on a disk that the
server's own backup covers.

With MS SQL, the database is backed up by the DBA's own tooling (`BACKUP DATABASE`); the
command then archives the uploads only, which still need backing up.

### Daily on Windows (Task Scheduler)

Run the task as `SYSTEM`: no password to store, and it may read `C:\ProgramData\TaskBoard` (unless
inheritance was switched off on that folder). The `.env` in the app folder applies, wherever the
task starts (D-069). In an administrator's command prompt:

```bat
schtasks /Create /TN "TaskBoard backup" /SC DAILY /ST 02:00 /RU SYSTEM ^
  /TR "C:\TaskBoard\app\.venv\Scripts\python.exe -m taskboard backup"
schtasks /Run /TN "TaskBoard backup"
```

The second line makes a first backup now; *Administration › Backups* then lists it. Don't add
`--output` to the task: backups written elsewhere are never cleaned up. In Task Scheduler, the
task's *Last Run Result* is `0x0` when all went well and `0x1` when the backup failed or an old one
could not be deleted.

**On a network share**, in the `.env` file:

```ini
TASKBOARD_BACKUP_DIR=\\fileserver\backups\TaskBoard
```

- Use the UNC path. Drive letters such as `Z:` exist only in a signed-in user's session, not for
  scheduled tasks and services.
- `SYSTEM`, and the service running as `NT SERVICE\TaskBoard`, reach the network as the server's
  computer account, `CORP\<server name>$`. Give that account *Modify* on the folder (share and
  folder permissions); the task writes and deletes there, the Backups page only reads. A service
  that runs as a domain account reads the folder as that account.
- Restart the service after changing `.env`, so the Backups page shows the new folder.

### Daily on Linux (systemd timer)

`/etc/systemd/system/taskboard-backup.service` plus a `.timer`:

```ini
# taskboard-backup.service
[Service]
Type=oneshot
User=taskboard
WorkingDirectory=/opt/taskboard
EnvironmentFile=/etc/taskboard/taskboard.env
ExecStart=/opt/taskboard/.venv/bin/python -m taskboard backup

# taskboard-backup.timer
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
```

### Restore

Stop the service first. Then, as the service account:

```sh
python -m taskboard restore <backup.zip> --replace
```

Nothing is deleted: the database and uploads it replaces are kept next to the originals as
`*.before-restore-<time>`. A backup made by an older TaskBoard is upgraded as it is restored; one
made by a newer version is refused. Start the service again afterwards.

### Try a restore once

A restore into an empty folder leaves the running board alone, so it can be tried any time. On
Windows, in PowerShell on the server (the other settings still come from `.env`; if it sets
`TASKBOARD_DATABASE_URL`, this does not apply):

```powershell
$env:TASKBOARD_DATA_DIR = "C:\Temp\taskboard-restore-test"
$env:TASKBOARD_PORT = "8099"
C:\TaskBoard\app\.venv\Scripts\python.exe -m taskboard restore "<a backup .zip from the list>"
C:\TaskBoard\app\.venv\Scripts\python.exe -m taskboard serve
```

Open port 8099 on the server itself (`https://` if the app serves HTTPS), check a few tasks and
images, stop it with Ctrl+C, and delete `C:\Temp\taskboard-restore-test`.

## Upgrading

1. Take a backup (above).
2. Stop the service, replace the code, run `uv sync --frozen --no-dev` (plus `--extra mssql` if
   used).
3. Start the service: migrations run automatically.

With more than one process on the same database (not the default), set
`TASKBOARD_AUTO_MIGRATE=false` and run `python -m taskboard db upgrade` once during step 2, so
two processes never migrate at the same time.

## Security checklist

- TLS and HSTS at the proxy; the app only on `127.0.0.1`. (With Windows sign-in and no proxy:
  TLS by the app, and the private key readable by the service account only.)
- `TASKBOARD_TRUSTED_PROXIES` lists the proxy and nothing else.
- The `admin` password is changed (it is the break-glass account).
- The data folder and the `.env` file are readable by the service account only.
- The proxy accepts uploads of at least 10 MB (post images); the app enforces the real limit.
- The app sends its own security headers (strict CSP, no framing, no sniffing; D-063); keep the
  proxy from overriding them.
- Backups run (*Administration › Backups* shows no warning), are copied off the machine, and a
  restore has been tried once.
