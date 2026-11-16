import asyncio
from unittest.mock import patch

import pytest

from tests.test_web import account, client, material
from sau_web.worker import Worker
from sau_web.youtube_browser import youtube_video_url, browser_destination
from sau_web.youtube_browser import YouTubeBrowser
from sau_web.schemas import BrowserAction


@pytest.mark.parametrize(("url", "expected"), [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=abc&t=2", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://www.youtube.com/results?search_query=music", None),
    ("https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ", None),
    ("http://127.0.0.1/watch?v=dQw4w9WgXcQ", None),
])
def test_current_video_is_canonicalized_without_playlist(url, expected):
    assert youtube_video_url(url) == expected


def test_browser_search_keeps_keywords_on_youtube():
    assert browser_destination("旅行 vlog") == "https://www.youtube.com/results?search_query=%E6%97%85%E8%A1%8C+vlog"
    with pytest.raises(ValueError):
        browser_destination("http://127.0.0.1:8765")


def submission(accounts):
    return {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "request_key": "youtube-test-1234",
            "title": "旅行日记", "description": "一次旅行", "tags": ["旅行"], "account_ids": accounts}


def test_download_submission_is_idempotent_and_protects_selected_accounts(client):
    user = account(client)
    payload = submission([user["id"], user["id"]])
    first = client.post("/api/v2/youtube/downloads", json=payload)
    assert first.status_code == 202
    assert client.post("/api/v2/youtube/downloads", json=payload).json() == first.json()
    assert len(client.app_store.list(kind="download")) == 1
    payload["title"] = "另一条文案"
    assert client.post("/api/v2/youtube/downloads", json=payload).status_code == 409
    assert client.delete(f"/api/v2/accounts/{user['id']}").status_code == 409


@pytest.mark.parametrize("success", [True, False])
def test_only_successful_download_creates_one_publish_per_account(client, success):
    users = [account(client, 1), account(client, 2), account(client, 3), account(client, 4)]
    video = material(client)
    task_id = client.post("/api/v2/youtube/downloads", json=submission([u["id"] for u in users])).json()["id"]
    client.app_store.claim(task_id)

    class Download:
        def __init__(self, *args): pass
        def create_youtube_download_task(self, *args, **kwargs): return "local-download"
        def _process_youtube_download(self, *args): pass
        def get_youtube_task(self, *args):
            return {"status": "success" if success else "failed", "materialId": video["id"] if success else None,
                    "errorMessage": "下载失败"}

    with patch("sau_core.services.DownloadService", Download):
        worker = Worker(client.runtime_home, task_id)
        worker.download()
        worker.download()  # Replayed completion cannot enqueue duplicate publishing.
    jobs = client.app_store.list(kind="publish")
    assert len(jobs) == (4 if success else 0)
    if success:
        assert {j["account_id"] for j in jobs} == {u["id"] for u in users}
        assert all(j["material_id"] == video["id"] and j["parent_id"] == task_id for j in jobs)
        assert {j["payload"]["platform"]: j["payload"]["description"] for j in jobs} == {1:"一次旅行",2:"",3:"一次旅行",4:"一次旅行"}
        assert client.app_store.get(task_id)["status"] == "succeeded"
    else:
        assert client.app_store.get(task_id)["status"] == "failed"


def test_youtube_browser_requires_session_and_mutation_token(client):
    assert client.post("/api/v2/youtube/browser/start", headers={"X-SAU-Token": "wrong"}).status_code == 403
    client.cookies.clear()
    assert client.get("/api/v2/youtube/browser").status_code == 401


def test_browser_uses_saved_youtube_cookies_before_first_page_load(client):
    cookies = (
        "# Netscape HTTP Cookie File\n"
        "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t4102444800\tSID\tsaved-login\n"
        ".youtube.com\tTRUE\t/\tFALSE\t0\tSESSION\tsession-login\n"
        ".google.com\tTRUE\t/\tTRUE\t4102444800\tSID\tgoogle-login\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1\tEXPIRED\told-login\n"
        ".youtube.com.evil.test\tTRUE\t/\tTRUE\t4102444800\tOTHER\tunrelated\n"
    )
    response = client.post(
        "/api/v2/settings/youtube-cookie",
        files={"file": ("cookies.txt", cookies.encode(), "text/plain")},
    )
    assert response.status_code == 200
    browser = client.app.state.youtube_browser
    observed = {}

    async def offline_page(url):
        async def serve(route):
            observed["header"] = (await route.request.all_headers()).get("cookie", "")
            await route.fulfill(content_type="text/html", body="<title>Offline YouTube</title>")

        await browser.context.route("**/*", serve)
        await browser.page.goto(url)
        observed["cookies"] = await browser.context.cookies()

    browser._navigate = offline_page
    response = client.post("/api/v2/youtube/browser/start")
    assert response.status_code == 200, response.text
    assert response.json()["active"]
    assert "SID=saved-login" in observed["header"]
    assert "SESSION=session-login" in observed["header"]
    assert "google-login" not in observed["header"]
    actual = {(c["domain"], c["name"]): c for c in observed["cookies"]}
    assert set(actual) == {(".youtube.com", "SID"), (".youtube.com", "SESSION"), (".google.com", "SID")}
    assert actual[(".youtube.com", "SID")]["httpOnly"]
    assert actual[(".youtube.com", "SID")]["secure"]
    assert actual[(".youtube.com", "SESSION")]["expires"] == -1
    assert "saved-login" not in response.text


def test_invalid_saved_browser_cookies_report_cookie_error_without_exposing_values(client):
    response = client.post(
        "/api/v2/settings/youtube-cookie",
        files={"file": ("cookies.txt", b"# Netscape HTTP Cookie File\nsecret-invalid-cookie\n", "text/plain")},
    )
    assert response.status_code == 200
    browser = client.app.state.youtube_browser

    async def offline_page(url):
        await browser.context.route("**/*", lambda route: route.fulfill(body="offline"))
        await browser.page.goto(url)

    browser._navigate = offline_page
    response = client.post("/api/v2/youtube/browser/start")
    assert response.status_code == 400
    assert "Cookie" in response.json()["message"]
    assert "secret-invalid-cookie" not in response.text
    assert not client.get("/api/v2/youtube/browser").json()["active"]


def test_switching_browser_window_preserves_current_session_cookies(tmp_path):
    async def exercise():
        browser = YouTubeBrowser(tmp_path)
        observed = []

        async def offline_page(url):
            async def serve(route):
                observed.append((await route.request.all_headers()).get("cookie", ""))
                await route.fulfill(content_type="text/html", body="<title>Offline</title>")

            await browser.context.route("**/*", serve)
            await browser.page.goto(url)

        browser._navigate = offline_page
        real_start = browser.start

        async def start_without_window(proxy, **options):
            # Exercise the real window handoff with Chrome kept headless in tests.
            return await real_start(proxy, **{**options, "headed": False})

        try:
            await browser.start()
            await browser.context.add_cookies([{
                "name": "SID", "value": "current-session", "domain": ".youtube.com",
                "path": "/", "httpOnly": True, "secure": True,
            }])
            with patch.object(browser, "start", start_without_window):
                await browser.action(BrowserAction(kind="show"))
            assert "SID=current-session" in observed[-1]
        finally:
            await browser.close()

    asyncio.run(exercise())


def test_full_browser_navigation_and_keyboard_work_without_contacting_youtube(tmp_path):
    async def exercise():
        browser = YouTubeBrowser(tmp_path)

        async def local_page(url):
            await browser.context.route("**/*", lambda route: route.fulfill(
                content_type="text/html", body='''<!doctype html><meta charset="utf-8"><title>离线测试 - YouTube</title>
                <a style="position:absolute;left:0;top:0;width:200px;height:50px" href="https://www.youtube.com/watch?v=dQw4w9WgXcQ">测试视频</a>
                <input id="search" style="position:absolute;left:0;top:80px;width:300px;height:40px">'''))
            await browser.page.goto(url)

        browser._navigate = local_page
        try:
            state = await browser.start()
            assert state["active"] and state["image"].startswith("data:image/jpeg;base64,")
            assert state["video_url"] is None
            await browser.action(BrowserAction(kind="click", x=30, y=100))
            await browser.action(BrowserAction(kind="text", text="旅行 vlog"))
            assert await browser.page.locator("#search").input_value() == "旅行 vlog"
            await browser.action(BrowserAction(kind="click", x=30, y=20))
            await browser.page.wait_for_url("**/watch?v=*")
            assert (await browser.state())["video_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        finally:
            await browser.close()
        assert not (await browser.state())["active"]

    asyncio.run(exercise())
