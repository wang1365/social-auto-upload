"""Real Chrome tab capture/RTC with synthetic video and tone, no external network."""
import asyncio
from unittest.mock import AsyncMock, patch

from sau_web.youtube_browser import YouTubeBrowser
from sau_web.schemas import BrowserAction
from tests.test_web import client


SOURCE = '''<!doctype html><title>Test - YouTube</title>
<canvas width="640" height="360"></canvas><script>
const ctx=document.querySelector('canvas').getContext('2d'); let f=0;
setInterval(()=>{ctx.fillStyle=f++%2?'red':'blue';ctx.fillRect(0,0,640,360)},33);
const audio=new AudioContext();const tone=audio.createOscillator();
tone.connect(audio.destination);tone.start();audio.resume();
</script>'''

RECEIVER = '''async () => {
 const peer=window.peer=new RTCPeerConnection({iceServers:[]});
 const video=document.createElement('video');video.autoplay=true;video.muted=true;
 document.body.append(video);window.video=video;
 const audio=window.audio=new AudioContext();
 window.energy=0;
 peer.ontrack=event=>{
   video.srcObject=event.streams[0];video.play();
   if(event.track.kind==='audio') {
     const analyser=audio.createAnalyser();
     audio.createMediaStreamSource(event.streams[0]).connect(analyser);
     const samples=new Float32Array(analyser.fftSize);
     setInterval(()=>{analyser.getFloatTimeDomainData(samples);
       window.energy=Math.max(window.energy,...samples.map(Math.abs));},50);
   }
 };
 peer.addTransceiver('video',{direction:'recvonly'});
 peer.addTransceiver('audio',{direction:'recvonly'});
 await peer.setLocalDescription(await peer.createOffer());
 await new Promise(resolve=>{
   if(peer.iceGatheringState==='complete') return resolve();
   peer.onicegatheringstatechange=()=>{if(peer.iceGatheringState==='complete')resolve()};
 });
 return peer.localDescription.toJSON();
}'''


def test_real_media_has_motion_audio_survives_navigation_and_closes(tmp_path):
    async def exercise():
        browser = YouTubeBrowser(tmp_path)
        receiver_browser = None
        async def navigate(url):
            await browser.page.route('**/*', lambda route: route.fulfill(content_type='text/html', body=SOURCE))
            await browser.page.goto(url)
        browser._navigate = navigate
        try:
            await browser.start()
            source = browser.page
            receiver_browser = await browser.driver.chromium.launch(channel='chrome', args=['--autoplay-policy=no-user-gesture-required'])
            receiver = await receiver_browser.new_page()
            await receiver.route('**/*', lambda route: route.fulfill(content_type='text/html', body='<title>Receiver</title>'))
            await receiver.goto('http://127.0.0.1/receiver')
            offer = await receiver.evaluate(RECEIVER)
            answer = await browser.media_offer(offer)
            assert browser.page == source  # Controller must never receive user input.
            await receiver.evaluate('answer=>peer.setRemoteDescription(answer)', {k: answer[k] for k in ('type','sdp')})
            try:
                await receiver.wait_for_function('video.getVideoPlaybackQuality().totalVideoFrames > 15 && energy > 0.01', timeout=20000)
            except Exception:
                print('RECEIVER', await receiver.evaluate("async()=>({state:peer.connectionState,ice:peer.iceConnectionState,frames:video.getVideoPlaybackQuality(),energy,audio:audio.state,stats:[...await peer.getStats()].filter(([k,v])=>v.type==='inbound-rtp')})"))
                print('SOURCE', await source.evaluate("({audio:audio.state, visibility:document.visibilityState})"))
                print('SENDER', await browser.controller.evaluate("async()=>({tracks:sauMedia.stream?.getTracks().map(t=>({kind:t.kind,muted:t.muted,state:t.readyState,settings:t.getSettings()})),stats:[...await [...sauMedia.peers.values()][0].getStats()].filter(([k,v])=>v.type==='outbound-rtp')})"))
                raise
            before = await receiver.evaluate('video.getVideoPlaybackQuality().totalVideoFrames')
            await browser.action(BrowserAction(kind='resize', width=1000, height=600))
            await source.goto('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
            await receiver.wait_for_function(f'video.getVideoPlaybackQuality().totalVideoFrames > {before + 15}', timeout=15000)
            assert (await browser.state())['image'] == ''  # Metadata polling cannot encode screenshots.
            assert (await browser.state())['width'] == 1000
            await browser.close_media(answer['id'])
            assert await browser.controller.evaluate('sauMedia.peers.size') == 0
            assert await browser.controller.evaluate('sauMedia.stream === null')
        finally:
            if receiver_browser:
                await receiver_browser.close()
            await browser.close()
        assert browser.controller is None
    asyncio.run(exercise())


def test_media_signaling_is_session_and_csrf_protected(client):
    body = {'type': 'offer', 'sdp': 'fake'}
    assert client.post('/api/v2/youtube/browser/media', json=body).status_code == 400
    assert client.post('/api/v2/youtube/browser/media', json=body, headers={'X-SAU-Token':'wrong'}).status_code == 403
    assert client.delete('/api/v2/youtube/browser/media/fake', headers={'X-SAU-Token':'wrong'}).status_code == 403
    client.cookies.clear()
    assert client.post('/api/v2/youtube/browser/media', json=body).status_code == 401


def test_signaling_preserves_sdp_line_endings(client):
    body = {'type': 'offer', 'sdp': 'v=0\r\na=test\r\n'}
    handler = AsyncMock(return_value={'id':'fake', 'type':'answer', 'sdp':'v=0\r\n'})
    with patch.object(client.app.state.youtube_browser, 'media_offer', handler):
        assert client.post('/api/v2/youtube/browser/media', json=body).status_code == 200
    assert handler.call_args.args[0] == body
