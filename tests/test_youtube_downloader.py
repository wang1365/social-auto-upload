import unittest
from pathlib import Path
from unittest.mock import patch

from myUtils.youtube_downloader import FALLBACK_FORMAT, PRIMARY_FORMAT, download_video


class YoutubeDownloaderTests(unittest.TestCase):
    def test_download_video_prefers_highest_quality_selector_first(self):
        calls: list[dict] = []
        existing_file = Path(__file__).resolve()

        class FakeYoutubeDL:
            def __init__(self, options):
                self.options = options
                calls.append(options)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def extract_info(self, url, download=False):
                return {
                    "ext": "mp4",
                    "requested_downloads": [{"filepath": str(existing_file)}],
                }

        with patch("myUtils.youtube_downloader.YoutubeDL", FakeYoutubeDL):
            final_path, subtitle_path = download_video(
                "https://www.youtube.com/watch?v=test123",
                Path("."),
                "sample",
                download_subtitles=False,
            )

        self.assertEqual(final_path, existing_file)
        self.assertIsNone(subtitle_path)
        self.assertEqual(calls[0]["format"], PRIMARY_FORMAT)
        self.assertEqual(FALLBACK_FORMAT, "bv*+ba/best")
