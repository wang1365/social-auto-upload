import re

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
