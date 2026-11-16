"""Offline upload state, CSP and bounded retry tests. No platform publishing."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from patchright.async_api import async_playwright

from uploader.douyin_uploader import main as douyin


def uploader(tmp_path):
    return douyin.DouYinVideo('测试', str(tmp_path/'video.mp4'), [], 0, str(tmp_path/'cookie.json'))


def test_upload_retries_twice_then_stops(tmp_path, monkeypatch):
    video = uploader(tmp_path)
    attempt = AsyncMock(side_effect=RuntimeError('抖音视频上传失败：解析失败'))
    monkeypatch.setattr(douyin, 'DOUYIN_UPLOAD_RETRY_DELAY', 0, raising=False)
    with patch.object(video, '_upload_video_attempt', attempt, create=True):
        with pytest.raises(RuntimeError, match='已重试 2 次'):
            asyncio.run(video._upload_video_with_retries(None))
    assert attempt.await_count == 3


def test_transient_upload_failure_can_succeed_without_publishing(tmp_path, monkeypatch):
    video = uploader(tmp_path)
    attempt = AsyncMock(side_effect=[RuntimeError('上传失败'), None])
    monkeypatch.setattr(douyin, 'DOUYIN_UPLOAD_RETRY_DELAY', 0, raising=False)
    with patch.object(video, '_upload_video_attempt', attempt, create=True):
        asyncio.run(video._upload_video_with_retries(None))
    assert attempt.await_count == 2
    assert not getattr(video, 'publish_attempted', False)


@pytest.mark.parametrize(('body', 'success'), [
    ('<div class="preview-button-new"><input type="file" accept="video/mp4"><div>重新上传</div></div>', True),
    ('<div class="long-card-old"><div>重新上传</div></div>', True),
    ('<div class="progress-div"><div>上传失败：文件解析失败</div></div><div>重新上传</div>', False),
    ('<div style="display:none">上传失败</div><div class="preview-button-new"><input type="file" accept="video/mp4"><div>重新上传</div></div>', True),
])
def test_upload_state_recognizes_current_and_legacy_pages(tmp_path, body, success):
    async def exercise():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel='chrome')
            try:
                page = await browser.new_page()
                await page.set_content(body)
                if success:
                    await uploader(tmp_path)._wait_for_upload(page, timeout=1)
                else:
                    with pytest.raises(RuntimeError, match='文件解析失败'):
                        await uploader(tmp_path)._wait_for_upload(page, timeout=1)
            finally:
                await browser.close()
    asyncio.run(exercise())


def test_upload_wait_has_deadline(tmp_path):
    async def exercise():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel='chrome')
            try:
                page = await browser.new_page()
                await page.set_content('<div class="progress-div">文件解析中</div>')
                with pytest.raises(RuntimeError, match='超时'):
                    await uploader(tmp_path)._wait_for_upload(page, timeout=0.05)
            finally:
                await browser.close()
    asyncio.run(exercise())


def test_douyin_upload_context_allows_its_blob_parser_worker(tmp_path):
    async def exercise():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel='chrome')
            try:
                video = uploader(tmp_path)
                video.account_file = {'cookies':[], 'origins':[]}
                context = await video._create_upload_context(browser)
                await context.route('**/*', lambda route: route.fulfill(
                    content_type='text/html',
                    headers={'Content-Security-Policy':"script-src 'self' 'unsafe-eval' *"},
                    body='<title>Upload parser</title>'))
                page = await context.new_page()
                await page.goto('https://creator.douyin.com/')
                assert await page.evaluate('''() => new Promise((resolve,reject)=>{
                    const worker=new Worker(URL.createObjectURL(new Blob(['postMessage("parsed")'],{type:'text/javascript'})));
                    worker.onmessage=event=>{worker.terminate();resolve(event.data)};
                    worker.onerror=reject;
                })''') == 'parsed'
            finally:
                await browser.close()
    asyncio.run(exercise())
