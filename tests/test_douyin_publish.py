"""Publish-page fixtures only; no real platform requests or content publishing."""
import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from patchright.async_api import async_playwright

from uploader.douyin_uploader.main import DouYinVideo


def test_publish_waits_for_confirmation_without_a_second_click(tmp_path):
    async def exercise():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel='chrome')
            try:
                page = await browser.new_page()
                await page.route('**/*', lambda r: r.fulfill(content_type='text/html', body='''
                    <meta charset="utf-8">
                    <button onclick="setTimeout(()=>location.href='/creator-micro/content/manage',3400)">发布</button>'''))
                await page.goto('https://creator.douyin.com/creator-micro/content/post/video')
                video = DouYinVideo('测试', str(tmp_path/'video.mp4'), [], 0, str(tmp_path/'cookie.json'))
                video.on_publish_attempt = Mock()
                video.on_publish_confirmed = Mock()
                await video._publish_video(page, timeout=6)
                assert video.publish_confirmed
                video.on_publish_attempt.assert_called_once()
                video.on_publish_confirmed.assert_called_once()
            finally:
                await browser.close()
    asyncio.run(exercise())


def test_uncertain_publish_times_out_without_reclicking(tmp_path):
    async def exercise():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel='chrome')
            try:
                page = await browser.new_page()
                await page.set_content('<button onclick="this.dataset.clicks=Number(this.dataset.clicks||0)+1">发布</button>')
                video = DouYinVideo('测试', str(tmp_path/'video.mp4'), [], 0, str(tmp_path/'cookie.json'))
                video.on_publish_attempt = Mock()
                with pytest.raises(RuntimeError, match='未收到.*确认'):
                    await video._publish_video(page, timeout=.15)
                assert await page.locator('button').get_attribute('data-clicks') == '1'
                assert not getattr(video, 'publish_confirmed', False)
            finally:
                await browser.close()
    asyncio.run(exercise())


def test_sms_verification_waits_for_human_and_never_reclicks_publish(tmp_path):
    async def exercise():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel='chrome')
            try:
                page = await browser.new_page()
                await page.route('**/*', lambda r: r.fulfill(content_type='text/html', body='''
                    <meta charset="utf-8">
                    <button onclick="this.dataset.clicks=Number(this.dataset.clicks||0)+1;document.querySelector('section').hidden=false">发布</button>
                    <section hidden><h2>接收短信验证码</h2><p>为确保是本人操作抖音账号，请输入短信验证码</p></section>'''))
                await page.goto('https://creator.douyin.com/creator-micro/content/post/video')
                video = DouYinVideo('测试', str(tmp_path/'video.mp4'), [], 0, str(tmp_path/'cookie.json'))
                async def human_finishes_fixture():
                    await asyncio.sleep(.6)
                    assert await page.locator('button').get_attribute('data-clicks') == '1'
                    await page.goto('https://creator.douyin.com/creator-micro/content/manage')
                video.on_publish_verification = Mock(side_effect=lambda message: asyncio.create_task(human_finishes_fixture()))
                await video._publish_video(page, timeout=.15, verification_timeout=2)
                assert video.publish_confirmed
                video.on_publish_verification.assert_called_once()
            finally:
                await browser.close()
    asyncio.run(exercise())


def test_web_douyin_uploader_has_visible_browser_for_verification(tmp_path):
    from sau_web.adapters import make_uploader
    video = make_uploader(3, tmp_path/'cookie.json', tmp_path/'video.mp4', '测试', '', [])
    assert video.headless is False


def test_verification_diagnostic_never_captures_code_entry(tmp_path):
    video = DouYinVideo('测试', str(tmp_path/'video.mp4'), [], 0, str(tmp_path/'cookie.json'))
    video.publish_verification_required = True
    video.publish_diagnostic_path = tmp_path/'diagnostic'
    page = Mock()
    page.screenshot = AsyncMock()
    asyncio.run(video._capture_publish_diagnostic(page))
    page.screenshot.assert_not_called()
    page.locator.assert_not_called()
    assert not (tmp_path/'diagnostic.png').exists()
    assert '人工安全验证' in (tmp_path/'diagnostic.txt').read_text(encoding='utf-8')
