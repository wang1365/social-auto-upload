import os
import unittest


class DesktopSmokeTests(unittest.TestCase):
    def test_main_window_can_be_created(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from sau_desktop.main import MainWindow
        except ImportError as exc:
            self.skipTest(f"PySide6 is not installed: {exc}")

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        self.assertEqual(window.windowTitle(), "拾光分发 1.0")
        self.assertEqual(window.stack.count(), 7)
        window.close()
        app.processEvents()

    def test_settings_page_exposes_full_video_processing_payload(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from myUtils.video_processor import DEFAULT_VIDEO_PROCESSING_CONFIG
            from sau_desktop.main import SettingsPage
        except ImportError as exc:
            self.skipTest(f"PySide6 is not installed: {exc}")

        class FakeSettingsService:
            def __init__(self):
                self.saved = None

            def get_settings(self):
                return {
                    "downloadProxy": "",
                    "youtubeCookieFileName": "",
                    "videoProcessing": dict(DEFAULT_VIDEO_PROCESSING_CONFIG),
                }

            def save_settings(self, download_proxy="", video_processing=None):
                self.saved = video_processing
                return self.get_settings()

        app = QApplication.instance() or QApplication([])
        fake_settings = FakeSettingsService()
        from sau_desktop._shared import EventBus

        page = SettingsPage(fake_settings, object(), EventBus())

        payload = page._video_processing_payload()
        self.assertEqual(set(payload), set(DEFAULT_VIDEO_PROCESSING_CONFIG))
        page.trim_head_enabled.setChecked(False)
        page.trim_tail_enabled.setChecked(True)
        self.assertTrue(page._video_processing_payload()["trimEnabled"])
        page.trim_tail_enabled.setChecked(False)
        self.assertFalse(page._video_processing_payload()["trimEnabled"])

        page.reset_video_processing()
        self.assertEqual(fake_settings.saved, DEFAULT_VIDEO_PROCESSING_CONFIG)
        page.close()
        app.processEvents()

    def test_create_download_dialog_defaults_to_subtitle_download(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from sau_desktop.main import CreateDownloadDialog
        except ImportError as exc:
            self.skipTest(f"PySide6 is not installed: {exc}")

        app = QApplication.instance() or QApplication([])
        dialog = CreateDownloadDialog()
        dialog.url.setText(" https://www.youtube.com/watch?v=abc123 ")

        self.assertTrue(dialog.subtitles.isChecked())
        self.assertEqual(dialog.values(), ("https://www.youtube.com/watch?v=abc123", True))
        dialog.close()
        app.processEvents()

    def test_run_background_delivers_callbacks_on_gui_thread(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import QEventLoop, QThread, QTimer
            from PySide6.QtWidgets import QApplication, QWidget
            from sau_desktop._shared import run_background
        except ImportError as exc:
            self.skipTest(f"PySide6 is not installed: {exc}")

        app = QApplication.instance() or QApplication([])
        parent = QWidget()
        loop = QEventLoop()
        observed = {}

        def work():
            return QThread.currentThread()

        def on_done(worker_thread):
            observed["worker_thread"] = worker_thread
            observed["callback_thread"] = QThread.currentThread()
            observed["gui_thread"] = app.thread()
            loop.quit()

        run_background(parent, work, on_done=on_done)
        QTimer.singleShot(3000, loop.quit)
        loop.exec()

        self.assertIn("callback_thread", observed)
        self.assertIs(observed["callback_thread"], observed["gui_thread"])
        self.assertIsNot(observed["worker_thread"], observed["gui_thread"])
        parent.close()
        app.processEvents()

    def test_download_detail_dialog_displays_task_progress(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from sau_desktop.main import DownloadTaskDetailDialog
        except ImportError as exc:
            self.skipTest(f"PySide6 is not installed: {exc}")

        class FakeDownloadService:
            def get_youtube_task(self, task_id):
                return {
                    "taskId": task_id,
                    "status": "downloading",
                    "phase": "downloading",
                    "videoTitleZh": "中文标题",
                    "sourceUrl": "https://www.youtube.com/watch?v=abc123",
                    "filename": "",
                    "updatedAt": "2026-04-26 12:00:00",
                    "progressPercent": 42,
                    "progressText": "正在下载",
                    "speedText": "1 MB/s",
                    "etaText": "10s",
                    "videoDescription": "描述",
                    "errorDetail": "",
                    "filePath": "downloaded.mp4",
                    "processedFilePath": "processed.mp4",
                    "processedFilename": "processed.mp4",
                    "processingProgressText": "处理完成",
                }

        app = QApplication.instance() or QApplication([])
        dialog = DownloadTaskDetailDialog(FakeDownloadService(), "task-1")

        self.assertEqual(dialog.status.text(), "downloading")
        self.assertEqual(dialog.title.text(), "中文标题")
        self.assertEqual(dialog.progress.value(), 42)
        self.assertEqual(dialog.source_preview["source_url"], "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(dialog.local_preview["play_button"].isEnabled(), True)
        self.assertEqual(dialog.processed_preview["play_button"].isEnabled(), True)
        dialog.close()
        app.processEvents()

    def test_download_page_uses_compact_columns_and_keeps_task_payload(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QApplication
            from sau_desktop.main import DownloadPage
        except ImportError as exc:
            self.skipTest(f"PySide6 is not installed: {exc}")

        class FakeDownloadService:
            def list_youtube_tasks(self):
                return [
                    {
                        "taskId": "task-1",
                        "createdAt": "2026-04-26 12:00:00",
                        "progressPercent": 42,
                        "progressText": "正在下载",
                        "videoTitleZh": "中文标题",
                        "resolution": "1920x1080",
                        "fileSize": 12.345,
                    }
                ]

            def get_youtube_task(self, task_id):
                return self.list_youtube_tasks()[0]

        app = QApplication.instance() or QApplication([])
        from sau_desktop._shared import EventBus

        page = DownloadPage(FakeDownloadService(), EventBus())

        headers = [page.table.horizontalHeaderItem(index).text() for index in range(page.table.columnCount())]
        self.assertEqual(headers, ["", "下载时间", "下载进度", "标题", "分辨率", "文件大小"])
        self.assertEqual(page.table.item(0, 1).text(), "42%  正在下载")
        self.assertEqual(page.table.item(0, 3).text(), "1920x1080")
        self.assertEqual(page.table.item(0, 4).text(), "12.35 MB")
        self.assertEqual(page.table.item(0, 0).data(Qt.UserRole + 1)["taskId"], "task-1")
        page.close()
        app.processEvents()

    def test_publish_page_uses_checked_rows_for_selected_payload(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QApplication
            from sau_desktop._shared import EventBus
            from sau_desktop.pages.publish_page import PublishPage
            import sau_desktop.pages.publish_page as publish_page_module
        except ImportError as exc:
            self.skipTest(f"PySide6 is not installed: {exc}")

        class FakeMaterialService:
            def list_materials(self):
                return [{"filename": "demo.mp4", "source_type": "youtube", "file_path": "stored-demo.mp4"}]

        class FakeAccountService:
            def list_accounts(self):
                return [{"type": 4, "platform": "快手", "userName": "KS", "status": 1, "filePath": "ks.json"}]

        class FakePublishService:
            def __init__(self):
                self.payload = None

            def publish(self, payload):
                self.payload = payload

        app = QApplication.instance() or QApplication([])
        publish_service = FakePublishService()
        original_run_background = publish_page_module.run_background
        publish_page_module.run_background = lambda parent, fn, on_done=None, on_error=None: (
            fn(),
            on_done(None) if on_done else None,
        )
        try:
            page = PublishPage(FakeMaterialService(), FakeAccountService(), publish_service, EventBus())
            page.refresh()
            page.materials.item(0, 0).setCheckState(Qt.Checked)
            page.accounts.item(0, 0).setCheckState(Qt.Checked)
            page.title.setText("Title")
            page.tags.setText("#tag1, tag2")

            page.publish()

            self.assertEqual(publish_service.payload["fileList"], ["stored-demo.mp4"])
            self.assertEqual(publish_service.payload["accountList"], ["ks.json"])
            self.assertEqual(publish_service.payload["type"], 4)
            self.assertEqual(publish_service.payload["tags"], ["tag1", "tag2"])
            page.close()
            app.processEvents()
        finally:
            publish_page_module.run_background = original_run_background

    def test_publish_page_appends_builtin_topic_presets(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from sau_desktop._shared import EventBus
            from sau_desktop.pages.publish_page import PublishPage
        except ImportError as exc:
            self.skipTest(f"PySide6 is not installed: {exc}")

        class FakeMaterialService:
            def list_materials(self):
                return []

        class FakeAccountService:
            def list_accounts(self):
                return []

        app = QApplication.instance() or QApplication([])
        page = PublishPage(FakeMaterialService(), FakeAccountService(), object(), EventBus())
        page.tags.setText("#已有, AI")
        page.topic_preset.setCurrentText("AI / 自动化")

        page.add_topic_preset()

        self.assertEqual(page._parse_tags(), ["已有", "AI", "自动化", "效率工具", "副业", "内容创作"])
        page.close()
        app.processEvents()

    def test_account_login_dialog_starts_login_and_handles_success(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication, QDialog
            from sau_desktop.main import AccountLoginDialog
        except ImportError as exc:
            self.skipTest(f"PySide6 is not installed: {exc}")

        class FakeAccountService:
            def __init__(self):
                self.calls = []

            def start_login(self, platform_type, account_id, callback=None):
                self.calls.append((platform_type, account_id))
                if callback:
                    callback({"message": "200"})

        app = QApplication.instance() or QApplication([])
        service = FakeAccountService()
        dialog = AccountLoginDialog(service)
        dialog.username.setText("creator")
        dialog.start_login()

        self.assertEqual(service.calls, [(1, "creator")])
        self.assertEqual(dialog.result(), QDialog.Accepted)
        dialog.close()
        app.processEvents()

    def test_account_page_lists_all_platform_accounts(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from sau_desktop.main import AccountPage
        except ImportError as exc:
            self.skipTest(f"PySide6 is not installed: {exc}")

        class FakeAccountService:
            def list_accounts(self):
                return [
                    {"id": 4, "platform": "快手", "userName": "KS", "filePath": "ks.json", "status": 1},
                    {"id": 2, "platform": "小红书", "userName": "Redbook", "filePath": "xhs.json", "status": 1},
                    {"id": 1, "platform": "抖音", "userName": "Douyin", "filePath": "dy.json", "status": 1},
                ]

        app = QApplication.instance() or QApplication([])
        from sau_desktop._shared import EventBus

        page = AccountPage(FakeAccountService(), EventBus())
        page.refresh()

        self.assertEqual(page.table.rowCount(), 3)
        platforms = [page.table.item(row, 1).text() for row in range(page.table.rowCount())]
        self.assertEqual(platforms, ["快手", "小红书", "抖音"])
        page.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
