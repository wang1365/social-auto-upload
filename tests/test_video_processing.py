import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sau_core.services as services
from myUtils.video_processor import normalize_video_processing_config, process_video


class VideoProcessingConfigTests(unittest.TestCase):
    def test_normalize_video_processing_config_clamps_and_orders_values(self):
        config = normalize_video_processing_config(
            {
                "trimHeadMin": 20,
                "trimHeadMax": -1,
                "speedMin": 3,
                "speedMax": 0.1,
                "cropPercentMin": 12,
                "cropPercentMax": 1,
                "frameDropStrength": 1,
                "maxConcurrent": 99,
                "hardwareMode": "bad",
            }
        )

        self.assertEqual(config["trimHeadMin"], 0)
        self.assertEqual(config["trimHeadMax"], 10)
        self.assertEqual(config["speedMin"], 0.5)
        self.assertEqual(config["speedMax"], 2)
        self.assertEqual(config["cropPercentMin"], 1)
        self.assertEqual(config["cropPercentMax"], 10)
        self.assertEqual(config["frameDropStrength"], 0.2)
        self.assertEqual(config["maxConcurrent"], 8)
        self.assertEqual(config["hardwareMode"], "cpu")

    def test_processing_service_saves_normalized_config(self):
        with isolated_runtime() as _base:
            payload = services.ProcessingService().save_settings(
                {"autoProcess": False, "maxConcurrent": 99, "hardwareMode": "gpu"}
            )

            self.assertFalse(payload["autoProcess"])
            self.assertEqual(payload["maxConcurrent"], 8)
            self.assertEqual(payload["hardwareMode"], "gpu")


class VideoProcessingStorageTests(unittest.TestCase):
    def test_create_material_record_stores_processed_metadata(self):
        with isolated_runtime() as _base:
            material_id = services.create_material_record(
                filename="demo.processed.mp4",
                filepath="demo.processed.mp4",
                filesize_mb=1.2,
                source_type="processed",
                material_type="processed",
                parent_file_id=7,
                display_tags=["已处理", "视频处理"],
                processing_profile="default-basic",
                processing_config={"speed": 1.01},
            )
            with services.db_connection() as conn:
                row = conn.execute("SELECT * FROM file_records WHERE id = ?", (material_id,)).fetchone()
            material = services.build_material_row(row)

            self.assertEqual(material["material_type"], "processed")
            self.assertEqual(material["parent_file_id"], 7)
            self.assertEqual(material["display_tags"], ["已处理", "视频处理"])
            self.assertEqual(json.loads(row["processing_config"]), {"speed": 1.01})


class VideoProcessorCommandTests(unittest.TestCase):
    def test_process_video_builds_ffmpeg_command(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "input.mp4"
            output_path = Path(tmp_dir) / "output.mp4"
            input_path.write_bytes(b"video")

            def fake_run(command, capture_output=True, text=True):
                class Result:
                    returncode = 0
                    stderr = ""
                    stdout = ""

                if "ffprobe" in command[0]:
                    Result.stdout = json.dumps(
                        {
                            "format": {"duration": "12.0"},
                            "streams": [
                                {"codec_type": "video", "width": 1920, "height": 1080},
                                {"codec_type": "audio"},
                            ],
                        }
                    )
                else:
                    output_path.write_bytes(b"processed")
                return Result()

            with patch("myUtils.video_processor.shutil.which") as mock_which, patch(
                "myUtils.video_processor.subprocess.run", side_effect=fake_run
            ) as mock_run:
                mock_which.side_effect = lambda name: f"C:/bin/{name}.exe" if name in {"ffmpeg", "ffprobe"} else None
                result = process_video(input_path, output_path, {}, seed=1)

            self.assertTrue(output_path.exists())
            self.assertEqual(result["profile"], "default-basic")
            ffmpeg_command = next(
                call.args[0]
                for call in mock_run.call_args_list
                if call.args[0][0].lower().endswith(("ffmpeg.exe", "ffmpeg"))
            )
            self.assertIn("-movflags", ffmpeg_command)
            self.assertIn("+faststart", ffmpeg_command)
            self.assertIn("libx264", ffmpeg_command)

    def test_process_video_requires_ffmpeg(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "input.mp4"
            input_path.write_bytes(b"video")
            with patch("myUtils.video_processor.shutil.which", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "ffmpeg is required"):
                    process_video(input_path, Path(tmp_dir) / "output.mp4", {})


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
