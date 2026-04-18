import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


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
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir / f"{filename_stem}.%(ext)s")

    def progress_hook(status: dict):
        if progress_callback:
            progress_callback(status)

    options = build_ytdlp_options(
        proxy,
        cookiefile=cookiefile,
        quiet=True,
        noplaylist=True,
        merge_output_format="mp4",
        outtmpl=template,
        format=(
            "bv*+ba/"
            "best*[ext=mp4][vcodec!=none][acodec!=none]/"
            "best*[vcodec!=none][acodec!=none]/"
            "best"
        ),
        progress_hooks=[progress_hook],
    )

    with YoutubeDL(options) as ydl:
        result = ydl.extract_info(url, download=True)

    if isinstance(result, dict) and result.get("entries"):
        raise DownloadError("playlist is not supported")

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
        matches = sorted(output_dir.glob(f"{filename_stem}.*"))
        if matches:
            final_path = matches[0]

    if final_path is None or not final_path.exists():
        raise DownloadError("download finished but local file not found")

    return final_path
