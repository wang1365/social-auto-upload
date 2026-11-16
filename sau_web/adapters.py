from __future__ import annotations

from utils.network import launch_browser_direct

import asyncio
import base64
import time
from pathlib import Path

PLATFORMS = {
    1: {"name": "小红书", "description": True, "tags": True},
    2: {"name": "视频号", "description": False, "tags": True},
    3: {"name": "抖音", "description": True, "tags": True},
    4: {"name": "快手", "description": True, "tags": True},
}


def modules():
    from uploader.douyin_uploader import main as douyin
    from uploader.ks_uploader import main as kuaishou
    from uploader.tencent_uploader import main as tencent
    from uploader.xiaohongshu_uploader import main as xhs

    return {1: xhs, 2: tencent, 3: douyin, 4: kuaishou}


async def check(platform: int, cookie: Path):
    if not cookie.is_file():
        return False
    return await asyncio.wait_for(
        modules()[platform].cookie_auth(str(cookie)), timeout=90
    )


async def login(platform: int, cookie: Path, callback, headed=False):
    module = modules()[platform]
    if platform == 2:
        # Keep the existing Video Accounts creator-site flow, but own the cookie path
        # and QR events here instead of inserting a second user_info row.
        from playwright.async_api import async_playwright
        from conf import LOCAL_CHROME_PATH

        async with async_playwright() as playwright:
            options = {"headless": not headed}
            if LOCAL_CHROME_PATH:
                options["executable_path"] = LOCAL_CHROME_PATH
            browser = await launch_browser_direct(playwright.chromium, **options)
            context = await browser.new_context()
            try:
                page = await context.new_page()
                await page.goto("https://channels.weixin.qq.com")
                previous = 0
                deadline = time.monotonic() + 300
                while time.monotonic() < deadline:
                    if page.url.startswith("https://channels.weixin.qq.com/platform/"):
                        await context.storage_state(path=str(cookie))
                        return
                    if time.monotonic() - previous > 20:
                        try:
                            image = (
                                page.frame_locator("iframe")
                                .first.get_by_role("img")
                                .first
                            )
                            data = await image.screenshot(timeout=5000)
                            callback(
                                {
                                    "image_data_url": "data:image/png;base64,"
                                    + base64.b64encode(data).decode()
                                }
                            )
                            previous = time.monotonic()
                        except Exception:
                            pass
                    await asyncio.sleep(2)
                raise TimeoutError("等待扫码超时，请重新登录或选择打开浏览器登录")
            finally:
                await context.close()
                await browser.close()
    else:
        # Resolve only the selected module's symbol.
        setup = getattr(
            module, {1: "xiaohongshu_setup", 3: "douyin_setup", 4: "ks_setup"}[platform]
        )
        result = await asyncio.wait_for(
            setup(
                str(cookie),
                handle=True,
                return_detail=True,
                qrcode_callback=callback,
                headless=not headed,
            ),
            timeout=420,
        )
        if not result.get("success"):
            raise RuntimeError(result.get("message") or "登录失败，请重试")


def make_uploader(platform, cookie, video, title, description, tags):
    module = modules()[platform]
    common = dict(
        title=title,
        file_path=str(video),
        tags=tags,
        publish_date=0,
        account_file=str(cookie),
    )
    if platform == 2:
        return module.TencentVideo(**common)
    uploader_type = {1: "XiaoHongShuVideo", 3: "DouYinVideo", 4: "KSVideo"}[platform]
    return getattr(module, uploader_type)(
        **common, desc=description, headless=True, debug=False
    )
