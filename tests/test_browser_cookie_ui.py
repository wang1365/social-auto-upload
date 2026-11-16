"""Exercise the real browser extension with fake credentials and no platform traffic."""

import socket
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright, expect

from tests.test_web import client


@contextmanager
def local_server(app):
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    try:
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


def test_settings_guides_installation_when_browser_helper_is_missing(client):
    with local_server(client.app) as url, sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(url + "/settings")
            page.get_by_role("button", name="一键从当前浏览器导入", exact=True).click()
            dialog = page.get_by_role("dialog", name="安装浏览器助手", exact=True)
            expect(dialog).to_be_visible()
            expect(dialog.get_by_role("link", name="下载浏览器助手")).to_have_attribute(
                "href", "/api/v2/settings/browser-helper.zip")
            assert not (client.runtime_home / "cookiesFile/system/youtube_cookies.txt").exists()
            output = Path(__file__).resolve().parents[1] / ".cache/web-qa"
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output / "browser-helper-install.png"), full_page=True)
        finally:
            browser.close()


def test_real_extension_imports_current_profile_without_exporting_unrelated_cookies(client, tmp_path):
    extension = Path(__file__).resolve().parents[1] / "sau_web/browser_helper"
    with local_server(client.app) as url, sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(tmp_path / "test-browser-profile"), channel="chromium", headless=True,
            executable_path=os.environ.get("SAU_TEST_CHROMIUM_PATH"),
            args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"],
            viewport={"width": 1440, "height": 900},
        )
        try:
            # The cookie API needs no network request to Google or YouTube.
            context.route("**/*", lambda route: route.continue_()
                          if route.request.url.startswith(url + "/") else route.abort())
            context.add_cookies([
                {"domain": ".youtube.com", "path": "/", "name": "SID", "value": "current-profile-session", "httpOnly": True, "secure": True},
                {"domain": ".google.com", "path": "/", "name": "SID", "value": "google-profile-session", "secure": True},
                {"domain": ".example.com", "path": "/", "name": "PRIVATE", "value": "never-export-this"},
            ])
            page = context.pages[0]
            page.goto(url + "/settings")
            # A scripted request without a user click cannot read credentials.
            cdp = context.new_cdp_session(page)
            unsolicited = cdp.send("Runtime.evaluate", {"userGesture": False, "awaitPromise": True,
                "returnByValue": True, "expression": """new Promise((resolve, reject) => {
                const requestId = crypto.randomUUID();
                const timer = setTimeout(() => reject(new Error('helper did not respond')), 5000);
                const receive = event => {
                    if (event.data?.type !== 'SAU_BROWSER_HELPER_RESPONSE' || event.data.requestId !== requestId) return;
                    clearTimeout(timer); window.removeEventListener('message', receive); resolve(event.data);
                };
                window.addEventListener('message', receive);
                window.postMessage({type:'SAU_BROWSER_HELPER_IMPORT',requestId}, location.origin);
            })"""})["result"]["value"]
            assert unsolicited["ok"] is False and "cookies" not in unsolicited
            expect(page.get_by_role("button", name="一键从当前浏览器导入", exact=True)).to_be_visible()
            page.get_by_role("button", name="一键从当前浏览器导入", exact=True).click()
            expect(page.get_by_text("已从当前浏览器导入，关闭并重新启动 YouTube 浏览后生效", exact=True)).to_be_visible(timeout=15000)
            saved = client.runtime_home / "cookiesFile/system/youtube_cookies.txt"
            text = saved.read_text(encoding="utf-8")
            assert "current-profile-session" in text and "google-profile-session" in text
            assert "never-export-this" not in text and "example.com" not in text
            assert "#HttpOnly_.youtube.com" in text
            context.clear_cookies()
            page.get_by_role("button", name="一键从当前浏览器导入", exact=True).click()
            expect(page.get_by_text("当前浏览器中未找到有效的 YouTube 登录凭据，请先在同一浏览器登录 YouTube 再导入", exact=True)).to_be_visible()
            assert saved.read_text(encoding="utf-8") == text
            page.screenshot(path=str(Path(__file__).resolve().parents[1] / ".cache/web-qa/browser-helper-import.png"), full_page=True)
        finally:
            context.close()
