"""Account profiles against offline Chrome pages; no platform requests or posts."""
import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from patchright.async_api import async_playwright
from tests.test_web import client

from utils.douyin_browser import (
    account_profile_dir, open_douyin_browser, profile_lock, save_douyin_storage,
)


def credentials(path, value='imported', local_value='initial'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        'cookies': [{'name':'auth', 'value':value, 'domain':'creator.douyin.com',
                     'path':'/', 'expires':time.time()+86400, 'httpOnly':True,
                     'secure':True, 'sameSite':'Lax'}],
        'origins': [{'origin':'https://creator.douyin.com',
                     'localStorage':[{'name':'device', 'value':local_value}]}],
    }), encoding='utf-8')


async def offline_page(context):
    await context.route('**/*', lambda r: r.fulfill(
        content_type='text/html', body='<meta charset="utf-8"><title>Offline creator</title>'))
    page = await context.new_page()
    await page.goto('https://creator.douyin.com/')
    return page


def test_profile_retains_browser_changes_and_session_cookies_across_relaunch(tmp_path):
    cookie = tmp_path/'cookiesFile'/'account-a.json'
    credentials(cookie)
    profile = account_profile_dir(cookie)
    async def exercise():
        async with async_playwright() as p:
            async with open_douyin_browser(p, cookie, profile_dir=profile) as context:
                page = await offline_page(context)
                assert await page.evaluate('localStorage.getItem("device")') == 'initial'
                assert {c['name']:c['value'] for c in await context.cookies()}['auth'] == 'imported'
                await page.evaluate('localStorage.setItem("device","trusted-device")')
                await page.evaluate('''() => new Promise((resolve,reject)=>{
                    const request=indexedDB.open('trusted-device',1);
                    request.onupgradeneeded=()=>request.result.createObjectStore('proof');
                    request.onerror=()=>reject(request.error);
                    request.onsuccess=()=>{
                        const db=request.result, tx=db.transaction('proof','readwrite');
                        tx.objectStore('proof').put('verified','device');
                        tx.oncomplete=()=>{db.close();resolve()};
                    };
                })''')
                await context.add_cookies([
                    {'name':'auth','value':'browser-updated','url':'https://creator.douyin.com','expires':time.time()+86400},
                    {'name':'session-proof','value':'verified','url':'https://creator.douyin.com'},
                ])
            async with open_douyin_browser(p, cookie, profile_dir=profile) as context:
                page = await offline_page(context)
                assert await page.evaluate('localStorage.getItem("device")') == 'trusted-device'
                values = {c['name']:c['value'] for c in await context.cookies()}
                assert values['auth'] == 'browser-updated'
                assert values['session-proof'] == 'verified'
                assert await page.evaluate('''() => new Promise((resolve,reject)=>{
                    const request=indexedDB.open('trusted-device',1);
                    request.onerror=()=>reject(request.error);
                    request.onsuccess=()=>{
                        const db=request.result, get=db.transaction('proof').objectStore('proof').get('device');
                        get.onsuccess=()=>{db.close();resolve(get.result)};
                    };
                })''') == 'verified'
                # Exporting the current state must not reset the profile next time.
                await save_douyin_storage(context, cookie, profile)
            async with open_douyin_browser(p, cookie, profile_dir=profile) as context:
                page = await offline_page(context)
                assert await page.evaluate('localStorage.getItem("device")') == 'trusted-device'
    asyncio.run(exercise())


def test_reimported_credentials_replace_old_account_authentication(tmp_path):
    cookie = tmp_path/'cookiesFile'/'account-a.json'
    credentials(cookie)
    profile = account_profile_dir(cookie)
    async def exercise():
        async with async_playwright() as p:
            async with open_douyin_browser(p, cookie, profile_dir=profile) as context:
                await offline_page(context)
                await context.add_cookies([{'name':'old-auth','value':'old','url':'https://creator.douyin.com'}])
            credentials(cookie, 'new-login', 'new-device')
            async with open_douyin_browser(p, cookie, profile_dir=profile) as context:
                page = await offline_page(context)
                assert await page.evaluate('localStorage.getItem("device")') == 'new-device'
                values = {c['name']:c['value'] for c in await context.cookies()}
                assert values['auth'] == 'new-login'
                assert 'old-auth' not in values
                await page.evaluate('localStorage.clear();localStorage.setItem("device","after-relogin")')
                await save_douyin_storage(context, cookie, profile, reset_bootstrap=True)
            async with open_douyin_browser(p, cookie, profile_dir=profile) as context:
                page = await offline_page(context)
                assert await page.evaluate('localStorage.getItem("device")') == 'after-relogin'
    asyncio.run(exercise())


def test_deleting_account_removes_its_private_profile(client):
    from tests.test_web import account
    from sau_core import services
    user = account(client)
    with client.app_store.connect() as conn:
        cookie_name = conn.execute('SELECT filePath FROM user_info WHERE id=?', (user['id'],)).fetchone()[0]
    profile = account_profile_dir(services.COOKIE_DIR/cookie_name)
    profile.mkdir(parents=True)
    (profile/'private-session.json').write_text('test credentials', encoding='utf-8')
    with profile_lock(profile):
        assert client.delete(f"/api/v2/accounts/{user['id']}").status_code == 409
        assert profile.exists()
    assert client.delete(f"/api/v2/accounts/{user['id']}").status_code == 204
    assert not profile.exists()


def test_profiles_are_account_specific_and_lock_is_exclusive(tmp_path):
    first = account_profile_dir(tmp_path/'cookiesFile'/'a.json')
    second = account_profile_dir(tmp_path/'cookiesFile'/'b.json')
    assert first != second
    assert first.is_relative_to(tmp_path/'runtime'/'douyin-browser')
    with profile_lock(first):
        with pytest.raises(RuntimeError, match='正在使用'):
            with profile_lock(first):
                pass
        with profile_lock(second):
            pass
    with profile_lock(first):
        pass


def test_web_login_check_and_publish_share_the_same_profile(tmp_path):
    from sau_web import adapters
    from uploader.douyin_uploader import main as douyin
    cookie = tmp_path/'cookiesFile'/'account.json'
    credentials(cookie)
    profile = account_profile_dir(cookie)
    async def exercise():
        with patch.object(douyin, 'cookie_auth', AsyncMock(return_value=True)) as check:
            assert await adapters.check(3, cookie)
            check.assert_awaited_once_with(str(cookie), profile_dir=profile)
        with patch.object(douyin, 'douyin_setup', AsyncMock(return_value={'success':True})) as login:
            await adapters.login(3, cookie, lambda data: None)
            assert login.await_args.kwargs['profile_dir'] == profile
        video = adapters.make_uploader(3, cookie, tmp_path/'v.mp4', '测试', '', [])
        assert video.browser_profile_dir == profile
    asyncio.run(exercise())
