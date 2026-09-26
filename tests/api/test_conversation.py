"""Conversation API: timeline, posting rights, editing, image uploads and their access rules."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from taskboard.config import Settings
from taskboard.db.base import utcnow
from taskboard.db.models import Attachment
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from taskboard.services.attachments import MAX_ATTACHMENT_BYTES
from taskboard.services.sample_data import defect_map_png
from tests.api.conftest import Ids, LoginAs
from tests.helpers import revoke_anonymous_access

PNG = defect_map_png(40, 20)
STL_EDITOR = "stl.editor"


def stl_editor(login_as: LoginAs, ids: Ids) -> TestClient:
    return login_as(STL_EDITOR, [(BuiltinRole.EDITOR, Scope.department(ids.departments["STL"]))])


def upload(client: TestClient, key: str, data: bytes = PNG, name: str = "map.png") -> dict:  # type: ignore[type-arg]
    response = client.post(
        f"/api/tasks/{key}/attachments", files={"file": (name, data, "image/png")}
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------- reading


def test_the_sample_timeline(board: TestClient) -> None:
    body = board.get("/api/tasks/T-104/conversation").json()
    kinds = [item["type"] if item["type"] == "post" else item["kind"] for item in body["items"]]
    assert kinds == ["status_changed", "post", "post", "post", "post"]
    event, update_post, reply, mention, _answer = body["items"]
    assert event["data"] == {"from": "idea", "to": "started"}
    assert event["actor"]["display_name"] == "Anna Claes"
    assert update_post["is_update"] is True
    assert "<strong>Week 38 status</strong>" in update_post["html"]
    assert '<img src="api/attachments/' in update_post["html"]
    assert "<code>WR-2291</code>" in reply["html"]
    assert '<span class="mention">@Anna</span>' in mention["html"]
    assert '<a class="task-ref" href="t/117"' in mention["html"]
    assert body["post_count"] == 4
    assert body["can_comment"] is False
    assert all(item.get("can_edit") in (None, False) for item in body["items"])


def test_updates_only(board: TestClient) -> None:
    body = board.get("/api/tasks/T-104/conversation", params={"updates_only": True}).json()
    assert [item["type"] for item in body["items"]] == ["post"]
    assert body["items"][0]["is_update"] is True
    assert body["post_count"] == 4


def test_the_task_detail_counts_posts(board: TestClient) -> None:
    assert board.get("/api/tasks/T-104").json()["post_count"] == 4
    assert board.get("/api/tasks/T-117").json()["post_count"] == 0


def test_the_sample_image_is_served(board: TestClient) -> None:
    html = board.get("/api/tasks/T-104/conversation").json()["items"][1]["html"]
    src = html.split('<img src="')[1].split('"')[0]
    response = board.get(f"/{src}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content.startswith(b"\x89PNG")


# ---------------------------------------------------------------- posting


def test_who_may_post(board: TestClient, login_as: LoginAs, ids: Ids) -> None:
    body = {"body_md": "Looks good"}
    assert board.post("/api/tasks/T-104/posts", json=body).status_code == 401
    viewer = login_as("viewer", [(BuiltinRole.VIEWER, Scope.everywhere())])
    assert viewer.post("/api/tasks/T-104/posts", json=body).status_code == 403
    viewer.post("/api/auth/logout")
    editor = stl_editor(login_as, ids)
    assert editor.post("/api/tasks/T-130/posts", json=body).status_code == 403  # R&D
    created = editor.post(
        "/api/tasks/T-104/posts", json={"body_md": "**Done** with @Dries", "is_update": True}
    )
    assert created.status_code == 201
    post = created.json()
    assert post["author"]["display_name"] == "Stl.Editor"
    assert post["is_update"] is True and post["can_edit"] is True
    assert '<span class="mention">@Dries</span>' in post["html"]
    assert editor.get("/api/tasks/T-104/conversation").json()["post_count"] == 5


def test_empty_posts_are_refused(login_as: LoginAs) -> None:
    client = login_as("admin")
    assert client.post("/api/tasks/T-104/posts", json={"body_md": "   "}).status_code == 422


def test_authors_edit_and_delete_their_own_posts(login_as: LoginAs, ids: Ids) -> None:
    editor = stl_editor(login_as, ids)
    post = editor.post("/api/tasks/T-104/posts", json={"body_md": "first"}).json()
    edited = editor.patch(
        f"/api/posts/{post['id']}", json={"body_md": "second", "is_update": False}
    ).json()
    assert edited["body_md"] == "second" and edited["edited_at"] is not None
    sample_post = editor.get("/api/tasks/T-104/conversation").json()["items"][1]["id"]  # Anna's
    assert (
        editor.patch(
            f"/api/posts/{sample_post}", json={"body_md": "x", "is_update": False}
        ).status_code
        == 403
    )
    assert editor.delete(f"/api/posts/{sample_post}").status_code == 403
    assert editor.delete(f"/api/posts/{post['id']}").status_code == 204
    assert editor.delete(f"/api/posts/{post['id']}").status_code == 404


def test_administrators_may_remove_any_post(login_as: LoginAs) -> None:
    admin = login_as("admin")
    sample_post = admin.get("/api/tasks/T-104/conversation").json()["items"][2]["id"]
    assert admin.delete(f"/api/posts/{sample_post}").status_code == 204
    assert (
        admin.patch(
            f"/api/posts/{sample_post}", json={"body_md": "x", "is_update": False}
        ).status_code
        == 404
    )


def test_preview_renders_like_a_post(board: TestClient, login_as: LoginAs) -> None:
    assert board.post("/api/markdown/preview", json={"body_md": "**x**"}).status_code == 401
    client = login_as("admin")
    html = client.post("/api/markdown/preview", json={"body_md": "**x** T-104"}).json()["html"]
    assert "<strong>x</strong>" in html and 'href="t/104"' in html


# ---------------------------------------------------------------- images


def test_upload_then_post_attaches_the_image(
    login_as: LoginAs, ids: Ids, sample_database: Database
) -> None:
    editor = stl_editor(login_as, ids)
    uploaded = upload(editor, "T-104", name="../../etc/Roll 7 marks.PNG")
    assert uploaded["filename"] == "Roll 7 marks.png"
    assert uploaded["url"] == f"api/attachments/{uploaded['id']}/Roll%207%20marks.png"
    assert uploaded["markdown"] == f"![Roll 7 marks.png]({uploaded['url']})"
    post = editor.post(
        "/api/tasks/T-104/posts", json={"body_md": f"Chatter marks:\n\n{uploaded['markdown']}"}
    ).json()
    assert f'<img src="{uploaded["url"]}"' in post["html"]
    with sample_database.session() as s:
        attachment = s.scalars(
            select(Attachment).where(Attachment.public_id == uploaded["id"])
        ).one()
        assert attachment.post_id == post["id"]
    assert editor.get(f"/{uploaded['url']}").status_code == 200


def test_only_real_images_of_limited_size(login_as: LoginAs) -> None:
    client = login_as("admin")
    fake = client.post(
        "/api/tasks/T-104/attachments", files={"file": ("x.png", b"not a png", "image/png")}
    )
    assert fake.status_code == 422
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>'
    assert (
        client.post(
            "/api/tasks/T-104/attachments", files={"file": ("x.svg", svg, "image/svg+xml")}
        ).status_code
        == 422
    )
    huge = PNG + b"\0" * MAX_ATTACHMENT_BYTES
    too_big = client.post(
        "/api/tasks/T-104/attachments", files={"file": ("big.png", huge, "image/png")}
    )
    assert too_big.status_code == 422 and "at most 10 MB" in too_big.json()["message"]
    gif = client.post(
        "/api/tasks/T-104/attachments", files={"file": ("a", b"GIF89a" + b"\0" * 20, "")}
    )
    assert gif.status_code == 201 and gif.json()["filename"] == "a.gif"


def test_uploading_needs_comment_rights(board: TestClient, login_as: LoginAs, ids: Ids) -> None:
    files = {"file": ("map.png", PNG, "image/png")}
    assert board.post("/api/tasks/T-104/attachments", files=files).status_code == 401
    editor = stl_editor(login_as, ids)
    assert editor.post("/api/tasks/T-130/attachments", files=files).status_code == 403


def test_images_are_only_served_to_people_who_see_the_task(
    login_as: LoginAs, ids: Ids, sample_database: Database
) -> None:
    editor = stl_editor(login_as, ids)
    url = upload(editor, "T-104")["url"]
    editor.post("/api/auth/logout")
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
    assert editor.get(f"/{url}").status_code == 401
    coatings = login_as("coatings", [(BuiltinRole.VIEWER, Scope.section(ids.sections["Coatings"]))])
    assert coatings.get(f"/{url}").status_code == 404
    assert coatings.get("/api/attachments/" + "0" * 32 + "/x.png").status_code == 404


def test_drafts_nobody_posted_are_cleaned_up(
    login_as: LoginAs, settings: Settings, sample_database: Database
) -> None:
    client = login_as("admin")
    old = upload(client, "T-104")
    with sample_database.session(write=True) as s:
        s.execute(
            update(Attachment)
            .where(Attachment.public_id == old["id"])
            .values(created_at=utcnow() - timedelta(days=2))
        )
    assert (settings.uploads_dir / old["id"]).exists()
    upload(client, "T-104")
    assert not (settings.uploads_dir / old["id"]).exists()
    assert client.get(f"/{old['url']}").status_code == 404


def test_deleting_posts_and_tasks_removes_their_files(
    login_as: LoginAs, settings: Settings
) -> None:
    client = login_as("admin")
    first = upload(client, "T-121")
    post = client.post("/api/tasks/T-121/posts", json={"body_md": first["markdown"]}).json()
    client.delete(f"/api/posts/{post['id']}")
    assert not (settings.uploads_dir / first["id"]).exists()

    second = upload(client, "T-121")
    client.post("/api/tasks/T-121/posts", json={"body_md": second["markdown"]})
    assert (settings.uploads_dir / second["id"]).exists()
    assert client.delete("/api/tasks/T-121").status_code == 204
    assert not (settings.uploads_dir / second["id"]).exists()
