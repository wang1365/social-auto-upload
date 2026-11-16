"""Browser acceptance test against a real local server with isolated test data.

No workers are started, so queued publish/login tasks cannot contact platforms.
Screenshots are test artifacts under .cache/web-qa, never real account data.
"""

import socket
import base64
import json
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import uvicorn
from playwright.sync_api import sync_playwright, expect

from sau_core import services
from sau_web.app import create_app
from sau_web.runtime import configure
from sau_web.store import Store
from sau_web.worker import Worker


def test_browser_workflow_and_layout(tmp_path, monkeypatch):
    for key in ("DATABASE_PATH", "VIDEO_DIR", "COOKIE_DIR", "SYSTEM_COOKIE_DIR"):
        monkeypatch.setattr(services, key, getattr(services, key))
    configure(tmp_path)
    store = Store(services.DATABASE_PATH)
    store.migrate()
    services.ensure_runtime_schema()
    with store.connect() as conn:
        for platform, name in [
            (3, "拾光创作号"),
            (1, "生活记录号"),
            (4, "日常分享号"),
            (2, "品牌视频号"),
        ]:
            conn.execute(
                "INSERT INTO user_info(type,filePath,userName,status) VALUES(?,?,?,1)",
                (platform, f"test-{platform}.json", name),
            )
    # The video is generated locally, without downloaded media or credentials.
    source = tmp_path / "演示视频.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x354f77:s=640x360:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    imported = services.MaterialService().import_files(
        [source], custom_filename="创作日常：把想法变成作品"
    )
    services.MaterialService().import_files(
        [source], custom_filename="周末记录：生活中的小片刻"
    )
    preview_id = store.create(
        "preview", "生成测试预览", {"transcode": True}, material_id=imported[0]["id"]
    )
    store.claim(preview_id)
    Worker(tmp_path, preview_id).run()
    assert store.get(preview_id)["status"] == "succeeded"
    assert (tmp_path / "runtime" / "previews" / f"{imported[0]['id']}.mp4").is_file()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(tmp_path, start_workers=False),
            host="127.0.0.1",
            port=0,
            log_level="error",
        )
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    output = Path(__file__).resolve().parents[1] / ".cache" / "web-qa"
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 900}, locale="zh-CN"
            )
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}")
            expect(page.locator(".stat-card").first).to_contain_text("2")
            page.screenshot(path=str(output / "dashboard-1440.png"), full_page=True)
            for path, heading in [
                ("/materials", "素材库"),
                ("/accounts", "连接您的创作账号"),
                ("/downloads", "下载中心"),
                ("/settings", "按您的习惯工作"),
            ]:
                page.goto(f"http://127.0.0.1:{port}{path}")
                expect(
                    page.get_by_role("heading", name=heading, exact=True)
                ).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), path
            page.goto(f"http://127.0.0.1:{port}/publish")
            expect(
                page.get_by_role("button", name="开始发布", exact=True)
            ).to_be_disabled()
            page.get_by_role("button", name="选择素材", exact=True).click()
            dialog = page.get_by_role("dialog", name="选择视频素材")
            expect(dialog.locator(".el-table__body tr")).to_have_count(2)
            dialog.locator(".el-table__header .el-checkbox").click()
            dialog.get_by_role("button", name="确定选择").click()
            expect(page.locator(".selected-material")).to_have_count(2)
            expect(
                page.locator(".account-option-name strong").filter(
                    has_text="拾光创作号"
                )
            ).to_be_visible()
            page.locator(".account-option").filter(has_text="拾光创作号").locator(
                ".el-checkbox"
            ).click()
            page.locator(".account-option").filter(has_text="生活记录号").locator(
                ".el-checkbox"
            ).click()
            page.get_by_placeholder("为这条视频写一个标题").fill("第一条：我的创作日常")
            page.locator(".selected-material").nth(1).click()
            page.get_by_placeholder("为这条视频写一个标题").fill("第二条：周末生活记录")
            page.get_by_role("button", name="批量填充", exact=True).click()
            bulk = page.get_by_role("dialog", name="批量填充文案")
            bulk.get_by_placeholder("留空将清空已有正文").fill(
                "记录值得分享的每一个瞬间。"
            )
            bulk.get_by_placeholder("多个话题用中文或英文逗号分隔").fill(
                "生活记录，内容创作"
            )
            bulk.get_by_role("button", name="应用到 2 条素材").click()
            expect(page.locator(".publish-footer")).to_contain_text("4 条发布任务")
            page.reload()
            expect(page.locator(".selected-material")).to_have_count(2)
            expect(
                page.get_by_role("button", name="开始发布", exact=True)
            ).to_be_enabled()
            page.locator(".preview-stage video").evaluate(
                "video => video.play().then(() => video.pause())"
            )
            for width, height in [(1440, 900), (1280, 720), (1024, 768)]:
                page.set_viewport_size({"width": width, "height": height})
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), width
                expect(
                    page.get_by_role("button", name="开始发布", exact=True)
                ).to_be_in_viewport()
                page.screenshot(
                    path=str(output / f"publish-{width}.png"), full_page=True
                )
            page.set_viewport_size({"width": 1440, "height": 900})
            page.get_by_role("button", name="开始发布", exact=True).click()
            page.get_by_role("button", name="确定", exact=True).click()
            expect(page.locator(".task-table .el-table__body tr")).to_have_count(4)
            assert len(store.list(kind="publish")) == 4
            assert {t["payload"]["title"] for t in store.list(kind="publish")} == {
                "第一条：我的创作日常",
                "第二条：周末生活记录",
            }
            page.reload()
            page.get_by_role("button", name="发布记录").click()
            expect(page.locator(".task-table .el-table__body tr")).to_have_count(4)
            page.get_by_role("button", name="详情", exact=True).first.click()
            expect(page.get_by_text("任务详情", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="取消等待")).to_be_visible()
            page.keyboard.press("Escape")
            # Exercise the running-task stop UI through the real API, with a
            # simulated worker so no publishing process contacts a platform.
            stopping = store.list(kind="publish")[0]
            store.claim(stopping['id'])
            store.update(stopping['id'], phase='测试手动终止')
            runtime = server.config.app.state.runtime
            process = Mock()
            runtime.processes[stopping['id']] = (process, stopping, time.monotonic())
            expect(page.get_by_text('测试手动终止', exact=True)).to_be_visible()
            row = page.locator('.el-table__body tr').filter(has_text='测试手动终止')
            expect(row.get_by_role('button',name='终止',exact=True)).to_be_visible()
            row.get_by_role('button',name='详情',exact=True).click()
            with patch.object(runtime, '_stop_process') as stopper:
                page.get_by_role('button',name='终止任务',exact=True).click()
                page.get_by_role('button',name='确定',exact=True).click()
                expect(page.get_by_role('dialog', name='任务详情').get_by_text('已手动终止', exact=True)).to_be_visible()
                stopper.assert_called_once_with(process)
            assert store.get(stopping['id'])['status'] == 'cancelled'
            expect(page.get_by_role('button',name='终止任务',exact=True)).to_have_count(0)
            page.keyboard.press('Escape')
            # Render the real browser screen fixture inside the workspace. All
            # browsing endpoints are intercepted; no platform is contacted.
            frame = base64.b64encode(page.screenshot()).decode()
            browser_state = {"active": True, "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "YouTube 测试视频", "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "image": "data:image/png;base64," + frame, "width":1280,"height":800,"message":""}
            page.route("**/api/v2/youtube/browser**", lambda route: route.fulfill(content_type="application/json", body=json.dumps(browser_state)))
            page.goto(f"http://127.0.0.1:{port}/youtube")
            expect(page.get_by_role("heading", name="YouTube 浏览", exact=True)).to_be_attached()
            expect(page.get_by_label("YouTube 浏览器网页", exact=True)).to_be_visible()
            page.get_by_role("button", name="下载并发布", exact=True).click()
            publish_dialog = page.get_by_role("dialog", name="下载并发布到多个平台")
            expect(publish_dialog.get_by_role("button", name="确认下载并发布")).to_be_disabled()
            publish_dialog.locator(".el-checkbox").nth(0).click()
            publish_dialog.locator(".el-checkbox").nth(1).click()
            publish_dialog.get_by_role("button", name="确认下载并发布").click()
            expect(page.get_by_text("任务详情", exact=True)).to_be_visible()
            downloads = store.list(kind="download")
            assert len(downloads) == 1
            assert len(downloads[0]["payload"]["publish_jobs"]) == 2
            assert len(store.list(kind="publish")) == 4  # Download has not completed.
            page.keyboard.press("Escape")
            for width in (1440, 1024):
                page.set_viewport_size({"width":width,"height":900})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(output / f"youtube-{width}.png"), full_page=True)
            context.close()
            browser.close()
            assert not errors, errors
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


def test_youtube_live_player_audio_layout_and_translation_settings(tmp_path, monkeypatch):
    from tests.test_browser_media import SOURCE

    for key in ("DATABASE_PATH", "VIDEO_DIR", "COOKIE_DIR", "SYSTEM_COOKIE_DIR"):
        monkeypatch.setattr(services, key, getattr(services, key))
    app = create_app(tmp_path, start_workers=False)
    remote = app.state.youtube_browser

    async def navigate(url):
        await remote.page.route('**/*', lambda route: route.fulfill(content_type='text/html', body=SOURCE))
        await remote.page.goto(url)
    remote._navigate = navigate
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=0, log_level='error'))
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    thread = threading.Thread(target=server.run, kwargs={'sockets':[sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    output = Path(__file__).resolve().parents[1] / '.cache' / 'web-qa'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(viewport={'width':1440,'height':900})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{port}/youtube')
            page.get_by_role('button', name='启动 YouTube 浏览器').click()
            try:
                page.wait_for_function("document.querySelector('.youtube-video')?.getVideoPlaybackQuality().totalVideoFrames > 20", timeout=30000)
            except Exception:
                print('PLAYER_STATE', page.locator('.youtube-workspace').inner_text(), errors)
                page.screenshot(path=str(output/'youtube-player-failure.png'))
                raise
            video = page.locator('.youtube-video')
            assert video.evaluate("v=>v.srcObject.getAudioTracks().length") == 1
            # A real browser may enforce autoplay restrictions; explicit audio
            # enable must resume playback and preserve the received audio signal.
            if video.evaluate('v=>v.muted'):
                page.locator('.youtube-audio-prompt').click()
            assert video.evaluate('v=>!v.muted && !v.paused')
            page.evaluate('''() => {
                const audio=window.qaAudio=new AudioContext();
                const analyser=audio.createAnalyser();
                audio.createMediaStreamSource(document.querySelector('.youtube-video').srcObject).connect(analyser);
                const samples=new Float32Array(analyser.fftSize);window.qaEnergy=0;
                setInterval(()=>{analyser.getFloatTimeDomainData(samples);window.qaEnergy=Math.max(window.qaEnergy,...samples.map(Math.abs));},50);
                audio.resume();
            }''')
            page.wait_for_function('qaEnergy > 0.01', timeout=10000)
            for width, height in [(1440,900), (1280,720), (1024,768)]:
                page.set_viewport_size({'width':width,'height':height})
                expect(page.get_by_role('button',name='下载并发布',exact=True)).to_be_in_viewport()
                page.wait_for_function('''() => {
                    const box=document.querySelector('.youtube-surface').getBoundingClientRect();
                    return box.height > innerHeight * .75 && box.bottom < innerHeight;
                }''')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(output/f'youtube-live-{width}.png'))
            page.get_by_role('button',name='沉浸',exact=True).click()
            expect(page.locator('.youtube-workspace')).to_have_class('panel youtube-workspace immersive')
            assert page.locator('.youtube-workspace').bounding_box()['x'] == 0
            page.keyboard.press('Escape')
            expect(page.get_by_role('button',name='沉浸',exact=True)).to_be_visible()
            page.get_by_role('button',name='全屏',exact=True).click()
            page.wait_for_function('Boolean(document.fullscreenElement)')
            page.evaluate('document.exitFullscreen()')
            page.get_by_role('button',name='关闭浏览',exact=True).click()
            expect(page.get_by_role('button',name='启动 YouTube 浏览器')).to_be_visible()
            page.goto(f'http://127.0.0.1:{port}/settings')
            page.get_by_role('button',name='大模型与翻译',exact=True).click()
            switch = page.get_by_role('switch')
            expect(switch).to_be_checked()
            page.get_by_label('API 地址',exact=True).fill('http://127.0.0.1:11434/v1')
            page.get_by_label('模型名称',exact=True).fill('test-local-model')
            page.locator('.el-switch').click()
            page.get_by_role('button',name='保存设置',exact=True).click()
            expect(page.get_by_text('设置已保存',exact=True)).to_be_visible()
            page.reload()
            page.get_by_role('button',name='大模型与翻译',exact=True).click()
            expect(page.get_by_label('模型名称',exact=True)).to_have_value('test-local-model')
            expect(page.get_by_role('switch')).not_to_be_checked()
            page.screenshot(path=str(output/'translation-settings.png'), full_page=True)
            assert not errors, errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        sock.close()
