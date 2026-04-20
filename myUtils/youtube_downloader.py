import re
import logging
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ytdlp_logger = logging.getLogger('yt-dlp')


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


def sanitize_filename(name: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "")
    sanitized = sanitized.strip().strip(".")
    return sanitized[:180] or "youtube_video"


def is_supported_youtube_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in YOUTUBE_HOSTS


def is_playlist_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query)
    if parsed.netloc.lower() == "youtu.be":
        return False
    if parsed.path == "/playlist":
        return True
    return "list" in query and "v" not in query


def is_valid_proxy_url(proxy: str) -> bool:
    if not proxy:
        return True
    try:
        parsed = urlparse(proxy.strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https", "socks5", "socks5h"}:
        return False
    return bool(parsed.hostname and parsed.port)


def classify_ytdlp_error(error: Exception) -> tuple[str, str, str]:
    detail = str(error).strip() or error.__class__.__name__
    lowered = detail.lower()

    if "cookie" in lowered and ("does not look like a netscape format cookies file" in lowered or "invalid cookie" in lowered):
        return "youtube_cookie_invalid", "YouTube cookie file is invalid", detail
    if "cookie" in lowered and ("not found" in lowered or "no such file" in lowered):
        return "youtube_cookie_missing", "YouTube cookie file is missing", detail
    if "cookie" in lowered and ("expired" in lowered or "sign in" in lowered or "login" in lowered):
        return "youtube_cookie_expired", "YouTube cookie may be expired or invalid", detail
    if "proxy" in lowered and ("unknown url type" in lowered or "invalid" in lowered):
        return "proxy_invalid", "Proxy format is invalid", detail
    if "proxy" in lowered and ("407" in lowered or "auth" in lowered or "authentication" in lowered):
        return "proxy_auth_failed", "Proxy authentication failed", detail
    if "proxy" in lowered and (
        "connection refused" in lowered
        or "failed to establish" in lowered
        or "cannot connect" in lowered
        or "timed out" in lowered
        or "timeout" in lowered
    ):
        return "proxy_connect_failed", "Proxy connection failed", detail
    if "unsupported url" in lowered or "not a valid url" in lowered:
        return "invalid_url", "URL is invalid or unsupported", detail
    if "playlist" in lowered:
        return "playlist_not_supported", "Playlist URLs are not supported", detail
    if "video unavailable" in lowered or "private video" in lowered:
        return "video_unavailable", "Video is unavailable or has been removed", detail
    if "sign in to confirm your age" in lowered or "age-restricted" in lowered:
        return "age_restricted", "Video is age restricted", detail
    if "country" in lowered or "region" in lowered or "geo" in lowered:
        return "region_restricted", "Video is region restricted", detail
    if "copyright" in lowered:
        return "copyright_restricted", "Video is copyright restricted", detail
    if "timed out" in lowered or "timeout" in lowered:
        return "network_timeout", "Download timed out", detail
    if "unable to download webpage" in lowered or "http error" in lowered:
        return "network_error", "Network request failed", detail
    if "requested format is not available" in lowered:
        return "format_unavailable", "No supported media format is available", detail
    if "permission denied" in lowered or "no space left" in lowered:
        return "file_write_failed", "Local file write failed", detail
    if "metadata" in lowered or "extractor" in lowered:
        return "metadata_extract_failed", "Metadata extraction failed", detail
    return "download_failed", "Video download failed", detail


def build_ytdlp_options(proxy: str | None = None, cookiefile: str | None = None, **kwargs) -> dict:
    options = dict(kwargs)
    if proxy:
        options["proxy"] = proxy
    if cookiefile:
        options["cookiefile"] = cookiefile
    return options


PRIMARY_FORMAT = (
    "bestvideo*[ext=mp4]+bestaudio[ext=m4a]/"
    "bestvideo*[ext=mp4]+bestaudio/"
    "bestvideo*+bestaudio[ext=m4a]/"
    "bestvideo*+bestaudio/"
    "best*[ext=mp4][vcodec!=none][acodec!=none]/"
    "best*[vcodec!=none][acodec!=none]"
)

FALLBACK_FORMAT = "bv*+ba/best"


def pick_best_subtitle_language(available_languages: list[str]) -> str | None:
    if not available_languages:
        return None
    normalized = [lang for lang in available_languages if lang and lang != "live_chat"]
    if not normalized:
        return None

    preferred_exact = ["zh-Hans", "zh-CN", "zh", "en-US", "en-GB", "en"]
    for candidate in preferred_exact:
        if candidate in normalized:
            return candidate
    for candidate in normalized:
        if candidate.lower().startswith("zh"):
            return candidate
    for candidate in normalized:
        if candidate.lower().startswith("en"):
            return candidate
    return normalized[0]


def extract_video_metadata(url: str, proxy: str | None = None, cookiefile: str | None = None) -> dict:
    options = build_ytdlp_options(
        proxy,
        cookiefile=cookiefile,
        quiet=True,
        skip_download=True,
        noplaylist=True,
    )
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    if isinstance(info, dict) and info.get("entries"):
        raise DownloadError("playlist is not supported")
    if not isinstance(info, dict):
        raise DownloadError("metadata extract failed")
    return {
        "title": info.get("title") or "",
        "description": info.get("description") or "",
        "id": info.get("id") or "",
        "ext": info.get("ext") or "mp4",
    }


def download_video(
    url: str,
    output_dir: Path,
    filename_stem: str,
    progress_callback=None,
    proxy: str | None = None,
    cookiefile: str | None = None,
    download_subtitles: bool = True,
) -> tuple[Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir / f"{filename_stem}.%(ext)s")

    def progress_hook(status: dict):
        if progress_callback:
            progress_callback(status)

    def find_downloaded_file(result: dict | None) -> Path | None:
        final_path = None
        if isinstance(result, dict):
            requested = result.get("requested_downloads") or []
            if requested:
                filepath = requested[0].get("filepath")
                if filepath:
                    final_path = Path(filepath)
            if final_path is None:
                ext = result.get("ext") or "mp4"
                candidate = output_dir / f"{filename_stem}.{ext}"
                if candidate.exists():
                    final_path = candidate

        if final_path is None or not final_path.exists():
            matches = sorted(
                (path for path in output_dir.glob(f"{filename_stem}.*") if ".f" not in "".join(path.suffixes)),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if matches:
                final_path = matches[0]
        return final_path

    def cleanup_partial_files() -> None:
        for path in output_dir.glob(f"{filename_stem}*"):
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    ytdlp_logger.warning("Failed to remove partial file: %s", path)

    def run_download(format_selector: str):
        options = build_ytdlp_options(
            proxy,
            cookiefile=cookiefile,
            quiet=True,
            no_warnings=True,
            noplaylist=True,
            merge_output_format="mp4",
            outtmpl=template,
            format=format_selector,
            retries=5,
            fragment_retries=5,
            extractor_retries=3,
            sleep_interval_requests=1,
            progress_hooks=[progress_hook],
        )
        if download_subtitles:
            options.update(
                {
                    "writesubtitles": True,
                    "writeautomaticsub": True,
                    # Avoid requesting every language track (can trigger 429 on Shorts).
                    "subtitleslangs": ["zh-Hans", "zh-CN", "zh", "en-US", "en-GB", "en", "-live_chat"],
                    "subtitlesformat": "srt/vtt/best",
                }
            )

        ytdlp_logger.info("开始下载 YouTube 视频: %s", url)
        ytdlp_logger.info("yt-dlp 配置参数: %s", options)
        ytdlp_logger.info("输出目录: %s", output_dir)
        ytdlp_logger.info("文件名模板: %s", template)

        with YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=True)

    try:
        result = run_download(PRIMARY_FORMAT)
    except DownloadError as exc:
        error_text = str(exc).lower()
        if "empty" not in error_text and "merge" not in error_text:
            raise
        ytdlp_logger.warning("Primary YouTube format failed, retrying with fallback: %s", exc)
        cleanup_partial_files()
        result = run_download(FALLBACK_FORMAT)

    if isinstance(result, dict) and result.get("entries"):
        raise DownloadError("playlist is not supported")

    final_path = find_downloaded_file(result)

    if final_path is None or not final_path.exists():
        raise DownloadError("download finished but local file not found")
    if final_path.stat().st_size == 0:
        raise DownloadError("downloaded file is empty")

    subtitle_path = None
    if isinstance(result, dict):
        requested_subtitles = result.get("requested_subtitles") or {}
        for subtitle in requested_subtitles.values():
            if isinstance(subtitle, dict):
                filepath = subtitle.get("filepath")
                if filepath:
                    candidate = Path(filepath)
                    if candidate.exists():
                        subtitle_path = candidate
                        break

    # If subtitle is still missing, download only one best available subtitle track.
    if download_subtitles and subtitle_path is None and isinstance(result, dict):
        subtitles_dict = result.get("subtitles") or {}
        auto_subtitles_dict = result.get("automatic_captions") or {}
        available_languages = list(dict.fromkeys([*subtitles_dict.keys(), *auto_subtitles_dict.keys()]))
        selected_lang = pick_best_subtitle_language(available_languages)
        if selected_lang:
            subtitle_only_options = build_ytdlp_options(
                proxy,
                cookiefile=cookiefile,
                quiet=True,
                no_warnings=True,
                skip_download=True,
                noplaylist=True,
                outtmpl=template,
                writesubtitles=True,
                writeautomaticsub=True,
                subtitleslangs=[selected_lang, "-live_chat"],
                subtitlesformat="srt/vtt/best",
                retries=5,
                fragment_retries=5,
                extractor_retries=3,
                sleep_interval_requests=1,
            )
            try:
                with YoutubeDL(subtitle_only_options) as ydl:
                    ydl.extract_info(url, download=True)
            except DownloadError:
                pass

    if subtitle_path is None:
        subtitle_candidates = sorted(
            [path for path in output_dir.glob(f"{filename_stem}*") if path.suffix.lower() in {".srt", ".vtt", ".ass", ".ttml", ".sbv"}],
            key=lambda path: (0 if path.suffix.lower() == ".srt" else 1, -path.stat().st_mtime),
        )
        if subtitle_candidates:
            subtitle_path = subtitle_candidates[0]

    return final_path, subtitle_path


def embed_subtitle_into_video(video_path: Path, subtitle_path: Path) -> Path:
    if not video_path.exists():
        raise FileNotFoundError(f"video file not found: {video_path}")
    if not subtitle_path.exists():
        raise FileNotFoundError(f"subtitle file not found: {subtitle_path}")

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg is required for subtitle embedding")

    output_path = video_path.with_name(f"{video_path.stem}.subtitled{video_path.suffix}")
    command = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(subtitle_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-map",
        "1:0",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-c:s",
        "mov_text",
        "-metadata:s:s:0",
        "language=chi",
        "-disposition:s:0",
        "default",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not output_path.exists():
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"ffmpeg subtitle embedding failed: {stderr[:400]}")
    return output_path
