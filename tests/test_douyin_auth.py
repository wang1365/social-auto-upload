"""Login checks against offline Chrome pages; never uploads or contacts Douyin."""
import asyncio
import json
from unittest.mock import patch

import pytest

from uploader.douyin_uploader import main as douyin


@pytest.mark.parametrize(('body', 'expected'), [
    ('<script>setTimeout(()=>document.body.innerHTML="<button>扫码登录</button>",300)</script>', False),
    ('<script>setTimeout(()=>document.body.innerHTML=\'<input type="file">\',300)</script>', True),
    ('<div style="display:none">扫码登录</div><input type="file">', True),
    ('<button>手机号登录</button><input type="file">', False),
])
def test_cookie_check_waits_for_real_login_or_upload_controls(tmp_path, body, expected):
    cookie = tmp_path / 'offline.json'
    cookie.write_text(json.dumps({'cookies': [], 'origins': []}), encoding='utf-8')
    async def offline(context):
        await context.route('**/*', lambda route: route.fulfill(
            content_type='text/html', body='<meta charset="utf-8">' + body))
        return context
    with patch.object(douyin, 'set_init_script', offline):
        assert asyncio.run(douyin.cookie_auth(str(cookie))) is expected


def test_unfinished_page_is_inconclusive_not_valid_or_expired(tmp_path, monkeypatch):
    cookie = tmp_path / 'offline.json'
    cookie.write_text(json.dumps({'cookies': [], 'origins': []}), encoding='utf-8')
    async def offline(context):
        await context.route('**/*', lambda route: route.fulfill(body='<title>Loading</title>'))
        return context
    monkeypatch.setattr(douyin, 'DOUYIN_AUTH_TIMEOUT_MS', 300, raising=False)
    with patch.object(douyin, 'set_init_script', offline):
        with pytest.raises(RuntimeError, match='登录状态检查未完成'):
            asyncio.run(douyin.cookie_auth(str(cookie)))
