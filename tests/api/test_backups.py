"""Administration › Backups (D-100): who may see them, why each backup is kept, the retention."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from taskboard.config import Settings
from taskboard.db.base import utcnow
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from taskboard.services.backup import STAMP
from taskboard.web import create_app
from tests.api.conftest import LoginAs
from tests.conftest import TEST_ADMIN_PASSWORD, start_client
from tests.helpers import fake_backups, login

MARCH = ["2025-03-06", "2025-03-05", "2025-03-04", "2025-03-03", "2025-02-10"]


@pytest.fixture
def elsewhere(
    settings: Settings, sample_database: Database, tmp_path: Path
) -> Iterator[TestClient]:
    """The administrator, on a server whose backup folder is a file (so it cannot be read)."""
    del sample_database
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    app = create_app(settings.model_copy(update={"backup_dir": blocker}))
    for client in start_client(app):
        login(client, "admin", TEST_ADMIN_PASSWORD)
        yield client


def test_only_user_administrators_see_backups(board: TestClient, login_as: LoginAs) -> None:
    retention = {"newest": 2, "weekly": 1, "monthly": 2}
    assert board.get("/api/admin/backups").status_code == 401
    assert board.put("/api/admin/backups/retention", json=retention).status_code == 401
    login_as("editor", [(BuiltinRole.EDITOR, Scope.everywhere())])
    assert board.get("/api/admin/backups").status_code == 403
    assert board.put("/api/admin/backups/retention", json=retention).status_code == 403


def test_the_backups_and_why_each_is_kept(login_as: LoginAs, settings: Settings) -> None:
    admin = login_as("admin")
    folder = settings.resolved_backup_dir
    names = fake_backups(folder, *MARCH)
    (folder / "pristine-demo.zip").write_bytes(b"made by hand, not listed")
    overview = admin.get("/api/admin/backups").json()
    assert overview["location"] == str(folder) and overview["problem"] is None
    assert [(b["name"], b["kept_as"]) for b in overview["backups"]] == [
        (names[0], ["newest"]),
        (names[1], ["newest"]),
        (names[2], []),  # deleted at the next backup
        (names[3], ["weekly", "monthly"]),  # Monday 3 March
        (names[4], ["monthly"]),
    ]
    assert overview["backups"][0]["size"] == 1000
    assert overview["total_size"] == 15_000
    assert overview["overdue"] is True  # the newest is months old
    assert overview["retention"] == {"newest": 2, "weekly": 1, "monthly": 2}  # the defaults
    assert overview["limits"]["newest"] == {"min": 2, "max": 30}

    just_now = (utcnow() - timedelta(minutes=5)).strftime(STAMP)
    (folder / f"taskboard-backup-{just_now}.zip").write_bytes(b"z")
    overview = admin.get("/api/admin/backups").json()
    assert overview["overdue"] is False and "newest" in overview["backups"][0]["kept_as"]


def test_retention_is_checked_saved_and_audited(login_as: LoginAs, settings: Settings) -> None:
    admin = login_as("admin")
    names = fake_backups(settings.resolved_backup_dir, *MARCH)
    for wrong in (
        {"newest": 1, "weekly": 1, "monthly": 2},  # only the last backup would remain
        {"newest": 2, "weekly": 0, "monthly": 2},
        {"newest": 2, "weekly": 1, "monthly": 25},
        {"newest": 2, "weekly": 1},
    ):
        assert admin.put("/api/admin/backups/retention", json=wrong).status_code == 422, wrong

    chosen = {"newest": 3, "weekly": 2, "monthly": 6}
    response = admin.put("/api/admin/backups/retention", json=chosen)
    assert response.status_code == 200 and response.json()["retention"] == chosen
    kept = {b["name"]: b["kept_as"] for b in response.json()["backups"]}
    assert kept[names[2]] == ["newest"]
    assert admin.get("/api/admin/backups").json()["retention"] == chosen

    [entry] = admin.get("/api/admin/audit", params={"limit": 1}).json()
    assert entry["action"] == "backup.retention_changed" and entry["details"] == chosen
    assert entry["actor"] == "Administrator"


def test_a_folder_that_cannot_be_read_is_explained(
    login_as: LoginAs, elsewhere: TestClient
) -> None:
    missing = login_as("admin").get("/api/admin/backups").json()  # nothing backed up yet
    assert missing["problem"].startswith("The folder does not exist or cannot be reached")
    assert missing["backups"] == [] and missing["overdue"] is True

    unreadable = elsewhere.get("/api/admin/backups").json()
    assert unreadable["problem"].startswith("The folder cannot be read")
    assert unreadable["location"].endswith("blocker")
