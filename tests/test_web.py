"""Web contract and task safety tests. All data and cookies are isolated."""

import json
import sqlite3
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from sau_core import services
from sau_web.app import create_app
from sau_web.runtime import Runtime
from sau_web.store import Store
from sau_web.worker import Worker


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key in ("DATABASE_PATH", "VIDEO_DIR", "COOKIE_DIR", "SYSTEM_COOKIE_DIR"):
        monkeypatch.setattr(services, key, getattr(services, key))
    app = create_app(tmp_path, start_workers=False)
    with TestClient(app) as browser:
        session = browser.get("/api/v2/session").json()
        browser.headers["X-SAU-Token"] = session["token"]
        browser.app_store = app.state.store
        browser.runtime_home = tmp_path
        yield browser


def material(client, filename="视频.mp4"):
    with patch("sau_web.app.shutil.which", return_value=None):
        response = client.post(
            "/api/v2/materials",
            files=[("files", (filename, b"example video content", "video/mp4"))],
        )
    assert response.status_code == 201, response.text
    return response.json()[0]


def account(client, platform=3):
    response = client.post(
        "/api/v2/accounts", json={"platform": platform, "name": "测试账号"}
    )
    assert response.status_code == 201, response.text
    result = response.json()
    with client.app_store.connect() as conn:
        conn.execute("UPDATE user_info SET status=1 WHERE id=?", (result["id"],))
    return result


def publish(client, media, user, key="test-submit-key"):
    return client.post(
        "/api/v2/publish-batches",
        json={
            "request_key": key,
            "items": [
                {
                    "material_id": media["id"],
                    "title": "逐条视频标题",
                    "description": "正文",
                    "tags": ["#测试", "测试"],
                }
            ],
            "account_ids": [user["id"]],
        },
    )


def test_migration_preserves_records_and_backup(tmp_path):
    database = tmp_path / "db" / "database.db"
    database.parent.mkdir()
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE user_info(id INTEGER PRIMARY KEY,type INTEGER,filePath TEXT,userName TEXT,status INTEGER)"
        )
        conn.execute("INSERT INTO user_info VALUES(17,3,'existing.json','已有账号',1)")
    store = Store(database)
    store.migrate()
    store.migrate()
    backups = list(database.parent.glob("database.pre-v2.*.db"))
    assert len(backups) == 1
    with store.connect() as conn:
        assert (
            conn.execute("SELECT userName FROM user_info WHERE id=17").fetchone()[0]
            == "已有账号"
        )
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("SELECT id FROM user_info").fetchone()[0] == 17


def test_session_origin_and_media_are_protected(client):
    with TestClient(client.app) as stranger:
        assert stranger.get("/api/v2/accounts").status_code == 401
        assert stranger.get("/api/v2/materials/1/video").status_code == 401
        assert (
            stranger.get(
                "/api/v2/session", headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert (
            stranger.get(
                "/api/v2/session", headers={"Sec-Fetch-Site": "cross-site"}
            ).status_code
            == 403
        )
    assert (
        client.post(
            "/api/v2/accounts",
            headers={"X-SAU-Token": "invalid"},
            json={"platform": 3, "name": "x"},
        ).status_code
        == 403
    )
    assert (
        client.get("/api/v2/health", headers={"Host": "evil.example"}).status_code
        == 400
    )


def test_import_range_subtitle_and_path_safety(client):
    row = material(client, "../../素材.mp4")
    assert row["filename"] == "素材.mp4"
    assert "file_path" not in row
    response = client.get(
        f"/api/v2/materials/{row['id']}/video", headers={"Range": "bytes=0-6"}
    )
    assert response.status_code == 206
    assert response.content == b"example"
    assert response.headers["content-range"].startswith("bytes 0-6/")
    assert client.get(f"/api/v2/materials/{row['id']}/subtitle").json() == {"text": ""}
    with client.app_store.connect() as conn:
        conn.execute(
            "UPDATE file_records SET file_path='../outside.mp4' WHERE id=?",
            (row["id"],),
        )
    assert client.get(f"/api/v2/materials/{row['id']}/video").status_code == 400


def test_upload_failure_leaves_no_material_or_temporary_files(client):
    response = client.post(
        "/api/v2/materials", files=[("files", ("empty.mp4", b"", "video/mp4"))]
    )
    assert response.status_code == 400
    assert client.get("/api/v2/materials").json()["total"] == 0
    assert not list((client.runtime_home / "videoFile").iterdir())
    response = client.post(
        "/api/v2/materials",
        files=[("files", ("executable.exe", b"invalid", "application/octet-stream"))],
    )
    assert response.status_code == 400


def test_batch_idempotency_granularity_and_resource_guards(client):
    media, user = material(client), account(client)
    first = publish(client, media, user)
    assert first.status_code == 202, first.text
    assert publish(client, media, user).json() == first.json()
    task = first.json()["tasks"][0]
    assert task["payload"]["tags"] == ["测试"]
    assert task["account_id"] == user["id"] and task["material_id"] == media["id"]
    assert client.delete(f"/api/v2/accounts/{user['id']}").status_code == 409
    assert client.delete(f"/api/v2/materials/{media['id']}").status_code == 409
    assert client.post(f"/api/v2/tasks/{task['id']}/cancel").status_code == 204
    assert client.delete(f"/api/v2/tasks/{task['id']}").status_code == 204
    assert client.get(f"/api/v2/materials/{media['id']}").status_code == 200
    assert client.delete(f"/api/v2/materials/{media['id']}").status_code == 204


def test_multiple_materials_accounts_and_incompatible_fields(client):
    media, media2, user, tencent = (
        material(client),
        material(client, "第二条.mp4"),
        account(client),
        account(client, 2),
    )
    body = {
        "request_key": "multiple-submit",
        "items": [
            {"material_id": row["id"], "title": row["filename"], "description": "正文"}
            for row in (media, media2)
        ],
        "account_ids": [user["id"], tencent["id"]],
    }
    response = client.post("/api/v2/publish-batches", json=body)
    assert response.status_code == 202, response.text
    tasks = response.json()["tasks"]
    assert len(tasks) == 4
    assert {t["payload"]["title"] for t in tasks} == {
        media["filename"],
        media2["filename"],
    }
    assert all(
        t["payload"]["description"] == ""
        for t in tasks
        if t["payload"]["platform"] == 2
    )
    body["items"][0]["title"] = "另一份内容"
    assert client.post("/api/v2/publish-batches", json=body).status_code == 409


def test_recovery_and_unknown_publishing_cannot_retry(client):
    media, user = material(client), account(client)
    task = publish(client, media, user).json()["tasks"][0]
    store = client.app_store
    assert store.claim(task["id"])
    download = store.create(
        "download", "测试下载", {"url": "https://youtu.be/test", "subtitles": False}
    )
    assert store.claim(download)
    store.recover()
    assert store.get(task["id"])["status"] == "unknown"
    assert store.get(download)["status"] == "interrupted"
    assert client.post(f"/api/v2/tasks/{task['id']}/retry").status_code == 409
    assert client.post(f"/api/v2/tasks/{download}/retry").status_code == 202
    assert client.post(f"/api/v2/tasks/{task['id']}/cancel").status_code == 409


@pytest.mark.parametrize("platform", [1, 2, 3, 4])
def test_publish_requires_positive_receipt(client, platform):
    media, user = material(client), account(client, platform)
    task = publish(client, media, user).json()["tasks"][0]
    client.app_store.claim(task["id"])

    class ConfirmedUploader:
        async def main(self):
            self.publish_attempted = True
            self.on_publish_attempt()
            self.publish_confirmed = True
            self.on_publish_confirmed()

    with (
        patch("sau_web.adapters.check", new=AsyncMock(return_value=True)),
        patch("sau_web.adapters.make_uploader", return_value=ConfirmedUploader()),
    ):
        Worker(client.runtime_home, task["id"]).run()
    assert client.app_store.get(task["id"])["status"] == "succeeded"


@pytest.mark.parametrize("attempted,expected", [(False, "failed"), (True, "unknown")])
def test_publish_errors_before_and_after_submission(client, attempted, expected):
    media, user = material(client), account(client)
    task = publish(client, media, user).json()["tasks"][0]
    client.app_store.claim(task["id"])

    class BrokenUploader:
        async def main(self):
            if attempted:
                self.publish_attempted = True
                self.on_publish_attempt()
            raise RuntimeError("模拟网络中断")

    with (
        patch("sau_web.adapters.check", new=AsyncMock(return_value=True)),
        patch("sau_web.adapters.make_uploader", return_value=BrokenUploader()),
    ):
        Worker(client.runtime_home, task["id"]).run()
    assert client.app_store.get(task["id"])["status"] == expected
    response = client.post(f"/api/v2/tasks/{task['id']}/retry")
    assert response.status_code == (409 if attempted else 202)


def test_login_qrcode_refresh_and_credentials_not_persisted_in_events(client):
    user = account(client)
    result = client.post(f"/api/v2/accounts/{user['id']}/login", json={"headed": False})
    task_id = result.json()["id"]
    client.app_store.claim(task_id)

    async def fake_login(platform, path, callback, headed):
        callback({"image_data_url": "data:image/png;base64,first"})
        callback({"image_data_url": "data:image/png;base64,second"})
        assert client.app_store.get(task_id)["result"]["qrcode"].endswith("second")
        path.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

    with patch("sau_web.adapters.login", side_effect=fake_login):
        Worker(client.runtime_home, task_id).run()
    assert client.app_store.get(task_id)["status"] == "succeeded"
    assert "qrcode" not in client.app_store.get(task_id)["result"]
    assert "base64" not in json.dumps(client.app_store.events())


def test_event_replay_is_ordered_and_snapshots_survive_new_store(client):
    store = client.app_store
    task_id = store.create("download", "event test", {"url": "url", "subtitles": True})
    cursor = store.latest_event()
    store.update(task_id, phase="下载中", progress=25)
    store.event(task_id, "log", {"message": "已下载 25%"})
    events = store.events(cursor)
    assert [e["event"] for e in events] == ["task", "log"]
    assert events[0]["id"] < events[1]["id"]
    assert Store(store.database).get(task_id)["progress"] == 25


def test_recovery_preserves_positive_publish_receipt(client):
    store = client.app_store
    task_id = store.create("publish", "confirmed before crash", {})
    store.claim(task_id)
    store.update(task_id, result={"confirmed": True, "attempted": True})
    store.recover()
    assert store.get(task_id)["status"] == "succeeded"


def test_retry_chain_prevents_republishing_after_nested_success(client):
    media, user = material(client), account(client)
    original = publish(client, media, user).json()["tasks"][0]
    store = client.app_store
    store.update(original["id"], status="failed")
    first = client.post(f"/api/v2/tasks/{original['id']}/retry").json()["id"]
    assert client.post(f"/api/v2/tasks/{original['id']}/retry").json()["id"] == first
    store.update(first, status="failed")
    second = client.post(f"/api/v2/tasks/{first}/retry").json()["id"]
    store.update(second, status="succeeded")
    assert client.post(f"/api/v2/tasks/{original['id']}/retry").status_code == 409
    assert client.delete(f"/api/v2/tasks/{second}").status_code == 204
    assert client.delete(f"/api/v2/tasks/{first}").status_code == 204
    assert client.post(f"/api/v2/tasks/{original['id']}/retry").status_code == 409


def test_real_worker_process_uses_isolated_home_and_finishes_check(client):
    user = account(client)
    task_id = client.post(f"/api/v2/accounts/{user['id']}/check").json()["id"]
    runtime = Runtime(client.runtime_home, client.app_store)
    try:
        runtime.tick()
        assert task_id in runtime.processes
        process = runtime.processes[task_id][0]
        process.wait(timeout=30)
        runtime.tick()
        task = client.app_store.get(task_id)
        assert task["status"] == "succeeded", task
        assert task["result"] == {"valid": False}
    finally:
        runtime.stop()
