"""Settings defaults and environment overrides."""

from pathlib import Path

import pytest

from taskboard.config import PROJECT_ROOT, Environment, Settings


def test_default_database_is_sqlite_inside_data_dir(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)  # pyright: ignore[reportCallIssue]
    expected = f"sqlite:///{(tmp_path / 'taskboard.sqlite3').as_posix()}"
    assert settings.resolved_database_url == expected
    assert settings.uploads_dir == tmp_path / "uploads"


def test_explicit_database_url_wins(tmp_path: Path) -> None:
    url = "mssql+pyodbc://user:secret@host/taskboard?driver=ODBC+Driver+18+for+SQL+Server"
    settings = Settings(data_dir=tmp_path, database_url=url, _env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.resolved_database_url == url


def test_environment_variables_are_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TASKBOARD_ENVIRONMENT", "production")
    monkeypatch.setenv("TASKBOARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TASKBOARD_PORT", "9123")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.environment is Environment.PRODUCTION
    assert settings.data_dir == tmp_path
    assert settings.port == 9123


def test_the_env_file_is_the_app_folders_whatever_the_working_directory() -> None:
    assert Settings.model_config.get("env_file") == PROJECT_ROOT / ".env"
