from unittest.mock import Mock, patch

import pytest

from tests.test_web import client
from sau_core import services
from sau_core.title_translation import translate_title_to_zh


def test_translation_defaults_and_key_is_never_returned(client):
    settings = client.get('/api/v2/settings').json()
    assert settings['translation']['autoTranslateTitle'] is True
    response = client.put('/api/v2/settings', json={
        'llm': {'baseUrl': 'https://example.test/v1', 'model': 'test-model', 'apiKey': 'secret-key'},
        'translation': {'autoTranslateTitle': True},
    })
    assert response.status_code == 200, response.text
    assert 'secret-key' not in response.text
    assert response.json()['llm']['apiKeyConfigured']
    assert 'secret-key' not in client.get('/api/v2/settings').text
    # Saving other settings or a blank password must retain the configured key.
    client.put('/api/v2/settings', json={'llm': {'baseUrl': 'https://example.test/v1', 'model': 'test-model', 'apiKey': ''}})
    assert client.get('/api/v2/settings').json()['llm']['apiKeyConfigured']
    client.put('/api/v2/settings', json={'llm': {'baseUrl': 'https://example.test/v1', 'model': 'test-model', 'clearApiKey': True}})
    assert not client.get('/api/v2/settings').json()['llm']['apiKeyConfigured']


def test_unconfigured_translation_keeps_original_without_network(client):
    with patch('sau_core.title_translation.requests.Session') as session:
        assert translate_title_to_zh('A day in Tokyo') == ''
        session.assert_not_called()


def configure(client):
    assert client.put('/api/v2/settings', json={
        'llm': {'baseUrl': 'https://example.test/v1/', 'model': 'test-model', 'apiKey': 'secret-key'},
    }).status_code == 200


def test_llm_translates_mixed_language_titles_and_disabled_does_not_send(client):
    configure(client)
    response = Mock()
    response.json.return_value = {'choices': [{'message': {'content': '我的旅行：东京的一天'}}]}
    with patch('sau_core.title_translation.requests.Session') as session:
        session.return_value.__enter__.return_value.post.return_value = response
        assert translate_title_to_zh('我的旅行: A day in Tokyo') == '我的旅行：东京的一天'
        call = session.return_value.__enter__.return_value.post.call_args
        assert call.args[0] == 'https://example.test/v1/chat/completions'
        assert call.kwargs['headers']['Authorization'] == 'Bearer secret-key'
        assert call.kwargs['json']['model'] == 'test-model'
        client.put('/api/v2/settings', json={'translation': {'autoTranslateTitle': False}})
        session.reset_mock()
        assert translate_title_to_zh('A day in Tokyo') == ''
        session.assert_not_called()


@pytest.mark.parametrize('content', ['', 'English only', '<think>hidden</think>'])
def test_bad_model_output_falls_back_without_failing_download(client, content):
    configure(client)
    response = Mock()
    response.json.return_value = {'choices': [{'message': {'content': content}}]}
    with patch('sau_core.title_translation.requests.Session') as session:
        session.return_value.__enter__.return_value.post.return_value = response
        assert translate_title_to_zh('A day in Tokyo') == ''


def test_translation_timeout_is_nonfatal_and_test_endpoint_redacts_errors(client):
    configure(client)
    with patch('sau_core.title_translation.requests.Session') as session:
        session.return_value.__enter__.return_value.post.side_effect = RuntimeError('secret-key')
        assert translate_title_to_zh('A day in Tokyo') == ''
        response = client.post('/api/v2/settings/translation/test')
        assert response.status_code == 400
        assert 'secret-key' not in response.text
    assert client.post('/api/v2/settings/translation/test', headers={'X-SAU-Token': 'wrong'}).status_code == 403


@pytest.mark.parametrize('translated', ['东京的一天', ''])
def test_download_uses_chinese_title_for_filename_and_material(client, translated):
    configure(client)
    services.save_video_processing_settings({'autoProcess': False})
    service = services.DownloadService()
    def download(url, directory, title, **options):
        assert title == (translated or 'A day in Tokyo')
        path = directory / (title + '.mp4')
        path.write_bytes(b'fake-video')
        return path, None
    with patch.object(services, 'extract_video_metadata', return_value={'title': 'A day in Tokyo'}), \
         patch.object(services, 'translate_title_to_zh', return_value=translated), \
         patch.object(services, 'download_video', side_effect=download), \
         patch.object(services, 'detect_video_resolution', return_value='1280x720'):
        task = service.create_youtube_download_task('https://youtu.be/dQw4w9WgXcQ', False, background=False)
        service._process_youtube_download(task, 'https://youtu.be/dQw4w9WgXcQ', False, None)
    result = service.get_youtube_task(task)
    assert result['status'] == 'success'
    assert result['videoTitleZh'] == translated
    material = services.MaterialService().list_materials()[0]
    assert material['video_title'] == 'A day in Tokyo'
    assert material['video_title_zh'] == translated
