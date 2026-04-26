import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sau_core.services as services
from myUtils.video_processor import normalize_video_processing_config


class ServiceLayerTests(unittest.TestCase):
    def test_settings_service_validates_proxy_and_cookie(self):
        with isolated_runtime() as base:
            settings = services.SettingsService()
            saved = settings.save_settings("http://127.0.0.1:7890", {"maxConcurrent": 99})
            self.assertEqual(saved["downloadProxy"], "http://127.0.0.1:7890")
            self.assertEqual(saved["videoProcessing"]["maxConcurrent"], 8)

            cookie_path = base / "cookies.txt"
            cookie_path.write_text(
                "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t0\tSID\tvalue\n",
                encoding="utf-8",
            )
            uploaded = settings.upload_youtube_cookie(cookie_path)
            self.assertTrue(uploaded["youtubeCookieConfigured"])
            self.assertEqual(uploaded["youtubeCookieFileName"], "youtube_cookies.txt")

            cleared = settings.clear_youtube_cookie()
            self.assertFalse(cleared["youtubeCookieConfigured"])

    def test_video_processing_config_accepts_legacy_setting_keys(self):
        config = normalize_video_processing_config(
            {
                "enableTrimHead": False,
                "enableTrimTail": True,
                "enableSpeed": False,
                "enableCrop": False,
                "trimHeadMin": 2,
                "trimHeadMax": 1,
            }
        )

        self.assertTrue(config["trimEnabled"])
        self.assertFalse(config["speedEnabled"])
        self.assertFalse(config["cropEnabled"])
        self.assertEqual(config["trimHeadMin"], 1)
        self.assertEqual(config["trimHeadMax"], 2)

    def test_material_service_imports_and_deletes_files(self):
        with isolated_runtime() as base:
            source = base / "source.mp4"
            source.write_bytes(b"video")
            material_service = services.MaterialService()

            imported = material_service.import_files([source], custom_filename="demo")
            self.assertEqual(imported[0]["filename"], "demo.mp4")
            materials = material_service.list_materials()
            self.assertEqual(len(materials), 1)
            stored_path = material_service.resolve_material_path(materials[0]["file_path"])
            self.assertTrue(stored_path.exists())

            deleted = material_service.delete_material(materials[0]["id"])
            self.assertEqual(deleted["filename"], "demo.mp4")
            self.assertFalse(stored_path.exists())

    def test_account_service_lists_and_deletes_cookie(self):
        with isolated_runtime() as _base:
            services.COOKIE_DIR.mkdir(parents=True, exist_ok=True)
            cookie_path = services.COOKIE_DIR / "account.json"
            cookie_path.write_text("{}", encoding="utf-8")
            with services.db_connection() as conn:
                conn.execute(
                    "INSERT INTO user_info (type, filePath, userName, status) VALUES (?, ?, ?, ?)",
                    (3, "account.json", "creator", 1),
                )
                conn.commit()

            account_service = services.AccountService()
            accounts = account_service.list_accounts()
            self.assertEqual(accounts[0]["platform"], "抖音")
            account_service.delete_account(accounts[0]["id"])
            self.assertFalse(cookie_path.exists())
            self.assertEqual(account_service.list_accounts(), [])

    def test_download_service_rejects_playlist_url(self):
        with isolated_runtime() as _base:
            download_service = services.DownloadService()
            with self.assertRaises(services.ServiceError):
                download_service.create_youtube_download_task(
                    "https://www.youtube.com/playlist?list=PL123",
                    callback=None,
                )

    def test_publish_service_dispatches_platform(self):
        publish_service = services.PublishService()
        with patch("sau_core.services.post_video_DouYin") as post_douyin:
            publish_service.publish(
                {
                    "type": 3,
                    "fileList": ["demo.mp4"],
                    "accountList": ["creator"],
                    "title": "标题",
                    "tags": ["tag"],
                }
            )
        post_douyin.assert_called_once()


class isolated_runtime:
    def __enter__(self):
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.original_db = services.DATABASE_PATH
        self.original_video_dir = services.VIDEO_DIR
        self.original_cookie_dir = services.COOKIE_DIR
        self.original_system_cookie_dir = services.SYSTEM_COOKIE_DIR
        base = Path(self.tmp_dir.name)
        services.DATABASE_PATH = base / "db" / "database.db"
        services.VIDEO_DIR = base / "videoFile"
        services.COOKIE_DIR = base / "cookiesFile"
        services.SYSTEM_COOKIE_DIR = services.COOKIE_DIR / "system"
        services.ensure_runtime_schema()
        return base

    def __exit__(self, exc_type, exc, tb):
        services.DATABASE_PATH = self.original_db
        services.VIDEO_DIR = self.original_video_dir
        services.COOKIE_DIR = self.original_cookie_dir
        services.SYSTEM_COOKIE_DIR = self.original_system_cookie_dir
        self.tmp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
