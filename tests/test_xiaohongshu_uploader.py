import asyncio
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from patchright.async_api import Error as BrowserError

import uploader.xiaohongshu_uploader.main as xhs_main


class FakeLocator:
    def __init__(self, name, count=0, src=None, children=None):
        self.name = name
        self.url = xhs_main.XHS_LOGIN_URL
        self._count = count
        self._src = src
        self._children = children or {}

    @property
    def first(self):
        return self

    def locator(self, selector):
        return self._children.get(selector, FakeLocator(selector))

    def get_by_text(self, text, exact=False):
        return self._children.get(f"text:{text}", FakeLocator(text))

    def filter(self, **kwargs):
        return self

    def nth(self, index):
        return self

    async def count(self):
        return self._count

    async def wait_for(self, **kwargs):
        return None

    async def get_attribute(self, name):
        if name == "src":
            return self._src
        return None

    async def fill(self, value):
        return None

    async def click(self):
        return None


class RecordingKeyboard:
    def __init__(self):
        self.actions = []

    async def press(self, key):
        self.actions.append(("press", key))

    async def type(self, text, delay=None):
        self.actions.append(("type", text, delay))


class RecordingLocator(FakeLocator):
    def __init__(self, name):
        super().__init__(name, count=1)
        self.actions = []

    async def fill(self, value):
        self.actions.append(("fill", value))

    async def click(self):
        self.actions.append(("click",))

    async def wait_for(self, **kwargs):
        self.actions.append(("wait_for", kwargs))


class RecordingPage:
    def __init__(self):
        self.keyboard = RecordingKeyboard()
        self.locators = {
            'input[placeholder*="填写标题"]': RecordingLocator("title"),
            'p[data-placeholder*="输入正文描述"]': RecordingLocator("desc"),
            '#creator-editor-topic-container': RecordingLocator("topic-container"),
            '#creator-editor-topic-container .item': RecordingLocator("topic-item"),
        }

    def locator(self, selector):
        return self.locators[selector]


class XiaohongshuUploaderTests(unittest.TestCase):
    def qrcode_page(self, qrcode_locator):
        scan_text = FakeLocator(
            "scan-text", count=1,
            children={"xpath=..//following-sibling::div//img": qrcode_locator},
        )
        login_box = FakeLocator(
            "login-box", count=1,
            children={
                "div:has-text('扫一扫')": scan_text,
                "text:APP扫一扫登录": scan_text,
            },
        )
        page = FakeLocator("page", children={
            "div[class*='login-box']": login_box,
            ".login-box-container": login_box,
        })
        page.url = xhs_main.XHS_LOGIN_URL
        page.wait_for_load_state = AsyncMock()
        return page, scan_text

    def test_qrcode_is_delivered_after_login_page_navigation(self):
        image = b"test-qr-image"
        src = "data:image/png;base64," + base64.b64encode(image).decode()
        page, scan_text = self.qrcode_page(FakeLocator("qrcode", count=1, src=src))
        scan_text.count = AsyncMock(side_effect=[
            BrowserError("Locator.count: Execution context was destroyed, most likely because of a navigation."),
            1,
        ])
        received = []
        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
            xhs_main, "decode_qrcode_from_path", return_value=None
        ):
            result = asyncio.run(xhs_main._save_xhs_qrcode(
                page, str(Path(tmp_dir) / "account.json"), qrcode_callback=received.append
            ))
            self.assertEqual(Path(result["image_path"]).read_bytes(), image)
            self.assertEqual(received[0]["image_data_url"], src)

    def test_qrcode_waits_for_image_instead_of_failing_before_it_mounts(self):
        src = "data:image/png;base64," + base64.b64encode(b"qr").decode()
        page, _ = self.qrcode_page(FakeLocator("qrcode", count=0, src=src))
        received = []
        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
            xhs_main, "decode_qrcode_from_path", return_value=None
        ):
            asyncio.run(xhs_main._save_xhs_qrcode(
                page, str(Path(tmp_dir) / "account.json"), qrcode_callback=received.append
            ))
        self.assertEqual(received[0]["image_data_url"], src)

    def test_remote_qrcode_image_is_delivered_as_local_image_data(self):
        locator = FakeLocator("qrcode", count=1, src="https://example.invalid/qr.png")
        async def screenshot(*, path):
            Path(path).write_bytes(b"qr-image")
        locator.screenshot = screenshot
        page, _ = self.qrcode_page(locator)
        received = []
        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
            xhs_main, "decode_qrcode_from_path", return_value=None
        ):
            asyncio.run(xhs_main._save_xhs_qrcode(
                page, str(Path(tmp_dir) / "account.json"), qrcode_callback=received.append
            ))
        self.assertEqual(received[0]["image_data_url"], "data:image/png;base64,cXItaW1hZ2U=")

    def test_platform_network_restriction_is_reported_instead_of_missing_qrcode(self):
        page, _ = self.qrcode_page(FakeLocator("qrcode"))
        page.url = "https://creator.xiaohongshu.com/website-login/error?code=300012"
        body = FakeLocator("body")
        body.inner_text = AsyncMock(return_value="安全限制\n当前网络存在风险，请切换可靠网络后重试\n300012")
        page._children["body"] = body
        with self.assertRaisesRegex(RuntimeError, "网络.*300012"):
            asyncio.run(xhs_main._find_xhs_qrcode_locator(page))

    def test_login_poll_keeps_waiting_when_navigation_destroys_context(self):
        page, _ = self.qrcode_page(FakeLocator("qrcode"))
        page.url = "https://creator.xiaohongshu.com/"
        page._children[xhs_main.XHS_LOGIN_BOX_SELECTOR].count = AsyncMock(
            side_effect=BrowserError("Execution context was destroyed, most likely because of a navigation.")
        )
        self.assertFalse(asyncio.run(xhs_main._is_xhs_login_completed(page)))

    def test_find_xhs_qrcode_locator_prefers_scan_sibling_inside_login_box(self):
        qrcode_locator = FakeLocator("qrcode", count=1, src="data:image/png;base64,abc")
        scan_text_locator = FakeLocator(
            "scan-text",
            count=1,
            children={
                "xpath=..//following-sibling::div//img": qrcode_locator,
            },
        )
        login_box_locator = FakeLocator(
            "login-box",
            count=1,
            children={
                "div:has-text('扫一扫')": scan_text_locator,
                "text:APP扫一扫登录": scan_text_locator,
            },
        )
        page = FakeLocator(
            "page",
            children={
                "div[class*='login-box']": login_box_locator,
                ".login-box-container": login_box_locator,
            },
        )

        locator = asyncio.run(xhs_main._find_xhs_qrcode_locator(page))
        self.assertIs(locator, qrcode_locator)

    def test_setup_returns_detail_when_cookie_invalid_without_handle(self):
        with patch("uploader.xiaohongshu_uploader.main.os.path.exists", return_value=False):
            result = asyncio.run(
                xhs_main.xiaohongshu_setup(
                    "missing.json",
                    handle=False,
                    return_detail=True,
                )
            )
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "cookie_invalid")

    def test_setup_uses_login_flow_when_handle_is_true(self):
        login_result = {
            "success": True,
            "status": "success",
            "message": "ok",
            "account_file": "account.json",
            "qrcode": {"image_path": "qrcode.png"},
            "current_url": "https://creator.xiaohongshu.com/",
        }
        with patch("uploader.xiaohongshu_uploader.main.os.path.exists", return_value=False):
            with patch(
                "uploader.xiaohongshu_uploader.main.xiaohongshu_cookie_gen",
                new=AsyncMock(return_value=login_result),
            ) as mock_login:
                result = asyncio.run(
                    xhs_main.xiaohongshu_setup(
                        "account.json",
                        handle=True,
                        return_detail=True,
                    )
                )
        self.assertTrue(result["success"])
        mock_login.assert_awaited_once()

    def test_video_validate_upload_args_normalizes_video_and_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            thumbnail_path = Path(tmp_dir) / "demo.png"
            cookie_path = Path(tmp_dir) / "account.json"
            video_path.write_bytes(b"video")
            thumbnail_path.write_bytes(b"image")
            cookie_path.write_text("{}")

            app = xhs_main.XiaoHongShuVideo(
                title="demo",
                file_path=str(video_path),
                tags=["xhs"],
                publish_date=0,
                account_file=str(cookie_path),
                thumbnail_path=str(thumbnail_path),
            )

            with patch(
                "uploader.xiaohongshu_uploader.main.cookie_auth",
                new=AsyncMock(return_value=True),
            ):
                asyncio.run(app.validate_upload_args())

        self.assertTrue(app.file_path.endswith("demo.mp4"))
        self.assertTrue(app.thumbnail_path.endswith("demo.png"))

    def test_note_uploader_exists_and_validates_required_fields(self):
        note_cls = getattr(xhs_main, "XiaoHongShuNote")
        app = note_cls(
            image_paths=[],
            note="",
            tags=[],
            publish_date=0,
            account_file="account.json",
        )

        with patch.object(app, "validate_base_args", new=AsyncMock(return_value=None)):
            with self.assertRaises(ValueError):
                asyncio.run(app.validate_upload_args())

    def test_video_fill_meta_uses_desc_then_first_tag(self):
        app = xhs_main.XiaoHongShuVideo(
            title="标题内容",
            file_path="demo.mp4",
            tags=["话题1"],
            publish_date=0,
            account_file="account.json",
            desc="描述内容",
        )
        page = RecordingPage()

        asyncio.run(app.fill_meta(page))

        self.assertEqual(
            page.locators['input[placeholder*="填写标题"]'].actions,
            [("fill", "标题内容")],
        )
        self.assertEqual(
            page.locators['p[data-placeholder*="输入正文描述"]'].actions,
            [("click",)],
        )
        self.assertIn(("type", "描述内容", None), page.keyboard.actions)
        self.assertIn(("type", "#话题1", 30), page.keyboard.actions)
        self.assertEqual(
            page.locators['#creator-editor-topic-container .item'].actions,
            [("wait_for", {"state": "visible", "timeout": 2000}), ("click",)],
        )

    def test_video_fill_meta_can_fill_first_tag_without_desc(self):
        app = xhs_main.XiaoHongShuVideo(
            title="标题内容",
            file_path="demo.mp4",
            tags=["话题1"],
            publish_date=0,
            account_file="account.json",
        )
        page = RecordingPage()

        asyncio.run(app.fill_meta(page))

        self.assertEqual(
            page.locators['p[data-placeholder*="输入正文描述"]'].actions,
            [("click",)],
        )
        self.assertNotIn(("type", "", None), page.keyboard.actions)
        self.assertIn(("type", "#话题1", 30), page.keyboard.actions)

    def test_note_title_defaults_do_not_override_explicit_title(self):
        app = xhs_main.XiaoHongShuNote(
            image_paths=["a.png"],
            note="正文",
            tags=[],
            publish_date=0,
            account_file="account.json",
            title="显式标题",
            desc="图文正文",
        )

        self.assertEqual(app.title, "显式标题")
        self.assertEqual(app.desc, "图文正文")


if __name__ == "__main__":
    unittest.main()
