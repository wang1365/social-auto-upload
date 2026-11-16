import io
import json
import zipfile

import pytest

from tests.test_web import client
from sau_web.youtube_browser import load_browser_cookies


def cookie(name="SID", value="browser-session", domain=".youtube.com", **fields):
    return {"name": name, "value": value, "domain": domain, "path": "/",
            "secure": True, "httpOnly": True, "expires": None, **fields}


def test_browser_import_saves_only_supported_unexpired_cookies_and_preserves_session(client):
    response = client.post("/api/v2/settings/youtube-cookie/browser", json={"cookies": [
        cookie(),
        cookie("PREF", " language with spaces ", httpOnly=False, expires=4102444800),
        cookie(domain=".google.com", value="google-session"),
        cookie("EXPIRED", "old", expires=1),
        cookie(domain=".youtube.com.evil.test", value="unrelated"),
    ]})
    assert response.status_code == 200, response.text
    assert response.json()["youtubeCookieConfigured"]
    saved = client.runtime_home / "cookiesFile/system/youtube_cookies.txt"
    actual = {(c["domain"], c["name"]): c for c in load_browser_cookies(saved)}
    assert set(actual) == {(".youtube.com", "SID"), (".youtube.com", "PREF"), (".google.com", "SID")}
    assert actual[(".youtube.com", "SID")]["httpOnly"]
    assert "expires" not in actual[(".youtube.com", "SID")]
    assert actual[(".youtube.com", "PREF")]["value"] == " language with spaces "
    assert "browser-session" not in response.text and "google-session" not in response.text


@pytest.mark.parametrize("cookies", [
    [], [cookie("PREF", "only-preferences")], [cookie(expires=1)],
    [cookie(domain=".example.com")], [cookie(value="secret\nnew-row")],
])
def test_unusable_import_does_not_overwrite_saved_credentials(client, cookies):
    saved = client.runtime_home / "cookiesFile/system/youtube_cookies.txt"
    saved.write_text("original-credentials", encoding="utf-8")
    response = client.post("/api/v2/settings/youtube-cookie/browser", json={"cookies": cookies})
    assert response.status_code in {400, 422}
    assert saved.read_text(encoding="utf-8") == "original-credentials"
    assert "secret" not in response.text


def test_browser_import_requires_csrf_token(client):
    response = client.post("/api/v2/settings/youtube-cookie/browser",
                           json={"cookies": [cookie()]}, headers={"X-SAU-Token": "wrong"})
    assert response.status_code == 403


def test_browser_helper_download_contains_only_extension_sources(client):
    response = client.get("/api/v2/settings/browser-helper.zip")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"manifest.json", "background.js", "content.js", "README.txt"}
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["manifest_version"] == 3
        assert manifest["permissions"] == ["cookies"]
        assert "<all_urls>" not in json.dumps(manifest)
        assert manifest["host_permissions"] == ["https://*.youtube.com/*", "https://*.google.com/*"]
