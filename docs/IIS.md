# TaskBoard on IIS, step by step

A walkthrough for someone who has never used IIS, for trying TaskBoard on a Windows server that
already runs other things. [`OPERATIONS.md`](OPERATIONS.md) is the reference behind it (settings,
backups, MS SQL, security checklist); this guide adds the IIS basics, the choices, and what tends
to go wrong.

> Not yet tried on a real IIS. The Python side is tested; the IIS steps follow Microsoft's
> documentation. If something differs, note what you changed.

Assumed: Windows Server with IIS, `git` and `uv` installed, and an **administrator** Windows
PowerShell (right-click › *Run as administrator*). Use local paths only (`C:\...`): drive letters
mapped to network shares do not exist for the accounts that run web apps, and SQLite must not
live on a network share.

## 1. Six IIS words

- **IIS Manager** (`inetmgr` in the Start menu): the admin GUI. The left tree shows the server,
  its *Application Pools* and its *Sites*.
- **Site**: one website. It has a **physical path** (a folder) and **bindings**: protocol, port
  and optionally a host name (`http` on port 8080, `https` on 443 for `tasks.corp.local`, ...).
  Two sites cannot share the same binding.
- **Application**: a sub-path of a site with its own folder, e.g. `/shiny` inside the default
  site.
- **Application pool**: the worker process (`w3wp.exe`) that serves a site or application. It
  runs as its own Windows identity, `IIS AppPool\<pool name>`, which needs file permissions like
  any user.
- **web.config**: an XML settings file in a site's or application's folder. It applies to that
  folder **and everything below it**, including applications inside it. Server-wide settings live
  in `C:\Windows\System32\inetsrv\config\applicationHost.config` (edit through IIS Manager, not by
  hand).
- **Modules**: add-ons that give IIS new abilities. Three matter here: *HttpPlatformHandler*
  (starts a program and passes it the requests), *URL Rewrite* and *Application Request Routing*
  (ARR; together they forward requests to another web server).

IIS cannot run Python itself. It either **starts TaskBoard and passes requests to it** (route A,
HttpPlatformHandler) or **forwards requests to TaskBoard running as a Windows service** (route B,
URL Rewrite + ARR):

```
route A:  browser ──> IIS site "TaskBoard" ──> python -m taskboard serve   (IIS starts and stops it)
route B:  browser ──> IIS site "TaskBoard" ──> python -m taskboard serve   (a Windows service, 127.0.0.1:8000)
```

If you see *wfastcgi* on the server: that older approach only runs WSGI apps; TaskBoard (FastAPI)
cannot use it.

## 2. Look around first (changes nothing)

It is a shared work server: find out what is there before touching it.

```powershell
Import-Module WebAdministration
$appcmd = "$env:windir\system32\inetsrv\appcmd.exe"
& $appcmd list site           # sites, their bindings (ports) and state
& $appcmd list vdir           # every site/application and the folder it serves from
& $appcmd list apppool        # application pools
Get-WebGlobalModule | Where-Object Name -Match 'httpPlatform|Rewrite|ApplicationRequestRouting|AspNetCore'
Get-NetTCPConnection -State Listen | Sort-Object LocalPort -Unique | Format-Table LocalAddress, LocalPort, OwningProcess
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Format-List ProcessId, ParentProcessId, CommandLine
```

**How does the Shiny app run?** Find its folder in the `list vdir` output and open the
`web.config` there:

| You see | Meaning |
|---|---|
| `<httpPlatform processPath="...python.exe" ...>` | IIS starts Shiny itself (route A). HttpPlatformHandler is installed: route A is ready to use. |
| `<rewrite>` with `<action type="Rewrite" url="http://localhost:8xxx/..." />` | IIS forwards to a Shiny process that runs on its own (route B). URL Rewrite and ARR are installed. The Python process list shows its command line; its parent is a service or a scheduled task. |
| `<aspNetCore processPath=...>` | The ASP.NET Core Module doing route A's job. Ask for a TaskBoard variant. |

**The mystery `web.config` in `C:\iis_something`** only has an effect if a site or application
serves from that folder (the `list vdir` output says). If one does, its rules apply to everything
inside that site, including anything you would add under it. The plan below keeps TaskBoard in
its **own site**, so that file stays out of the way. Don't edit it.

**Before changing anything:**

- Take a snapshot of the server-wide IIS configuration: `& $appcmd add backup before-taskboard`.
  `& $appcmd restore backup before-taskboard` puts it back (and undoes everyone's server-level
  changes since, so only in an emergency). It does not cover `web.config` files in site folders.
- Never run `iisreset`: it restarts every site, Shiny included. Restart only your own pool or
  site.
- Installing modules or changing server-level settings (the server node in IIS Manager) affects
  everyone. Check with whoever owns the server.

## 3. Choose a route

| | Route A: IIS starts TaskBoard | Route B: service + forwarding |
|---|---|---|
| Needs | HttpPlatformHandler | URL Rewrite + ARR, and a service wrapper ([WinSW](https://github.com/winsw/winsw)) |
| Moving parts | one `web.config` | a Windows service, a `web.config`, server-level ARR settings |
| Address | its own site: `http://server:8080/` | its own site, or under a prefix: `https://server/taskboard/` |
| Restart | recycle the app pool | restart the service |

**Pick route A** unless you need the prefix: HttpPlatformHandler passes the full path
(`/taskboard/api/...`) to TaskBoard, and TaskBoard expects the prefix to be removed first (which
route B's rewrite rule does). If neither is installed, route A needs one installer:
[HttpPlatformHandler v1.2](https://www.iis.net/downloads/microsoft/httpplatformhandler) (x64).

A port for the new site: pick one that the listening-ports list and `list site` don't show, e.g.
8080. A host name instead (`tasks.corp.local` on port 80/443) needs a DNS record from IT, and a
matching certificate for HTTPS.

## 4. Install TaskBoard (both routes)

The layout used below:

```
C:\TaskBoard\app\           the code (git checkout), .venv and .env
C:\TaskBoard\python\        the Python that uv downloads
C:\TaskBoard\site\          the IIS site's folder: only web.config
C:\TaskBoard\logs\          TaskBoard's output (route A)
C:\ProgramData\TaskBoard\   the data: database, uploaded images, backups
```

```powershell
New-Item -ItemType Directory -Force C:\TaskBoard\site, C:\TaskBoard\logs, C:\ProgramData\TaskBoard
git clone https://github.com/TheDerivator/TaskBoard.git C:\TaskBoard\app
cd C:\TaskBoard\app
$env:UV_PYTHON_INSTALL_DIR = "C:\TaskBoard\python"
$env:UV_LINK_MODE = "copy"
uv sync --frozen --no-dev
```

Why the two variables (set them again before every later `uv sync`):

- `UV_PYTHON_INSTALL_DIR`: uv otherwise downloads Python into *your* profile
  (`C:\Users\you\AppData\...`), which the account that runs TaskBoard cannot read.
- `UV_LINK_MODE=copy`: uv otherwise *hard-links* packages from its cache in your profile, and
  hard-linked files keep the cache's permissions, so TaskBoard would fail to import them.

If `uv sync` cannot download (corporate proxy): `$env:HTTPS_PROXY = "http://proxy.corp:8080"` with
the proxy your browser uses. A private repository asks for GitHub credentials; copying the folder
works too.

**Settings.** Create `C:\TaskBoard\app\.env` in Notepad (no quotes around values):

```ini
TASKBOARD_ENVIRONMENT=production
TASKBOARD_DATA_DIR=C:\ProgramData\TaskBoard
```

Only with HTTPS: add `TASKBOARD_COOKIE_SECURE=true` (on plain HTTP it makes logging in fail
silently: the browser drops the cookie).

**Database and admin account:**

```powershell
.venv\Scripts\python.exe -m taskboard seed
```

It ends with `Admin password (change it at first login): ...`. This is the only time it is
shown: store it in your password manager. To start from the design's sample board, whose sample
people can log in with a shared demo password (single quotes, so PowerShell leaves `$` alone):

```powershell
.venv\Scripts\python.exe -m taskboard seed --sample --demo-password '<a demo password>'
```

By default anyone who reaches the site can *read* the board without logging in. To make it
login-only: log in as `admin`, *Administration › Accounts › Anonymous visitors*, remove
*Viewer · Everywhere*.

**Try it without IIS** (this separates Python problems from IIS problems):

```powershell
.venv\Scripts\python.exe -m taskboard serve
```

Open `http://127.0.0.1:8000` in a browser **on the server** and log in; stop with Ctrl+C.

## 5A. Route A: IIS starts TaskBoard

**Application pool** (IIS Manager › *Application Pools*):

```powershell
New-WebAppPool -Name TaskBoard
Set-ItemProperty IIS:\AppPools\TaskBoard -Name managedRuntimeVersion -Value ""           # "No Managed Code"
Set-ItemProperty IIS:\AppPools\TaskBoard -Name processModel.idleTimeout -Value "00:00:00" # never idle out
```

Without the second setting, IIS stops the pool (and TaskBoard) after 20 idle minutes, and the next
visitor waits for a cold start. Keep *Maximum Worker Processes* at 1.

**Permissions** for the pool's identity: read the code and Python, write logs and data. The data
folder is closed to everyone else (it holds password and session hashes). The `*S-1-5-...` names
are SYSTEM and Administrators, written so they work on any Windows language.

```powershell
icacls C:\TaskBoard /grant "IIS AppPool\TaskBoard:(OI)(CI)RX"
icacls C:\TaskBoard\logs /grant "IIS AppPool\TaskBoard:(OI)(CI)M"
icacls C:\ProgramData\TaskBoard /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "IIS AppPool\TaskBoard:(OI)(CI)M"
```

**`C:\TaskBoard\site\web.config`:**

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <handlers>
      <add name="TaskBoard" path="*" verb="*" modules="httpPlatformHandler" resourceType="Unspecified" />
    </handlers>
    <httpPlatform processPath="C:\TaskBoard\app\.venv\Scripts\python.exe"
                  arguments="-m taskboard serve --port %HTTP_PLATFORM_PORT%"
                  startupTimeLimit="60"
                  stdoutLogEnabled="true"
                  stdoutLogFile="C:\TaskBoard\logs\python">
      <environmentVariables>
        <environmentVariable name="PYTHONUNBUFFERED" value="1" />
      </environmentVariables>
    </httpPlatform>
  </system.webServer>
</configuration>
```

IIS picks a free local port, starts TaskBoard on it at the first request, passes every request
on, and restarts it if it crashes. Its output lands in `C:\TaskBoard\logs\python*`.

**Site and firewall:**

```powershell
New-Website -Name TaskBoard -Port 8080 -PhysicalPath C:\TaskBoard\site -ApplicationPool TaskBoard
New-NetFirewallRule -DisplayName "TaskBoard (8080)" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
```

**Test**, first on the server (IIS shows detailed error pages only there), then from your PC:

- `http://localhost:8080/api/health` answers `{"status":"ok",...}`. The first request takes a
  few seconds while Python starts.
- `http://localhost:8080/`, then `http://<server name>:8080/` from your PC. If only the server
  works, a network firewall between you blocks the port: ask IT, or use a port that is open.

**Day to day:**

- Restart TaskBoard: `Restart-WebAppPool TaskBoard` (also after changing `.env`; saving
  `web.config` restarts it by itself).
- Upgrade: `Stop-WebAppPool TaskBoard`, then in `C:\TaskBoard\app`: `git pull`, set the two
  `UV_*` variables, `uv sync --frozen --no-dev`, then `Start-WebAppPool TaskBoard`. Migrations
  run at start.
- IIS restarts the pool on its own about once a day (*Recycling*); TaskBoard doesn't mind.

## 5B. Route B: TaskBoard as a service, IIS forwards

1. **The service**: follow [*Windows service (WinSW)*](OPERATIONS.md#windows-service-winsw).
   Check first that nothing else listens on port 8000 (Shiny's default is also 8000). If
   something does, add `TASKBOARD_PORT=8002` to `.env` and use that port below. Add
   `<logpath>C:\TaskBoard\logs</logpath>` to `TaskBoard.xml`, so the logs go where the service
   may write. For the account, Windows has a built-in one per service:
   `sc.exe config TaskBoard obj= "NT SERVICE\TaskBoard"` (in PowerShell type `sc.exe`, since `sc`
   means something else there). Then give it the three permission lines from 5A with
   `NT SERVICE\TaskBoard` in place of `IIS AppPool\TaskBoard`, and `Restart-Service TaskBoard`.
2. **Enable forwarding in ARR (server-wide, once)**: IIS Manager › the server node ›
   *Application Request Routing Cache* › *Server Proxy Settings* (right-hand side) › tick
   *Enable proxy* › *Apply*. If Shiny is already forwarded like this, it is on.
3. **Allow the header** the rule sets: the server node › *URL Rewrite* › *View Server Variables*
   › *Add* › `HTTP_X_FORWARDED_PROTO`.
4. **`C:\TaskBoard\site\web.config`**: this tells TaskBoard whether the visitor used http or
   https, so login works on both:

   ```xml
   <?xml version="1.0" encoding="utf-8"?>
   <configuration>
     <system.webServer>
       <rewrite>
         <rules>
           <clear />  <!-- ignore rules inherited from a parent site -->
           <rule name="TaskBoard" stopProcessing="true">
             <match url="(.*)" />
             <conditions>
               <add input="{CACHE_URL}" pattern="^(https?)://" />
             </conditions>
             <serverVariables>
               <set name="HTTP_X_FORWARDED_PROTO" value="{C:1}" />
             </serverVariables>
             <action type="Rewrite" url="http://127.0.0.1:8000/{R:1}" />
           </rule>
         </rules>
       </rewrite>
     </system.webServer>
   </configuration>
   ```

5. **Site, firewall, test**: as in 5A, but create the site with the default pool:
   `New-Website -Name TaskBoard -Port 8080 -PhysicalPath C:\TaskBoard\site`.

**Under a prefix instead of its own site** (`https://server/taskboard/`): in IIS Manager,
right-click the existing site › *Add Application*, alias `taskboard`, physical path
`C:\TaskBoard\site`. Rules in an application's `web.config` see the path *without* the prefix,
so the same file forwards `/taskboard/api/...` as `/api/...`, and its `<clear />` keeps the
parent site's rules out. Add `TASKBOARD_BASE_PATH=/taskboard/` to `.env` and restart the
service.

Day to day: `Restart-Service TaskBoard`. Upgrade as in 5A with `Stop-Service` / `Start-Service`.

## 6. HTTP or HTTPS

**Plain HTTP**, common on intranets, is what sections 4 and 5 set up, and it works as it is: keep
`TASKBOARD_COOKIE_SECURE` out of `.env`. Worth knowing:

- Passwords and session cookies cross the network unencrypted: anyone who can watch the traffic
  between a browser and the server could read them. Fine for an experiment, but don't use a
  password that you use anywhere else (certainly not your Windows password).
- Browsers show "Not secure" next to the address, and the browser console (F12) warns that the
  `Cross-Origin-Opener-Policy` header was ignored. Both are harmless.
- If the browser switches to `https://` by itself, or warns before opening the page, a browser or
  company policy prefers HTTPS: type `http://` explicitly, or try the short server name without
  the domain. If the policy is enforced, you need HTTPS (below).
- Sign-in with Microsoft Entra ID ([`AUTH.md`](AUTH.md)), should you want it later, requires
  HTTPS; Windows sign-in through IIS does not.

**HTTPS.** The certificate the other site already uses usually works for the same server name on another
port. IIS Manager › *Sites* › TaskBoard › *Bindings...* › *Add*: type `https`, port e.g. 8443,
pick the *SSL certificate*. Open the port in the firewall as above, add
`TASKBOARD_COOKIE_SECURE=true` to `.env`, restart TaskBoard, and use only the https address from
then on. Once it is more than an experiment, add the HSTS header from
[`OPERATIONS.md`](OPERATIONS.md#iis-as-reverse-proxy).

## 7. When it doesn't work

Look in this order:

1. The error page, **opened on the server itself** (remote visitors get a generic one). IIS
   errors have a number like `502.3`; the part after the dot is what counts.
2. TaskBoard's output in `C:\TaskBoard\logs\`. Empty or missing: run the command from section 4
   by hand, it shows the same error.
3. *Event Viewer* › *Windows Logs* › *Application*: HttpPlatformHandler reports start failures
   there.
4. IIS's request log: `C:\inetpub\logs\LogFiles\W3SVC<site id>\` (the id is in `list site`),
   one line per request with its status.

| Symptom | Usual cause |
|---|---|
| **502.3** Bad Gateway | TaskBoard did not start or is not answering. Route A: read the log folder; if it is empty, the pool cannot read `python.exe` or Python (section 4's variables, the permissions). Route B: the service is stopped, or the port in the rule is wrong. |
| **500.19** configuration error | A typo in `web.config`, or it uses a module that is not installed (`<httpPlatform>`, `<rewrite>`). The page shows the offending line. |
| **500.50** URL Rewrite error | `HTTP_X_FORWARDED_PROTO` is not in the allowed server variables (5B step 3). |
| A **404** in IIS's style (route B) | ARR's *Enable proxy* is off (5B step 2). |
| **503** Service Unavailable | The application pool is stopped: start it, then check the log for why. |
| The browser asks for a **Windows** user name | Windows Authentication is on for the site. Site › *Authentication*: *Anonymous* enabled, *Windows* disabled (TaskBoard has its own login). |
| Log in "works" but you stay logged out, or `csrf_failed` | A Secure cookie over plain http: remove `TASKBOARD_COOKIE_SECURE=true`, or use https. |
| `unable to open database file`, `readonly database` | The data folder's permissions. |
| Page loads without styling (prefix setup) | `TASKBOARD_BASE_PATH` doesn't match the prefix. |
| Works on the server, not from your PC | A firewall (Windows or network), or the binding is limited to a host name you didn't type. |

Two known limits of route A: TaskBoard may see every visitor as `127.0.0.1` (HttpPlatformHandler
does not promise to pass the client's address), so its limit of 50 failed logins per address in
15 minutes then counts everyone together. Fine for an experiment. It also cannot run under a
prefix (section 3).

## 8. Backups, and removing the experiment

Backups and restores: [`OPERATIONS.md`](OPERATIONS.md#backups). For a scheduled task with route
A, run it as `SYSTEM` (`/RU SYSTEM`, no password), which may read the data folder.

To remove everything again:

```powershell
Remove-Website TaskBoard
Remove-WebAppPool TaskBoard          # route A
Remove-NetFirewallRule -DisplayName "TaskBoard (8080)"
# route B: Stop-Service TaskBoard; C:\TaskBoard\TaskBoard.exe uninstall
Remove-Item -Recurse C:\TaskBoard, C:\ProgramData\TaskBoard   # the data too: back it up first
```
