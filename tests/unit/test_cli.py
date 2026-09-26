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
