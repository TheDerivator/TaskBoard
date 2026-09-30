"""Command line: argument parsing, and the database commands end to end."""

from pathlib import Path

import pytest

from taskboard.cli import build_parser, main
from taskboard.config import get_settings


def test_serve_accepts_host_port_and_reload() -> None:
    args = build_parser().parse_args(
        ["serve", "--host", "192.0.2.10", "--port", "9000", "--reload"]
    )
    assert (args.command, args.host, args.port, args.reload) == ("serve", "192.0.2.10", 9000, True)


def test_serve_leaves_forwarded_headers_to_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uvicorn's own proxy handling would hide the proxy's address (see taskboard/api/client.py)."""
    import uvicorn

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    assert main(["serve", "--port", "9000"]) == 0
    assert calls[0]["proxy_headers"] is False and calls[0]["port"] == 9000
    assert calls[0]["h11_max_incomplete_event_size"] is None  # Uvicorn's default limit
    assert calls[0]["ssl_certfile"] is None and calls[0]["ssl_keyfile"] is None  # plain HTTP


def _serve_with(monkeypatch: pytest.MonkeyPatch, **env: str) -> tuple[int, list[dict[str, object]]]:
    """Run `serve` with these TASKBOARD_ settings; the exit code and what Uvicorn was asked."""
    import uvicorn

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    for name, value in env.items():
        monkeypatch.setenv(f"TASKBOARD_{name}", value)
    get_settings.cache_clear()
    try:
        return main(["serve"]), calls
    finally:
        get_settings.cache_clear()


def test_serve_makes_room_for_kerberos_tickets(monkeypatch: pytest.MonkeyPatch) -> None:
    """With Windows sign-in, a ticket of Windows' maximum size must fit in the request headers."""
    code, calls = _serve_with(monkeypatch, WINDOWS_AUTH="true")
    limit = calls[0]["h11_max_incomplete_event_size"]
    assert code == 0 and isinstance(limit, int) and limit > 48_000 * 4 / 3  # base64-encoded


def test_serve_can_do_https_itself(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    code, calls = _serve_with(monkeypatch, TLS_CERTFILE=str(cert), TLS_KEYFILE=str(key))
    assert code == 0
    assert (calls[0]["ssl_certfile"], calls[0]["ssl_keyfile"]) == (str(cert), str(key))

    monkeypatch.delenv("TASKBOARD_TLS_KEYFILE")
    code, calls = _serve_with(monkeypatch, TLS_CERTFILE=str(cert))
    assert code == 1 and calls == []  # half a configuration must not silently mean plain HTTP
    assert "TASKBOARD_TLS_KEYFILE" in capsys.readouterr().out


def test_a_command_is_required() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_db_upgrade_and_seed_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TASKBOARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TASKBOARD_INITIAL_ADMIN_PASSWORD", "cli-admin-password")
    get_settings.cache_clear()
    try:
        assert main(["db", "upgrade"]) == 0
        assert main(["seed", "--sample", "--demo-password", "demo-password-1"]) == 0
        first = capsys.readouterr().out
        assert main(["seed", "--sample"]) == 0
        second = capsys.readouterr().out
    finally:
        get_settings.cache_clear()
    assert "Database schema is up to date." in first
    assert "created user admin" in first and "Loaded the sample board." in first
    assert "Admin password" not in first  # it was configured, not generated
    assert "Board is not empty" in second and "created" not in second
    assert (tmp_path / "taskboard.sqlite3").exists()
