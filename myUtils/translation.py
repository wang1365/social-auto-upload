import re
from pathlib import Path

import requests


MYMEMORY_TRANSLATE_URL = "https://api.mymemory.translated.net/get"


def contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def translate_title_to_zh(title: str) -> str:
    normalized_title = (title or "").strip()
    if not normalized_title:
        return ""
    if contains_chinese(normalized_title):
        return normalized_title

    response = requests.get(
        MYMEMORY_TRANSLATE_URL,
        params={
            "q": normalized_title,
            "langpair": "en|zh-CN",
        },
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()
    translated_text = (
        payload.get("responseData", {}).get("translatedText", "").strip()
        if isinstance(payload, dict)
        else ""
    )
    return translated_text or ""


def translate_text_to_zh(text: str) -> str:
    normalized_text = (text or "").strip()
    if not normalized_text:
        return ""
    if contains_chinese(normalized_text):
        return normalized_text
    try:
        response = requests.get(
            MYMEMORY_TRANSLATE_URL,
            params={
                "q": normalized_text,
                "langpair": "en|zh-CN",
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        translated_text = (
            payload.get("responseData", {}).get("translatedText", "").strip()
            if isinstance(payload, dict)
            else ""
        )
        return translated_text or normalized_text
    except Exception:
        return normalized_text


def _is_subtitle_text_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.isdigit():
        return False
    if "-->" in stripped:
        return False
    if stripped.upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION", "X-TIMESTAMP-MAP")):
        return False
    return True


def _read_text_with_fallback(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def translate_subtitle_file_to_zh(subtitle_path: Path | None) -> Path | None:
    if subtitle_path is None or not subtitle_path.exists() or not subtitle_path.is_file():
        return subtitle_path

    content = _read_text_with_fallback(subtitle_path)
    if not content.strip():
        return subtitle_path

    cache = {}
    translated_lines = []
    translated_any = False
    for line in content.splitlines():
        if not _is_subtitle_text_line(line):
            translated_lines.append(line)
            continue
        stripped = line.strip()
        if stripped not in cache:
            cache[stripped] = translate_text_to_zh(stripped)
        translated_line = cache[stripped]
        if translated_line != stripped:
            translated_any = True
        translated_lines.append(translated_line)

    if not translated_any:
        return subtitle_path

    translated_filename = f"{subtitle_path.stem}.zh{subtitle_path.suffix}"
    translated_path = subtitle_path.with_name(translated_filename)
    translated_path.write_text("\n".join(translated_lines), encoding="utf-8")
    return translated_path
