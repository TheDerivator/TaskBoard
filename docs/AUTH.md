# Accounts, access rights and SSO

How TaskBoard decides who someone is and what they may do. Code: `taskboard/domain/access.py`
(the rules, pure), `taskboard/identity/` (database-backed parts), `taskboard/services/auth.py`
(use cases), `taskboard/api/routers/auth.py` (endpoints).

## Concepts

| Concept | Meaning |
|---|---|
| **User** | A login account. Built-in: `admin` (break-glass administrator) and `anonymous` (every visitor who is not logged in). |
| **Person** | Someone on the board (leads/helps on tasks). Optionally linked 1:1 to a user. |
| **Permission** | `task.view`, `task.edit`, `task.comment`, `task.delete` (per section); `project.manage`, `people.manage`, `users.manage` (global only). |
| **Role** | A named set of permissions. Built-in: *Viewer*, *Editor*, *Administrator*; their permissions are re-synced from code at every start. Custom roles are possible. |
| **Assignment** | A user holds a role at a **scope**: everywhere, one department (all its sections), or one section. |
| **Section** | The organizational section (Department › Section, e.g. STL › Quality). Every task has exactly one, and that decides which assignments apply to the task. Project nodes are *not* permission scopes. |

## Rules

1. A per-section permission applies to a task if the user holds it globally, for the task's
   department, or for the task's section.
2. A global permission (`*.manage`) only counts when assigned globally. An *Administrator* role
   assigned to one section gives full task rights there, but no user or project management.
3. **Anonymous rights are a floor**: every logged-in user also has what `anonymous` has, so logging
   in never shows less. By default `anonymous` is *Viewer* everywhere; an admin can narrow or remove
   that, which makes (parts of) the board login-only.
4. Lists only contain what the caller may view. Ranks stay global, so a restricted viewer may see
   gaps (#1, #4, #5); counts only include visible tasks.
5. Changing a task's section needs edit rights on both the old and the new section.
6. A suspended account loses access at its next request (sessions are server-side and checked on
   every request). A pending account (pre-provisioned for SSO) cannot log in with a password.
7. An account flagged *must change password* (e.g. the generated first admin password) can do
   nothing but change its password.
8. The server enforces every rule; `GET /api/auth/me` tells the frontend where each permission
   applies so it can hide controls, nothing more.

## Password login (built-in accounts)

- Passwords are hashed with argon2id; hashes are upgraded automatically at login when the
  parameters change. Minimum length 10.
- Sessions: a random 256-bit token in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` over HTTPS,
  or forced with `TASKBOARD_COOKIE_SECURE`); the database stores only its SHA-256 hash. Lifetime
  `TASKBOARD_SESSION_LIFETIME_HOURS` (default 14 days). Logout and password changes end sessions
  immediately; a password change ends all *other* sessions of that account.
- Throttling: after `TASKBOARD_LOGIN_MAX_FAILURES_PER_USER` (5) failures since the last success,
  or `TASKBOARD_LOGIN_MAX_FAILURES_PER_IP` (50) from one address, within
  `TASKBOARD_LOGIN_THROTTLE_MINUTES` (15), logins are refused with HTTP 429. Behind a reverse
  proxy, list it in `TASKBOARD_TRUSTED_PROXIES` (see *Reverse proxies and client addresses*),
  otherwise all users share the proxy's address.
- Errors never reveal whether a username exists, and unknown usernames take as long as known ones.
- CSRF: every state-changing API request must carry the `X-CSRF-Token` header equal to the
  `taskboard_csrf` cookie (double submit), on top of `SameSite` cookies.
- The first `admin` password comes from `TASKBOARD_INITIAL_ADMIN_PASSWORD`, or is generated,
  printed once in the log / CLI output, and must be changed at first login.

## SSO (external identity providers)

SSO is **off unless configured**. With no provider configured (e.g. the Linux demo server) only
built-in accounts exist, the SSO sign-in routes are not even mounted, and identity headers are
ignored. Three providers exist, and they can be enabled together:

| Provider | Shape | Name (stored with linked accounts) | Enabled by |
|---|---|---|---|
| OpenID Connect, e.g. **Microsoft Entra ID** | *redirect*: the login dialog shows "Sign in with Microsoft" | `TASKBOARD_OIDC_NAME` (default `entra`) | `TASKBOARD_OIDC_ISSUER` + `TASKBOARD_OIDC_CLIENT_ID` |
| **Windows sign-in** by TaskBoard itself | *negotiate*: the browser proves the Windows login to the app (Kerberos or NTLM), once per session | `windows` | `TASKBOARD_WINDOWS_AUTH` |
| **Trusted header** from an authenticating proxy | *ambient*: every request through the proxy carries the user | `proxy` | `TASKBOARD_TRUSTED_HEADER` |

For Windows accounts on a Windows server, use **Windows sign-in**: the trusted header cannot be
filled in by IIS's own modules (see its section below).

Code: `taskboard/identity/providers/` (`oidc.py`, `negotiate.py`, `header.py`),
`taskboard/services/sso.py`, `taskboard/api/routers/` (`sso.py`, `windows.py`),
`taskboard/identity/provisioning.py`.

### How an SSO login becomes a TaskBoard user

A provider hands over an `ExternalIdentity(provider, subject, email, display_name, groups, username)`.
`taskboard/identity/provisioning.py` then:

1. uses the user already linked to `(provider, subject)`, if any;
2. otherwise looks for a user with the same **email**: an account an administrator prepared in
   advance (status *pending*, with role assignments). It links the identity and activates the
   account, so the prepared rights apply from the first request;
3. otherwise (Windows sign-in usually has no email) looks for a user whose **username** equals
   the provider's login name (`CORP\jdoe` → `jdoe`) and links it the same way;
4. otherwise follows `TASKBOARD_SSO_UNKNOWN_USERS`: `reject` (default, invite-only: "no account
   has been set up for you") or `create` (a new account without roles, so it has only the
   anonymous floor).

Built-in accounts (`admin`, `anonymous`) are never linked by email or username, and an account
already linked to another identity of the same provider is not taken over. Suspended accounts
are refused whatever the provider says. The name an administrator gave an account is kept.
Local password login keeps working next to SSO; the built-in `admin` remains the break-glass
account. Links, activations and created accounts are written to the audit log.

### Pre-provisioning workflow (admin)

1. *Administration › Accounts › New account*: the person's work email (Entra ID: their UPN) and,
   for Windows sign-in, their Windows login name as username; no password; status *pending*.
2. Assign roles and scopes, e.g. *Editor* on STL › Quality.
3. Optionally link the account to their Person record.
4. At the person's first SSO login the account is linked and activated with exactly these rights.

### Group mappings

*Administration › SSO groups* gives everyone in an identity-provider group a role at a scope
("members of `STL-Maintenance` are *Editor* on STL › Maintenance"). The groups a provider reports
are stored with the linked identity and refreshed at every sign-in (OIDC) or whenever the proxy
reports different ones (trusted header), so rights follow group membership. Group rights come
*on top of* the account's own assignments and the anonymous floor; they never take anything away.
Group names are compared exactly (case-sensitive), as the provider sends them.

- Entra ID sends group **object ids** (GUIDs), not names. Tokens carry at most 200 groups; beyond
  that Entra ID leaves the claim out ("overage"), so configure the groups claim as *Groups
  assigned to the application* and assign just the groups you map.
- A group mapping only grants rights to accounts that exist: with `reject` (the default), people
  still need an account (pre-provisioned, or `TASKBOARD_SSO_UNKNOWN_USERS=create`).

### Configuring Microsoft Entra ID (OpenID Connect)

1. Entra admin center › *App registrations* › *New registration*: accounts in this organizational
   directory only (**single tenant**). Redirect URI, platform *Web*:
   `https://<host>/<base path>/api/auth/sso/entra/callback`
   (the `entra` part is `TASKBOARD_OIDC_NAME`).
2. *Certificates & secrets*: create a client secret. Note its expiry date: sign-in stops working
   when it expires.
3. Optional, for group mappings: *Token configuration* › *Add groups claim* (see the overage note).
4. Settings (environment variables or `.env`):

   ```ini
   TASKBOARD_OIDC_ISSUER=https://login.microsoftonline.com/<tenant id>/v2.0
   TASKBOARD_OIDC_CLIENT_ID=<application (client) id>
   TASKBOARD_OIDC_CLIENT_SECRET=<secret value>
   TASKBOARD_OIDC_SUBJECT_CLAIM=oid
   TASKBOARD_PUBLIC_URL=https://tasks.corp.example/taskboard/
   ```

   Optional: `TASKBOARD_OIDC_DISPLAY_NAME` (button text, default "Microsoft"),
   `TASKBOARD_OIDC_SCOPES` (default `openid profile email`), `TASKBOARD_OIDC_EMAIL_CLAIMS` (first
   claim present is the email, default `email,preferred_username,upn`),
   `TASKBOARD_OIDC_GROUPS_CLAIM` (default `groups`).

`TASKBOARD_PUBLIC_URL` is the address people type; the redirect URI is built from it and must match
the registration exactly. Without it, the URL is taken from the request, which is wrong as soon as
a proxy changes host, scheme or path. Use a tenant-specific issuer, never `common` or
`organizations`: the token's issuer is checked against it.

**What the app checks.** Authorization code flow with PKCE. Each sign-in gets a random *state*
(stored hashed, single use, 10 minutes, bound to the browser by the `taskboard_sso_state`
cookie) and a *nonce* that must come back inside the ID token. The ID token is verified locally:
signature against the provider's published keys (refetched once when an unknown key id appears,
for key rotation), algorithm (RS/PS/ES only, never `none` or HMAC), issuer, audience, expiry.
After sign-in the browser returns to the page it started from (only paths on this site: no
open redirects). Failures return to the board with a message ("Sign-in failed: ...").

### Configuring Windows sign-in (Negotiate, without IIS)

Step by step, for a first setup: [`WINDOWS-SIGNIN.md`](WINDOWS-SIGNIN.md). In short: TaskBoard
runs as a Windows service that browsers reach **directly**, and

```ini
TASKBOARD_WINDOWS_AUTH=true
TASKBOARD_HOST=0.0.0.0
```

Optional: `TASKBOARD_WINDOWS_AUTH_AUTOMATIC=false` (nobody is signed in on arrival; the login
dialog offers "Sign in with Windows"), `TASKBOARD_WINDOWS_AUTH_STRIP_DOMAIN=false` (accounts are
pre-provisioned as `corp\jdoe` instead of `jdoe`), `TASKBOARD_TLS_CERTFILE` +
`TASKBOARD_TLS_KEYFILE` (HTTPS by the app itself, as no proxy is in front).

**How it works.** The page posts to `/api/auth/windows` (mounted only when switched on). The
answer is `401` with `WWW-Authenticate: Negotiate`; the browser, if the site is in its intranet
zone, repeats the request with a token, and Windows (SSPI, through pyspnego) verifies it:
Kerberos in one request, NTLM in two. The result, `CORP\jdoe`, goes through the provisioning
above (matched on the login name: Windows tells no email), and TaskBoard starts an **ordinary
session**. So:

- Only that one endpoint challenges. Every other request is judged by the session cookie, which
  keeps anonymous reading, the built-in `admin` and "Log out" working. After a logout the page
  does not sign in by itself again in that browser tab.
- With `..._AUTOMATIC` on (the default) the page makes that request by itself when it loads for
  a visitor who is not signed in, once per tab, before showing anything. A browser that does
  not answer leaves the visitor anonymous, silently; someone Windows identified but TaskBoard
  refuses (no account, suspended) is told so.
- A refused token is challenged again, so the browser can ask for a user name and password.
- NTLM's two requests must arrive on the **same connection**: a half-finished handshake is
  remembered per connection for 30 seconds (in memory, in the one server process). A reverse
  proxy in between, which shares its connections among clients, breaks that. Kerberos, being
  one request, is not affected.
- Kerberos tickets travel in a request header and can reach 64 kB (users in many groups).
  `python -m taskboard serve` raises Uvicorn's header limit (16 kB) to 128 kB when Windows
  sign-in is on; with plain `uvicorn` pass `--h11-max-incomplete-event-size 131072`.
- For Kerberos the service must run as an identity the domain knows under the name in the
  address: the service's own account (`NT SERVICE\TaskBoard`), `LocalSystem` and
  `NetworkService` act as the computer, whose name is registered from the start. A domain
  service account needs `setspn -S HTTP/<server> <account>`.
- No groups are reported, so group mappings do not apply to this provider.

Proved by tests with a stand-in for SSPI on every platform, and on Windows against the real one
(`tests/api/test_windows_auth.py`, and `tests/e2e/test_windows_signin.py` with a real browser
over NTLM). Not yet tried in a domain (Kerberos).

### Configuring a trusted header (an authenticating proxy)

A reverse proxy authenticates the user and passes the login name to TaskBoard in a request
header. Only do this when TaskBoard is reachable **exclusively** through that proxy.

> **IIS cannot do this with its own modules.** The plan was: Windows Authentication on the IIS
> site, and a URL Rewrite rule that copies `{LOGON_USER}` into `X-Remote-User`. On a real IIS
> the header arrives empty: URL Rewrite runs when a request begins, before IIS authenticates
> it, so `{LOGON_USER}` is not known yet. It takes a custom module (or a small proxy program
> of your own behind IIS) to set the header after authentication. For Windows accounts, use
> Windows sign-in above instead. The provider remains for proxies that do authenticate first
> (oauth2-proxy, Apache with `mod_auth_gssapi`, such a custom module).

- Run TaskBoard on `127.0.0.1` (the default `TASKBOARD_HOST`) so nobody can reach it around the
  proxy.
- The proxy sets the header on **every** request, overwriting whatever a client sent.
- Settings:

  ```ini
  TASKBOARD_TRUSTED_HEADER=X-Remote-User
  TASKBOARD_TRUSTED_PROXIES=127.0.0.1,::1
  ```

  Optional headers: `TASKBOARD_TRUSTED_HEADER_EMAIL`, `TASKBOARD_TRUSTED_HEADER_NAME`,
  `TASKBOARD_TRUSTED_HEADER_GROUPS` (comma-separated group names in one header).
  `TASKBOARD_TRUSTED_HEADER_STRIP_DOMAIN=false` keeps the domain, so accounts are pre-provisioned
  as `corp\jdoe` instead of `jdoe`.

The header is believed only on requests that come through one of `TASKBOARD_TRUSTED_PROXIES`;
from anywhere else it is ignored and a warning is logged once. Visitors are signed in on every
request, so the sidebar offers them no "Log out" (it says "Signed in through Windows sign-in").
To use the built-in `admin` account, open TaskBoard on the server itself at
`http://127.0.0.1:8000/`: requests that bypass the proxy carry no identity header, so the login
dialog is there.

### Reverse proxies and client addresses

`TASKBOARD_TRUSTED_PROXIES` (addresses or networks, comma-separated; default `127.0.0.1,::1`)
lists the reverse proxies whose `X-Forwarded-For` and `X-Forwarded-Proto` headers TaskBoard
believes. The client's address (login throttling, audit) and the scheme (`Secure` cookies,
redirect URIs) then come from those headers, and the trusted-header provider knows the request
came through the proxy. IIS ARR appends the client's port (`203.0.113.5:51234`); that is handled.

The app reads these headers itself (`taskboard/api/client.py`), so Uvicorn's own
`--proxy-headers` must be **off**: it would replace the proxy's address with the client's, and
the identity header would then be ignored. `python -m taskboard serve` turns it off; when
starting Uvicorn directly, pass `--no-proxy-headers`.

### Security notes

- `subject` is the provider's **stable, non-reassignable** id (Entra ID: `oid`, with a
  single-tenant registration; Windows sign-in and trusted header: the full `DOMAIN\login`),
  never an email or name.
- Windows sign-in links a prepared account by its **username**: whoever holds that Windows
  login gets that account (built-in accounts excepted), so name local accounts with that in
  mind. With several domains that reuse login names, keep the domain
  (`TASKBOARD_WINDOWS_AUTH_STRIP_DOMAIN=false`).
- Windows sign-in over plain HTTP sends no password, but NTLM can be relayed by someone who
  lures a user to a server of theirs, and the session cookie travels unencrypted: use HTTPS
  beyond an experiment. The handshake is not bound to the TLS channel (no Extended Protection).
- Emails link prepared accounts, so they must come from a directory your organization manages:
  in a single tenant, Entra ID's `email`/`preferred_username` are set by your directory admins.
  After the first link, the account is found by `subject` only.
- Ambient (header) sign-in must only be enabled when the app is reachable exclusively through
  the proxy that sets the header, and the proxy must overwrite that header on every request.
  Anything that can send requests from a trusted proxy address (with the default setting: any
  program on the server itself) can claim any identity.
- Group mappings are powerful: anyone who can add people to a mapped group grants them rights here.
