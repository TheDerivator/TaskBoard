"""Typed application settings, read from environment variables prefixed `TASKBOARD_` (or `.env`)."""

from datetime import date
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"


class UnknownUserPolicy(StrEnum):
    REJECT = "reject"
    CREATE = "create"


class Settings(BaseSettings):
    """All runtime configuration. Every field can be set as `TASKBOARD_<FIELD_NAME>`."""

    model_config = SettingsConfigDict(
        env_prefix="TASKBOARD_",
        # The app folder's .env, whatever the working directory (Windows services and scheduled
        # tasks start elsewhere). Environment variables take precedence over it.
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT

    # Where the SQLite database (by default) and uploaded files live. Keep it outside the code
    # folder in production, e.g. C:\ProgramData\TaskBoard or /var/lib/taskboard.
    data_dir: Path = PROJECT_ROOT / "var"

    # Where `python -m taskboard backup` puts its zips and deletes the ones no longer kept
    # (Administration › Backups shows them). Defaults to <data_dir>/backups. A network share must
    # be a UNC path (\\server\share\TaskBoard): services and scheduled tasks have no drive letters.
    backup_dir: Path | None = None

    # Any SQLAlchemy URL. Defaults to <data_dir>/taskboard.sqlite3.
    # MS SQL example: mssql+pyodbc://user:pass@host/db?driver=ODBC+Driver+18+for+SQL+Server
    database_url: str | None = None

    # Apply migrations and create built-in data at startup. Turn off to manage the schema
    # explicitly with `python -m taskboard db upgrade` (e.g. with several servers on one database).
    auto_migrate: bool = True

    # Password for the built-in `admin` account when it is first created. When unset, a random
    # password is generated and printed once; the admin must change it at first login.
    initial_admin_password: SecretStr | None = None

    # Session cookies get the Secure flag. Leave unset to decide per request (on when HTTPS).
    cookie_secure: bool | None = None
    session_lifetime_hours: int = 24 * 14

    # Password login throttling: failed attempts allowed per account / per client address within
    # the window. Behind a reverse proxy, list it in `trusted_proxies` so addresses are real.
    login_max_failures_per_user: int = 5
    login_max_failures_per_ip: int = 50
    login_throttle_minutes: int = 15

    # What happens when someone signs in through SSO whom no administrator has set up:
    # "reject" (default: invite-only) or "create" (an account without any rights).
    sso_unknown_users: UnknownUserPolicy = UnknownUserPolicy.REJECT

    # SSO with OpenID Connect (e.g. Microsoft Entra ID). Enabled when issuer and client id are set.
    # Entra ID: issuer https://login.microsoftonline.com/<tenant id>/v2.0, subject claim "oid".
    oidc_name: str = "entra"  # stored with linked accounts; don't change once in use
    oidc_display_name: str = "Microsoft"  # the button says "Sign in with <this>"
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_scopes: str = "openid profile email"
    oidc_subject_claim: str = "sub"
    oidc_email_claims: str = "email,preferred_username,upn"  # first one present is used
    oidc_groups_claim: str = "groups"

    # The address people use to reach the app, e.g. https://tasks.example.com/taskboard/.
    # Needed for SSO redirect URIs when a proxy changes the host or path; else taken from requests.
    public_url: str | None = None

    # SSO through a trusted reverse proxy that authenticates users and passes them in headers
    # (e.g. IIS with Windows authentication). Enabled when `trusted_header` names the user header.
    # Only requests that come through one of the `trusted_proxies` may assert identities.
    trusted_header: str | None = None  # e.g. "X-Remote-User" (value like CORP\jdoe)
    trusted_header_email: str | None = None
    trusted_header_name: str | None = None
    trusted_header_groups: str | None = None  # a comma-separated list in one header
    trusted_header_strip_domain: bool = True  # CORP\jdoe → username hint "jdoe"

    # Windows sign-in by the app itself, without IIS in front (docs/WINDOWS-SIGNIN.md): the browser
    # proves who is logged in to Windows (HTTP Negotiate: Kerberos or NTLM), and Windows checks
    # it. Needs a Windows server; people reach the app directly, not through a proxy.
    windows_auth: bool = False
    windows_auth_automatic: bool = True  # the page tries it by itself; false: only on request
    windows_auth_strip_domain: bool = True  # CORP\jdoe → username hint "jdoe"

    # Reverse proxies (addresses or networks, comma-separated) whose X-Forwarded-For/-Proto headers
    # are believed: the client address and scheme then come from them. Also decides who may
    # assert identities for `trusted_header`.
    trusted_proxies: str = "127.0.0.1,::1"

    # URL path the app is published under, e.g. "/taskboard/" behind an IIS or nginx prefix
    # (the proxy strips the prefix before forwarding). Used for the page's <base href>.
    base_path: str = "/"

    # Pretend it is this date (YYYY-MM-DD) instead of the server's own: process-change states
    # ("Test running", "Planned") depend on it. Meant for tests and frozen demos only.
    today: date | None = None

    # For `python -m taskboard serve`.
    host: str = "127.0.0.1"
    port: int = 8000
    # HTTPS by the app itself, for when no proxy in front does it: the certificate (PEM, followed
    # by its intermediate certificates) and its private key (PEM, not password-protected).
    tls_certfile: Path | None = None
    tls_keyfile: Path | None = None

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'taskboard.sqlite3').as_posix()}"

    @property
    def normalized_base_path(self) -> str:
        """`base_path` with exactly one leading and one trailing slash."""
        inner = self.base_path.strip().strip("/")
        return f"/{inner}/" if inner else "/"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def resolved_backup_dir(self) -> Path:
        return self.backup_dir or self.data_dir / "backups"

    def current_date(self) -> date:
        """Today on the server (in its own time zone), unless `today` pins it."""
        return self.today or date.today()


@lru_cache
def get_settings() -> Settings:
    """Settings from the environment, created once per process."""
    return Settings()
