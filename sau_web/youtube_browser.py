"""A local Chrome session shown inside the web workspace; no remote page proxy."""
from __future__ import annotations

import asyncio
import base64
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlsplit

from playwright.async_api import Error as BrowserError, async_playwright


YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def load_browser_cookies(cookie_file):
    """Read Netscape cookies without exposing credential values in diagnostics."""
    try:
        lines = Path(cookie_file).read_text(encoding="utf-8-sig").splitlines()
        cookies = []
        for line in lines:
            http_only = line.startswith("#HttpOnly_")
            if not line.strip() or (line.startswith("#") and not http_only):
                continue
            if http_only:
                line = line[len("#HttpOnly_"):]
            domain, subdomains, path, secure, expiry, name, value = line.split("\t")
            host = domain.lstrip(".").lower()
            if not any(
                host == root or host.endswith("." + root)
                for root in ("youtube.com", "google.com")
            ):
                continue
            if (
                subdomains not in {"TRUE", "FALSE"}
                or secure not in {"TRUE", "FALSE"}
                or not path.startswith("/")
            ):
                raise ValueError()
            expires = int(expiry) if expiry else 0
            if expires > 0 and expires <= time.time():
                continue
            cookie = {
                "name": name,
                "value": value,
                "path": path,
                "domain": ("." if subdomains == "TRUE" else "") + host,
                "secure": secure == "TRUE",
                "httpOnly": http_only,
            }
            if expires > 0:
                cookie["expires"] = expires
            cookies.append(cookie)
    except (OSError, UnicodeError, ValueError):
        raise ValueError(
            "无法读取已保存的 YouTube Cookie，请在设置中重新导入有效的 Netscape Cookie 文件"
        ) from None
    if not cookies:
        raise ValueError("已保存的 Cookie 中没有未过期的 YouTube 或 Google 凭据，请重新导入")
    return cookies


def youtube_video_url(value: str) -> str | None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in YOUTUBE_HOSTS:
        return None
    parts = parsed.path.strip("/").split("/")
    video_id = None
    if parsed.hostname == "youtu.be":
        video_id = parts[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [None])[0]
    elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
        video_id = parts[1]
    if video_id and re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return "https://www.youtube.com/watch?v=" + video_id
    return None


def browser_destination(value: str) -> str:
    value = value.strip()
    if not value:
        return "https://www.youtube.com/"
    if "://" not in value:
        if value.startswith(("youtube.com/", "www.youtube.com/", "youtu.be/")):
            value = "https://" + value
        else:
            return "https://www.youtube.com/results?search_query=" + quote_plus(value)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in YOUTUBE_HOSTS or parsed.port not in {None, 443} or parsed.username:
        raise ValueError("请输入 YouTube 链接或搜索关键词")
    return value


class YouTubeBrowser:
    width, height = 1280, 800

    def __init__(self, home):
        self.home = home
        self.lock = asyncio.Lock()
        self.driver = self.context = self.page = None
        self.proxy = ""
        self.message = ""
        self.headed = False

    async def start(
        self, proxy="", *, cookies=None, headed=False, url="https://www.youtube.com/"
    ):
        async with self.lock:
            if self.context and self.page and not self.page.is_closed():
                return await self._state()
            if self.context:
                await self._close()
            self.proxy, self.headed = proxy, headed
            from conf import LOCAL_CHROME_PATH
            options = {"headless": not headed, "viewport": {"width": self.width, "height": self.height}}
            if LOCAL_CHROME_PATH:
                options["executable_path"] = LOCAL_CHROME_PATH
            else:
                options["channel"] = "chrome"
            if proxy:
                parsed = urlsplit(proxy)
                options["proxy"] = {"server": f"{parsed.scheme}://{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")}
                if parsed.username:
                    from urllib.parse import unquote
                    options["proxy"].update(username=unquote(parsed.username), password=unquote(parsed.password or ""))
            try:
                self.driver = await async_playwright().start()
                profile = self.home / "runtime" / "youtube-browser" / "profile"
                profile.mkdir(parents=True, exist_ok=True)
                self.context = await self.driver.chromium.launch_persistent_context(str(profile), **options)
                if cookies:
                    await self.context.add_cookies(cookies)
                self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
                self.context.on("page", self._select_page)
                await self._navigate(url)
            except Exception:
                await self._close()
                raise ValueError("无法启动 YouTube 浏览器，请确认本机已安装 Chrome，或关闭占用浏览会话的窗口") from None
            return await self._state()

    def _select_page(self, page):
        self.page = page

    async def _navigate(self, url):
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
            self.message = ""
        except BrowserError:
            self.message = "网页尚未加载完成，请检查网络或设置中的下载代理，然后刷新。"

    async def _state(self):
        if not self.page or self.page.is_closed():
            return {"active": False, "url": "", "title": "", "video_url": None, "image": "", "width": self.width, "height": self.height, "message": ""}
        image, title = "", ""
        try:
            title = (await self.page.title()).removesuffix(" - YouTube")
            image = "data:image/jpeg;base64," + base64.b64encode(await self.page.screenshot(type="jpeg", quality=65, timeout=5000)).decode()
        except BrowserError:
            pass  # A navigation in progress will supply the next frame.
        return {"active": True, "url": self.page.url, "title": title, "video_url": youtube_video_url(self.page.url), "image": image, "width": self.width, "height": self.height, "message": self.message}

    async def state(self):
        async with self.lock:
            return await self._state()

    async def action(self, action):
        if action.kind == "show":
            async with self.lock:
                url = (
                    self.page.url if self.page and not self.page.is_closed()
                    else "https://www.youtube.com/"
                )
                proxy = self.proxy
                cookies = await self.context.cookies() if self.context else []
            await self.close()
            return await self.start(proxy, cookies=cookies, headed=True, url=url)
        async with self.lock:
            if not self.page or self.page.is_closed():
                raise ValueError("请先启动 YouTube 浏览器")
            page = self.page
            try:
                if action.kind == "navigate":
                    await self._navigate(browser_destination(action.text))
                elif action.kind in {"back", "forward", "reload"}:
                    method = {"back": page.go_back, "forward": page.go_forward, "reload": page.reload}[action.kind]
                    await method(wait_until="domcontentloaded", timeout=15000)
                elif action.kind == "click":
                    await page.mouse.click(action.x, action.y, click_count=action.clicks)
                elif action.kind == "scroll":
                    await page.mouse.move(action.x, action.y)
                    await page.mouse.wheel(action.dx, action.dy)
                elif action.kind == "text":
                    await page.keyboard.insert_text(action.text)
                elif action.kind == "key":
                    await page.keyboard.press(action.text)
                self.message = ""
            except BrowserError:
                self.message = "页面正在切换或暂时无法操作，请稍后重试。"
            return await self._state()

    async def _close(self):
        try:
            if self.context:
                await self.context.close()
        finally:
            self.context = self.page = None
            if self.driver:
                await self.driver.stop()
                self.driver = None

    async def close(self):
        async with self.lock:
            await self._close()
