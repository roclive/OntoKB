import json

import pytest

from ontokb import media, pipeline
from ontokb.sources import youtube


@pytest.mark.parametrize('mode', ['video', 'audio'])
def test_media_caption_backfill_detects_source_language_without_changing_ingest(monkeypatch, tmp_path, mode):
    config = {'sources': {'youtube': {
        'whisper_language': 'zh', 'whisper_model': 'small', 'whisper_device': 'cpu',
        'whisper_compute_type': 'int8', 'cookies_file': 'configured-cookies.txt',
    }}}
    row = {'id': 'yt:abcdefghijk', 'url': 'https://youtu.be/abcdefghijk',
           'title': 'Source language test', 'meta': '{}'}
    monkeypatch.setattr(pipeline, 'load_config', lambda: config)
    monkeypatch.setattr(media, '_ffmpeg', lambda: 'ffmpeg')
    monkeypatch.setattr(media.importlib.util, 'find_spec', lambda name: object())
    monkeypatch.setattr(youtube, 'read_transcript_segments', lambda *a: [])
    calls = []

    class StopAfterAcquisition(Exception):
        pass

    def run(args, **kwargs):
        calls.append(args)
        raise StopAfterAcquisition

    monkeypatch.setattr(media, '_run', run)
    with pytest.raises(StopAfterAcquisition):
        media._generate(row, tmp_path / mode, mode=mode)
    assert len(calls) == 1
    payload = json.loads(calls[0][-1])
    assert payload['options']['whisper_language'] == 'auto'
    assert payload['options']['whisper_model'] == 'small'
    assert payload['options']['cookies_file'] == 'configured-cookies.txt'
    assert 'require_segments=True' in calls[0][-2]
    assert config['sources']['youtube']['whisper_language'] == 'zh'
    assert youtube.DEFAULT_WHISPER_LANGUAGE == 'zh'
