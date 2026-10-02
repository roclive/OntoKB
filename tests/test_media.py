import json
import math
import subprocess
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from ontokb import media
from ontokb.api import GraphApiHandler
from ontokb.graph import GraphStore


@pytest.fixture
def graph(tmp_path):
    graph = GraphStore(tmp_path / 'test.db')
    graph.conn.execute('INSERT INTO contents (id,kind,source,url,title,status,meta) VALUES (?,?,?,?,?,?,?)',
        ('yt:example', 'video', 'youtube', 'https://www.youtube.com/watch?v=abcdefghijk',
         'Example', 'processed', json.dumps({'summary': 'neural networks learning systems'})))
    graph.conn.commit()
    yield graph
    graph.close()


def ready(graph, mode='video'):
    directory, _ = media._directory(graph, media._record(graph, 'yt:example'), mode)
    directory.mkdir(parents=True, exist_ok=True)
    ext = 'mp4' if mode == 'video' else 'm4a'
    (directory / f'0.{ext}').write_bytes(b'0123456789')
    (directory / f'highlight.{ext}').write_bytes(b'0123456789')
    (directory / '0.jpg').write_bytes(b'image')
    manifest = {'status': 'ready', 'mode': mode, 'slides': [{'start': 0, 'end': 10}], 'duration': 10,
                'generation_backend': 'codex-harness', 'alignment_version': 1,
                'subtitle_language': 'zh', 'summary_steps': []}
    manifest['slides'][0].update({'text': '中文字幕', 'captions': [
        {'start': 0, 'end': 10, 'text': '中文字幕', 'summary_index': None}],
        'summary_index': None, 'summary_indices': []})
    (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return directory


def test_clip_selection_grounded_bounded_and_chronological():
    segments = [{'start': i * 5, 'end': i * 5 + 5, 'text': f'neural networks {i}'} for i in range(80)]
    clips = media.select_clips(segments, 'neural networks')
    assert len(clips) == 6
    assert sum(c['end'] - c['start'] for c in clips) <= 120
    assert all(a['end'] <= b['start'] for a, b in zip(clips, clips[1:]))
    assert all('neural networks' in c['text'] for c in clips)


def test_invalid_timestamps_and_long_cues_not_fabricated():
    segments = [{'start': 0, 'end': 100, 'text': 'Cannot align all this text to twenty seconds'},
                {'start': math.nan, 'end': 3, 'text': 'bad'},
                {'start': -1, 'end': 4, 'text': 'bad'},
                {'start': 3, 'end': 2, 'text': 'bad'},
                {'start': 110, 'end': 117, 'text': 'A complete short quote'}]
    assert media.select_clips(segments, '') == [{'start': 110, 'end': 117, 'text': 'A complete short quote'}]


def test_semantic_indices_cannot_invent_timestamps(monkeypatch):
    class Response:
        returncode = 0
        stdout = '[1, 1, -1, 99, true, "0"]'
    monkeypatch.setattr(media.subprocess, 'run', lambda *a, **kw: Response())
    clips, message = media._select_summary_clips(
        [{'start': 0, 'end': 10, 'text': 'Introduction'},
         {'start': 30, 'end': 40, 'text': 'Neural networks can learn'}], '神经网络', {})
    assert clips == [{'start': 30, 'end': 40, 'text': 'Neural networks can learn'}]
    assert '语义' in message


def test_no_summary_match_is_unavailable(monkeypatch):
    class Response:
        returncode = 1
        stdout = ''
    monkeypatch.setattr(media.subprocess, 'run', lambda *a, **kw: Response())
    with pytest.raises(media.MediaUnavailable, match='可靠对应'):
        media._select_summary_clips([{'start': 0, 'end': 10, 'text': 'Welcome everyone'}], '神经网络', {})


def test_cache_reused_and_invalidated_by_summary(graph):
    ready(graph)
    assert media.prepare(graph, 'yt:example')['status'] == 'ready'
    graph.conn.execute('UPDATE contents SET meta=?', (json.dumps({'summary': 'Changed summary'}),))
    graph.conn.commit()
    assert media.status(graph, 'yt:example')['status'] == 'unavailable'


def test_deleted_asset_never_returns_stale_ready(graph):
    directory = ready(graph)
    media._jobs[str(directory)] = {'status': 'ready', 'slides': [{}], 'duration': 10}
    (directory / '0.mp4').unlink()
    assert media.status(graph, 'yt:example')['status'] == 'unavailable'


def test_corrupt_short_clip_transcript_cache_is_regenerated_without_invalidating_good_cache(graph):
    good = ready(graph, 'video')
    bad = ready(graph, 'audio')
    data = json.loads((bad / 'manifest.json').read_text(encoding='utf-8'))
    data['slides'][0].update({'start': .259, 'end': 3.309, 'text': '坏字幕' * 2000})
    (bad / 'manifest.json').write_text(json.dumps(data), encoding='utf-8')
    assert media._cached_manifest(bad, 'audio') is None
    assert media.status(graph, 'yt:example', 'audio')['status'] == 'unavailable'
    assert media._cached_manifest(good, 'video')['status'] == 'ready'
    assert media.status(graph, 'yt:example', 'video')['status'] == 'ready'


def test_modes_have_separate_results_and_one_shared_source(graph):
    video = ready(graph)
    audio = ready(graph, 'audio')
    row = media._record(graph, 'yt:example')
    assert video != audio
    assert media._source_path(video, row) == media._source_path(audio, row)
    assert media.asset(graph, 'yt:example', 'highlight.mp4') == video / 'highlight.mp4'
    assert media.asset(graph, 'yt:example', 'highlight.m4a', 'audio') == audio / 'highlight.m4a'
    with pytest.raises(ValueError):
        media.asset(graph, 'yt:example', 'highlight.mp4', 'audio')
    with pytest.raises(ValueError):
        media.prepare(graph, 'yt:example', mode=[])


def test_audio_context_reaches_one_third_without_duplicate_speech():
    segments = [{'start': i, 'end': i+5, 'text': f'Spoken sentence {i}'} for i in range(0, 570, 5)]
    anchors = [dict(segments[i]) for i in (5, 15, 30, 50, 70, 100)]
    clips = media.fit_duration(anchors, segments, 572/3, 572)
    total = sum(c['end'] - c['start'] for c in clips)
    assert .85 * (572/3) <= total <= 1.15 * (572/3)
    assert all(a['end'] <= b['start'] for a, b in zip(clips, clips[1:]))


def test_short_audio_budget_keeps_long_cues_without_exceeding_one_third():
    segments = [{'start': i, 'end': i + 20, 'text': 'complete spoken paragraph'}
                for i in range(0, 180, 20)]
    count, window = media._selection_budget('audio', 60, segments)
    assert count == 3 and window == 20
    anchors = media.select_clips(segments, 'spoken paragraph', max_clips=count, window_seconds=window)
    clips = media.fit_duration(anchors, segments, 60, 180)
    assert sum(c['end'] - c['start'] for c in clips) == 60
    assert all(c['text'] for c in clips)
    assert all(c['text'] for c in clips)
    assert all(any(c['start'] <= a['start'] and c['end'] >= a['end'] for c in clips) for a in anchors)
    assert all(c['start'] % 5 == 0 and c['end'] % 5 == 0 for c in clips)


def test_context_preserves_complete_selected_assertions():
    segments = [{'start': i, 'end': i+20, 'text': f'Complete assertion {i}'} for i in range(0, 240, 40)]
    clips = media.fit_duration(segments, segments, 90, 300)
    assert sum(c['end'] - c['start'] for c in clips) <= 120
    assert [c['text'] for c in clips] == [s['text'] for s in segments]
    assert all(c['start'] == s['start'] and c['end'] == s['end'] for c, s in zip(clips, segments))


def test_source_duration_never_assumes_caption_end_is_video_end(tmp_path):
    from ontokb.models import ContentItem
    item = ContentItem(id='yt:abcdefghijk', kind='video', source='youtube', url='https://www.youtube.com/watch?v=abcdefghijk')
    segments = [{'start': 0, 'end': 100, 'text': 'caption'}]
    assert media._source_duration(item, tmp_path, {}, segments) is None
    assert media._source_duration(item, tmp_path, {'duration_seconds': 90}, segments) is None
    assert media._source_duration(item, tmp_path, {'duration_seconds': 3600}, segments) == 3600


def test_concurrent_modes_download_source_only_once(graph, monkeypatch):
    row = media._record(graph, 'yt:example')
    directories = [media._directory(graph, row, mode)[0] for mode in ('video', 'audio')]
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        from pathlib import Path
        Path(args[args.index('-o')+1]).write_bytes(b'source')
    monkeypatch.setattr(media, '_run', fake_run)
    threads = [threading.Thread(target=media._download_source, args=(row, directory, {}, 'ffmpeg')) for directory in directories]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(3)
        assert not thread.is_alive()
    assert len(calls) == 1
    assert media._source_path(directories[0], row).read_bytes() == b'source'


@pytest.mark.parametrize('name', ['../source.mp4', 'manifest.json', 'source.mp4', '6.mp4', '/0.jpg', '0.jpg/..'])
def test_asset_whitelist(graph, name):
    ready(graph)
    with pytest.raises(ValueError):
        media.asset(graph, 'yt:example', name)


def test_background_job_uses_own_connection_and_deduplicates(graph, monkeypatch):
    from ontokb import media_harness
    monkeypatch.setattr(media_harness, 'run_media_task', lambda context, callback, **kw: callback())
    release, entered = threading.Event(), threading.Event()
    calls = []
    def generate(row, directory, options, mode):
        calls.append(row['id'])
        entered.set()
        release.wait(3)
        raise media.MediaUnavailable('test stop')
    monkeypatch.setattr(media, '_generate', generate)
    assert media.prepare(graph, 'yt:example')['status'] == 'working'
    assert entered.wait(3)
    assert media.prepare(graph, 'yt:example')['status'] == 'working'
    release.set()
    assert calls == ['yt:example']


def test_http_asset_ranges_and_status(graph):
    ready(graph)
    ready(graph, 'audio')
    db = graph.conn.execute('PRAGMA database_list').fetchone()[2]
    class Handler(GraphApiHandler):
        def setup(self):
            super().setup()
            self.store = GraphStore(db)
        def finish(self):
            try:
                super().finish()
            finally:
                self.store.close()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection('127.0.0.1', server.server_port)
    try:
        connection.request('GET', '/api/media/status?content_id=yt%3Aexample')
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())['status'] == 'ready'
        connection.request('GET', '/api/media/asset?content_id=yt%3Aexample&name=0.mp4', headers={'Range': 'bytes=2-5'})
        response = connection.getresponse()
        assert response.status == 206
        assert response.getheader('Content-Range') == 'bytes 2-5/10'
        assert response.read() == b'2345'
        connection.request('GET', '/api/media/asset?content_id=yt%3Aexample&name=0.mp4', headers={'Range': 'bytes=20-'})
        response = connection.getresponse()
        assert response.status == 416
        response.read()
        connection.request('GET', '/api/media/asset?content_id=yt%3Aexample&mode=audio&name=highlight.m4a&download=1')
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader('Content-Type') == 'audio/mp4'
        assert response.getheader('Content-Disposition') == 'attachment; filename="ontokb-highlight.m4a"'
        assert response.read() == b'0123456789'
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize('mode', ['video', 'audio'])
def test_real_ffmpeg_preserves_audio_and_creates_screenshot(graph, monkeypatch, mode):
    from ontokb import pipeline
    from ontokb.sources import youtube
    pytest.importorskip('yt_dlp')
    try:
        ffmpeg = media._ffmpeg()
    except media.MediaUnavailable:
        pytest.skip('FFmpeg optional media dependency is not installed')
    row = media._record(graph, 'yt:example')
    directory, _ = media._directory(graph, row, mode)
    directory.mkdir(parents=True)
    source = media._source_path(directory, row)
    source.parent.mkdir(parents=True)
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
        'color=c=blue:s=320x240:d=6', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=6',
        '-c:v', 'libx264', '-c:a', 'aac', '-threads', '2', '-shortest', str(source)], check=True, timeout=30)
    monkeypatch.setattr(pipeline, 'load_config', lambda: {})
    monkeypatch.setattr(youtube, 'read_transcript_segments', lambda *a: [{'start': i, 'end': i+1, 'text': 'neural networks'} for i in range(6)])
    monkeypatch.setattr(media, '_select_summary_clips', lambda *a: ([{'start': 0, 'end': 2, 'text': 'neural networks'}], 'test'))
    result = media._generate(row, directory, mode=mode)
    assert result['duration'] == pytest.approx(6 if mode == 'video' else 2, abs=.15)
    assert result['target_duration'] == (6 if mode == 'video' else 2)
    assert result['source_duration'] == 6
    assert 'download=1' in result['download_url']
    assert (directory / '0.jpg').stat().st_size > 100
    ext = 'mp4' if mode == 'video' else 'm4a'
    probe = subprocess.run([ffmpeg, '-hide_banner', '-i', str(directory / f'highlight.{ext}'), '-f', 'null', '-'],
        capture_output=True, text=True, timeout=30)
    assert probe.returncode == 0
    assert 'Audio: aac' in probe.stderr
    assert ('Video: h264' in probe.stderr) == (mode == 'video')
    assert source.is_file()
