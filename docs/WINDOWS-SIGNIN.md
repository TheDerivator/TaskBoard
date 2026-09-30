# TaskBoard with Windows sign-in, without IIS, step by step

A walkthrough for someone who has never set up Windows sign-in for a website. At the end, people
open the board and are signed in as their Windows account, without typing anything. TaskBoard
does this itself: browsers talk to it directly, and IIS takes no part. [`AUTH.md`](AUTH.md) and
[`OPERATIONS.md`](OPERATIONS.md) are the references behind this guide; [`IIS.md`](IIS.md) is its
sibling for running TaskBoard behind IIS (with TaskBoard's own login).

**Why not through IIS?** The obvious plan is to let IIS do the Windows authentication and pass
the user name on to TaskBoard in a header. On a real IIS that fails: the module that forwards
requests (URL Rewrite) runs *before* the one that authenticates, so the user name it should pass
on (`{LOGON_USER}`) is still empty. The way around it is a custom program inside IIS. Letting
TaskBoard ask the browser itself is simpler, and is what this guide sets up.

> Tried on a Windows 11 PC outside a domain: the sign-in itself over NTLM (with Chromium and
> with Windows' `curl`), the account steps of section 5, and HTTPS. **Not yet tried in a
> domain**: so not with Kerberos, and not with the service account of section 3 doing the
> checking. If something differs, note what you changed.

Assumed: a Windows server that is a member of your domain (as are the users' PCs), `git` and `uv`
installed, and an **administrator** Windows PowerShell (right-click › *Run as administrator*).
Use local paths only (`C:\...`), as in the IIS guide.

## 1. Six words

- **Windows service**: a program that Windows starts at boot and keeps running with nobody logged
  in. TaskBoard runs as one, wrapped by a small tool called WinSW. A service runs as an
  **account**, which needs file permissions like any user.
- **Uvicorn**: the web server inside TaskBoard; `python -m taskboard serve` starts it. In the IIS
  guide it hides behind IIS on `127.0.0.1`. Here it listens on the network itself.
- **Negotiate**: how a browser proves to a website who is logged in to Windows, without sending a
  password. The site answers "401, Negotiate", the browser answers with a *token*, and Windows
  on the server checks the token. It is what IIS calls *Windows Authentication*.
- **Kerberos** and **NTLM**: the two methods Negotiate chooses from. With Kerberos the browser
  fetches a *ticket* for the server from the domain controller: one request, and the better of
  the two. NTLM is the older fallback (the server sends a challenge, the browser answers: two
  requests), used when Kerberos is not possible: an IP address instead of a name, a PC outside
  the domain. Both end the same way for TaskBoard: `CORP\jdoe`.
- **SPN** (service principal name): the name under which the domain knows a service, such as
  `HTTP/server01.corp.local`. Kerberos tickets are issued for an SPN. Every domain computer has
  one for its own name from the start, which is all this guide needs.
- **Intranet zone**: browsers give the Windows login only to sites they consider internal. Any
  other site gets a user name and password prompt instead.

```
IIS guide:   browser ──> IIS site ──> TaskBoard (127.0.0.1)          TaskBoard's own login
this guide:  browser ──> TaskBoard (a Windows service, port 8080)
                           └─ "who is this?" ─> Windows checks the browser's token ─> CORP\jdoe
```

What a visitor notices: nothing. The page asks TaskBoard once to sign them in, the browser and
Windows settle it, and TaskBoard starts its usual session (a cookie, 14 days). So Windows is
asked once per session, not at every click, and everything else (roles, the `admin` account,
reading without logging in) works as before.

## 2. Look around first (changes nothing)

```powershell
Get-CimInstance Win32_ComputerSystem | Format-List Name, Domain, PartOfDomain   # in a domain?
[System.Net.Dns]::GetHostEntry('').HostName      # the server's full name, e.g. server01.corp.local
whoami                                           # your own login, e.g. corp\jdoe
Get-NetTCPConnection -State Listen | Sort-Object LocalPort -Unique | Format-Table LocalAddress, LocalPort, OwningProcess
Get-Service TaskBoard -ErrorAction SilentlyContinue                              # installed before?
```

Note the server's short name (`server01`) and full name: people will type one of them. Pick a
port that the listening-ports list does not show, e.g. 8080. If TaskBoard already runs behind IIS
(the IIS guide's route B), read section 8 first: most of the work is done.

`PartOfDomain : False` (a stand-alone server): Windows sign-in still works, with NTLM and the
server's *local* Windows accounts only.

## 3. Install TaskBoard as a Windows service

**Install**: follow [section 4 of the IIS guide](IIS.md#4-install-taskboard-both-routes) (the
folders, `uv sync`, `.env`, the `seed` command and its admin password, the try-out). Nothing in
it is about IIS. Already installed? After `git pull`, run `uv sync --frozen --no-dev` again
(with the two `UV_*` variables set): Windows sign-in needs two packages that older installs lack.

**The service.** Download `WinSW-x64.exe` from [WinSW's releases](https://github.com/winsw/winsw/releases),
save it as `C:\TaskBoard\TaskBoard.exe`, and create `C:\TaskBoard\TaskBoard.xml` next to it:

```xml
<service>
  <id>TaskBoard</id>
  <name>TaskBoard</name>
  <description>Team task board (python -m taskboard serve)</description>
  <executable>C:\TaskBoard\app\.venv\Scripts\python.exe</executable>
  <arguments>-m taskboard serve</arguments>
  <workingdirectory>C:\TaskBoard\app</workingdirectory>
  <logpath>C:\TaskBoard\logs</logpath>
  <onfailure action="restart" delay="10 sec" />
  <log mode="roll-by-size" />
</service>
```

```powershell
C:\TaskBoard\TaskBoard.exe install
sc.exe config TaskBoard obj= "NT SERVICE\TaskBoard"      # the account (type sc.exe, not sc)
icacls C:\TaskBoard /grant "NT SERVICE\TaskBoard:(OI)(CI)RX"
icacls C:\TaskBoard\logs /grant "NT SERVICE\TaskBoard:(OI)(CI)M"
icacls C:\ProgramData\TaskBoard /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "NT SERVICE\TaskBoard:(OI)(CI)M"
```

The three `icacls` lines let the service read the code and Python and write its logs and data;
the data folder is closed to everyone else (it holds password and session hashes).

**Why that account matters here.** `NT SERVICE\TaskBoard` is an account that Windows makes for
the service: no password to manage, and no rights beyond the three lines above. Towards the
network it acts as *the server itself*, and that is what makes Kerberos work with no further
setup: the domain already knows the server's name. If you run the service as a domain account
(`CORP\svc-taskboard`) instead, a domain administrator has to register the SPN for it
(`setspn -S HTTP/server01.corp.local CORP\svc-taskboard`), and on a server where IIS sites also
use Windows Authentication that takes Kerberos away from *them*. Prefer the account above.

## 4. Switch on Windows sign-in

`C:\TaskBoard\app\.env` (Notepad, no quotes around values):

```ini
TASKBOARD_ENVIRONMENT=production
TASKBOARD_DATA_DIR=C:\ProgramData\TaskBoard
TASKBOARD_HOST=0.0.0.0
TASKBOARD_PORT=8080
TASKBOARD_WINDOWS_AUTH=true
```

- `TASKBOARD_HOST=0.0.0.0`: listen on the server's network addresses. The default, `127.0.0.1`,
  only answers programs on the server itself (right behind IIS, wrong here).
- `TASKBOARD_PORT`: the port people will type.
- `TASKBOARD_WINDOWS_AUTH=true`: answer browsers with the Negotiate challenge.
- Remove `TASKBOARD_TRUSTED_HEADER`, `TASKBOARD_BASE_PATH` and `TASKBOARD_COOKIE_SECURE` if an
  earlier IIS attempt left them there.

Open the port and start:

```powershell
New-NetFirewallRule -DisplayName "TaskBoard (8080)" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
Restart-Service TaskBoard        # Start-Service the first time
Get-Content C:\TaskBoard\logs\TaskBoard.err.log -Tail 5
```

The log should end with `Uvicorn running on http://0.0.0.0:8080`. (TaskBoard's messages go to
`TaskBoard.err.log` even when nothing is wrong.)

Browsers must reach TaskBoard **directly**. Anything that forwards requests in between (IIS, a
load balancer) breaks NTLM, whose two requests must travel over the same connection.

## 5. Accounts: who gets in

Windows tells TaskBoard *who* someone is. What they may do is still decided in TaskBoard, where
each person has an account with roles. There are two ways to give people accounts:

**Invite-only (the default).** An administrator prepares an account per person: *Administration
› Accounts › New account*, with

- **Username**: the Windows login name without the domain, so `jdoe` for `CORP\jdoe`;
- **Sign-in**: *SSO only (pre-provisioned)* (no password; the email can stay empty);
- an **initial role**, e.g. *Editor* on their section.

At that person's first visit the account is recognised by its username and activated. Everyone
else reads the board as an anonymous visitor and sees the message *"Windows sign-in: no account
has been set up for you; ask an administrator"*. An account that already exists with a password
and the same username is simply used; its password keeps working.

**Everyone in the domain.** Add `TASKBOARD_SSO_UNKNOWN_USERS=create` to `.env`: whoever opens
the board gets an account without any roles (so they see what anonymous visitors see), and an
administrator hands out roles afterwards under *Administration › Accounts*.

**Start with yourself.** Nobody has an account yet, so:

1. Open the board from your PC with the server's short name, `http://server01:8080/` (section 6
   explains why the short name). You are not signed in, and you see the message above: that
   message is good news, it means Windows sign-in works.
2. *Log in* (bottom left) as `admin` with the password that the `seed` command printed.
3. Create an account with your own Windows login name and the role *Administrator ·
   Everywhere*. Log out, press *Log in* › *Sign in with Windows*: you are in as yourself.

Worth knowing:

- The `admin` account stays as the way in when Windows sign-in fails. *Log out* leaves you logged
  out in that browser tab, so you can log in as `admin`; a new tab signs you in with Windows
  again.
- To make the board login-only: *Administration › Accounts › Anonymous visitors*, remove
  *Viewer · Everywhere*.
- Two domains with the same login names in them? `TASKBOARD_WINDOWS_AUTH_STRIP_DOMAIN=false`
  keeps the domain: usernames are then `corp\jdoe`.
- `TASKBOARD_WINDOWS_AUTH_AUTOMATIC=false`: nobody is signed in on arrival; the login dialog
  offers *Sign in with Windows*.
- Windows sign-in does not report group memberships, so *Administration › SSO groups* has no
  effect on it: assign roles to accounts.

## 6. Browsers: no password prompt

Whether the browser hands over the Windows login is the browser's decision, by the address:

| Address | Edge and Chrome |
|---|---|
| `http://server01:8080/` (no dots) | Internal by default on domain PCs: works at once. |
| `http://server01.corp.local:8080/` | Only after the site is put in the *Local intranet* zone. |
| `http://10.1.2.3:8080/` | As above, and NTLM only (Kerberos needs a name). |

To put a site in the zone on one PC: Start › *Internet Options* › *Security* › *Local intranet* ›
*Sites* › *Advanced* › add `http://server01.corp.local`. For everyone: ask IT for the group
policy *Site to Zone Assignment List* (value `1` for the site), or the Edge/Chrome policy
`AuthServerAllowlist`. Firefox ignores the zones: `about:config`, add the server name to
`network.negotiate-auth.trusted-uris` and `network.automatic-ntlm-auth.trusted-uris`.

Without any of this the browser shows a **user name and password prompt**. Typing a Windows
login there (`CORP\jdoe`) works, but it is the symptom that the zone is not set. Cancelling it
leaves the visitor anonymous. Private (InPrivate, incognito) windows never hand over the Windows
login by themselves either.

If the zone cannot be arranged for everyone, `TASKBOARD_WINDOWS_AUTH_AUTOMATIC=false` spares
visitors the prompt: only someone who presses *Log in* › *Sign in with Windows* is asked.

## 7. Test

On the server first, then from your PC:

1. `http://localhost:8080/api/health` answers `{"status":"ok",...}`.
2. `http://localhost:8080/api/auth/me` contains `"windows":{"automatic":true}`: the setting is
   read.
3. From your PC, `http://server01:8080/`: your name stands bottom left (or the *no account*
   message appears: section 5). Then `http://server01:8080/api/auth/me` shows your `username`.
4. Kerberos or NTLM? On your PC, in a Command Prompt: `klist`. A ticket for
   `HTTP/server01.corp.local` means Kerberos. None means NTLM was used: it works, see section 10
   if you want Kerberos.
5. *Administration › Audit log* lists every sign-in: `auth.login` with `method: windows`.

## 8. Coming from the IIS guide (route B)

There, an IIS site listens on the public port and forwards to the TaskBoard service on an
internal one. Say the site is on **8111** and the service on **8002**. TaskBoard takes over the
public port, so people keep their address:

```powershell
Import-Module WebAdministration
Stop-Website TaskBoard             # frees port 8111; the site stays, stopped, as a way back
```

In `C:\TaskBoard\app\.env`, change the port and add two lines (section 4 explains them). If the
attempt to pass the user through IIS left `TASKBOARD_TRUSTED_HEADER` there, remove it:

```ini
TASKBOARD_HOST=0.0.0.0
TASKBOARD_PORT=8111
TASKBOARD_WINDOWS_AUTH=true
```

Then fetch the TaskBoard version that has Windows sign-in, and restart:

```powershell
Stop-Service TaskBoard
cd C:\TaskBoard\app
git pull
$env:UV_PYTHON_INSTALL_DIR = "C:\TaskBoard\python"; $env:UV_LINK_MODE = "copy"
uv sync --frozen --no-dev
Start-Service TaskBoard
Get-Content C:\TaskBoard\logs\TaskBoard.err.log -Tail 5     # ...running on http://0.0.0.0:8111
```

The firewall rule for 8111 exists already, the service and its account are the ones from the IIS
guide, and port 8002 is no longer used. Continue with section 5. If the site had *Windows
Authentication* switched on for the header attempt, that no longer matters: the site is stopped.

Way back: put the old port (8002) in `.env` and remove the two lines, `Restart-Service
TaskBoard`, `Start-Website TaskBoard`. Once you are content: `Remove-Website TaskBoard`.

Two things this route cannot do, both IIS features: run under a prefix of another site
(`https://server/taskboard/`), and share port 80 or 443 with other sites. TaskBoard needs a port
of its own.

## 9. HTTP or HTTPS

**Plain HTTP** is what the sections above set up, and Windows sign-in works over it. Worth
knowing:

- No Windows password crosses the network: the browser sends tokens that prove the login.
  TaskBoard's session cookie and the board's contents do travel unencrypted, and so does the
  `admin` password when someone types it.
- Browsers show "Not secure". If a browser or company policy insists on `https://`, you need
  HTTPS.

**HTTPS.** Without IIS there is nothing in front to do it, so TaskBoard does it itself. It needs
the certificate and its private key as two PEM files. IT usually hands out a `.pfx` file (one
file with both, and a password); Git for Windows brings the tool that converts it:

```powershell
New-Item -ItemType Directory -Force C:\TaskBoard\tls
$openssl = "C:\Program Files\Git\usr\bin\openssl.exe"
& $openssl pkcs12 -in C:\TaskBoard\tls\server01.pfx -nokeys -out C:\TaskBoard\tls\cert.pem
& $openssl pkcs12 -in C:\TaskBoard\tls\server01.pfx -nocerts -noenc -out C:\TaskBoard\tls\key.pem
icacls C:\TaskBoard\tls /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "NT SERVICE\TaskBoard:(OI)(CI)RX"
```

Both commands ask for the `.pfx` file's password; if they complain about an *unsupported*
algorithm (older `.pfx` files), add `-legacy`. In `cert.pem` the server's own certificate must
come first, before the certificates of whoever issued it (open it in Notepad: each block says
whose it is). The `icacls` line keeps the key to the service and administrators; delete the
`.pfx` afterwards. Then, in `.env`:

```ini
TASKBOARD_PORT=8443
TASKBOARD_TLS_CERTFILE=C:\TaskBoard\tls\cert.pem
TASKBOARD_TLS_KEYFILE=C:\TaskBoard\tls\key.pem
```

Open port 8443 in the firewall (as in section 4), `Restart-Service TaskBoard`, and use
`https://server01.corp.local:8443/` from then on: the name must be one the certificate is for,
which usually means the full name, so the intranet zone of section 6 now needs the `https://`
address. One port speaks one protocol: the `http://` address stops working. Renewing the
certificate means converting the new `.pfx` and restarting the service.

## 10. When it doesn't work

Look in this order:

1. `Get-Service TaskBoard`: is it running?
2. `C:\TaskBoard\logs\TaskBoard.err.log` (TaskBoard's output) and `TaskBoard.wrapper.log`
   (WinSW's own). Nothing useful: stop the service and run
   `C:\TaskBoard\app\.venv\Scripts\python.exe -m taskboard serve` by hand, it shows the same
   error.
3. In the browser, F12 › *Network*, reload: the line `windows` is the sign-in. `200` means signed
   in, `401` that the browser did not (or could not) answer.

| Symptom | Usual cause |
|---|---|
| The service stops right after starting; the log says `error while attempting to bind` | Something else holds the port: the IIS site is still started (section 8), or another program (section 2's list). |
| Works on the server, not from your PC | The firewall rule, or `TASKBOARD_HOST` is still `127.0.0.1`. |
| A user name and password prompt | The site is not in the intranet zone, or it is a private window (section 6). |
| The prompt comes back although the password is right | The PC's clock is more than 5 minutes off (Kerberos refuses), or NTLM is blocked by a domain policy while Kerberos is not possible (see *No Kerberos*). |
| *"no account has been set up for you"* | Windows sign-in works; the account is missing, or its username is not exactly the Windows login name (section 5). `whoami` on that PC shows the name. |
| Not signed in, no message, *Log in* bottom left | The browser did not answer (section 6), or this tab was logged out or failed before: open a new tab. |
| `api/auth/me` says `"windows":null` | The setting is not read: a typo, a `.env` that is not in `C:\TaskBoard\app\`, or the service was not restarted. |
| The service does not start; the log says `ModuleNotFoundError: No module named 'spnego'` | `uv sync --frozen --no-dev` was not run after the upgrade (section 3). |
| No Kerberos (`klist` shows no `HTTP/` ticket) | The address is an IP address or a name other than the server's own, or the service runs as an ordinary account. An extra name needs an SPN from a domain administrator: `setspn -S HTTP/tasks.corp.local SERVER01`. NTLM keeps it working meanwhile. |
| Sign-in fails now and then, or for everyone behind a proxy | Something forwards the requests (section 4): NTLM cannot cross it. Connect directly. |
| `400 Bad Request` for a few people only | Their Kerberos ticket is large (many group memberships) and TaskBoard was started with plain `uvicorn ...`. `python -m taskboard serve` makes room for it. |
| Log in "works" but you stay logged out, or `csrf_failed` | `TASKBOARD_COOKIE_SECURE=true` on plain http: remove it. |
| Someone is signed in as the wrong person | The browser runs under that Windows login (a shared PC). *Log out* in TaskBoard does not change the Windows user. |

## 11. Day to day, and removing it

- Restart TaskBoard (also after changing `.env`): `Restart-Service TaskBoard`.
- Upgrade: `Stop-Service TaskBoard`, then in `C:\TaskBoard\app`: `git pull`, set the two `UV_*`
  variables, `uv sync --frozen --no-dev`, then `Start-Service TaskBoard`. Migrations run at start.
- Backups and restores: [`OPERATIONS.md`](OPERATIONS.md#backups).
- Someone leaves: suspend their account (*Administration › Accounts*). It takes effect at once,
  whatever Windows says.

To switch Windows sign-in off, remove `TASKBOARD_WINDOWS_AUTH` from `.env` and restart: accounts
and their roles stay. To remove everything:

```powershell
Stop-Service TaskBoard; C:\TaskBoard\TaskBoard.exe uninstall
Remove-NetFirewallRule -DisplayName "TaskBoard (8080)"
Remove-Item -Recurse C:\TaskBoard, C:\ProgramData\TaskBoard   # the data too: back it up first
```
