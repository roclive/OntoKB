from __future__ import annotations

import sys
import json
import io
import pytest
from pathlib import Path
from types import SimpleNamespace

from ontokb.models import ContentItem
from ontokb.sources import youtube


def test_hls_caption_index_downloads_segment_bodies(monkeypatch):
    responses = {
        'https://example.test/captions/index.m3u8': '#EXTM3U\n#EXTINF:600,\npart1.vtt\n#EXTINF:600,\npart2.vtt',
        'https://example.test/captions/part1.vtt': 'WEBVTT\nX-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:0\n\n00:00:00.000 --> 00:00:02.000\n第一段正文',
        'https://example.test/captions/part2.vtt': 'WEBVTT\n\n00:10:00.000 --> 00:10:02.000\n第二段正文 &amp; 细节',
    }
    monkeypatch.setattr(youtube.urllib.request, 'urlopen',
                        lambda url, **kw: io.BytesIO(responses[url].encode()))
    assert youtube._fetch_caption_text('https://example.test/captions/index.m3u8') == '第一段正文\n第二段正文 & 细节'


def test_caption_segment_failure_does_not_accept_partial_text(monkeypatch):
    def read(url, **kwargs):
        if url.endswith('index'):
            return io.BytesIO(b'#EXTM3U\na.vtt\nb.vtt')
        if url.endswith('a.vtt'):
            return io.BytesIO(b'WEBVTT\n00:00:00 --> 00:00:01\nfirst')
        raise OSError('segment unavailable')
    monkeypatch.setattr(youtube.urllib.request, 'urlopen', read)
    with pytest.raises(OSError):
        youtube._fetch_caption_text('https://example.test/index')


@pytest.mark.parametrize('body', ['#EXTM3U\n#EXTINF:600,\nhttps://example.test/subs',
                                 '<html>Request denied</html>', 'https://example.test/subs', ''])
def test_transport_payload_is_not_transcript(tmp_path, body):
    item = ContentItem(id='yt:CETs0u10aSc', kind='video', source='youtube',
                       url='https://youtu.be/CETs0u10aSc')
    (tmp_path / 'CETs0u10aSc.json').write_text(json.dumps({'raw_text': body}), encoding='utf-8')
    assert not youtube.valid_transcript(body)
    assert youtube._read_cached_transcript(item, tmp_path) == ''


def test_fetch_transcript_falls_back_to_whisper(monkeypatch, tmp_path):
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def extract_info(self, url, download=False):
            assert download is False
            return {
                "title": "No captions",
                "subtitles": {},
                "automatic_captions": {},
            }

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYDL))
    def fake_transcribe(item, **kwargs):
        assert kwargs["language"] == "zh"
        return "local text"

    monkeypatch.setattr(youtube, "_transcribe_with_whisper", fake_transcribe)

    item = ContentItem(
        id="yt:CETs0u10aSc",
        kind="video",
        source="youtube",
        url="https://www.youtube.com/watch?v=CETs0u10aSc",
    )

    assert youtube.fetch_transcript(item, cache_dir=tmp_path) == "local text"
    assert item.title == "No captions"
    cached = json.loads((tmp_path / "CETs0u10aSc.json").read_text(encoding="utf-8"))
    assert cached["source"] == "faster-whisper:small"
    assert cached["raw_text"] == "local text"


def test_fetch_transcript_uses_cache_without_ytdlp(monkeypatch, tmp_path):
    cache = tmp_path / "CETs0u10aSc.json"
    cache.write_text(
        json.dumps(
            {
                "id": "yt:CETs0u10aSc",
                "url": "https://www.youtube.com/watch?v=CETs0u10aSc",
                "title": "Cached title",
                "duration_seconds": 42,
                "source": "faster-whisper:small",
                "raw_text": "cached text",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    item = ContentItem(
        id="yt:CETs0u10aSc",
        kind="video",
        source="youtube",
        url="https://www.youtube.com/watch?v=CETs0u10aSc",
    )

    assert youtube.fetch_transcript(item, cache_dir=tmp_path) == "cached text"
    assert item.title == "Cached title"
    assert item.duration_seconds == 42


def test_transcribe_with_whisper_uses_downloaded_audio(monkeypatch, tmp_path):
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"audio")

    def fake_download(item, target_dir: Path, cookies_file=None):
        target = target_dir / audio.name
        target.write_bytes(audio.read_bytes())
        return target

    class FakeWhisperModel:
        def __init__(self, model_size, device, compute_type):
            assert model_size == "tiny"
            assert device == "cpu"
            assert compute_type == "int8"

        def transcribe(self, path, language=None, vad_filter=True):
            assert Path(path).name == "audio.m4a"
            assert language == "zh"
            assert vad_filter is True
            segments = [
                SimpleNamespace(text=" 第一段 "),
                SimpleNamespace(text=""),
                SimpleNamespace(text="第二段"),
            ]
            return segments, SimpleNamespace(duration=12.8)

    monkeypatch.setattr(youtube, "_download_audio", fake_download)
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeWhisperModel),
    )
    item = ContentItem(
        id="yt:abc",
        kind="video",
        source="youtube",
        url="https://www.youtube.com/watch?v=abc",
    )

    text = youtube._transcribe_with_whisper(
        item,
        model_size="tiny",
        language="zh",
        device="cpu",
        compute_type="int8",
    )

    assert text == "第一段\n第二段"
    assert item.duration_seconds == 12


def test_vtt_segments_preserve_timing_and_repeated_speech():
    vtt = ('WEBVTT\n\nintro\n00:01.250 --> 00:03.500 align:start\n'
           '<c>Hello &amp; welcome</c>\n\n00:05.000 --> 00:07.000\nHello &amp; welcome\n')
    assert youtube.vtt_to_segments(vtt) == [
        {'start': 1.25, 'end': 3.5, 'text': 'Hello & welcome'},
        {'start': 5.0, 'end': 7.0, 'text': 'Hello & welcome'},
    ]


def test_json3_segments_require_real_valid_timestamps():
    segments = youtube.json3_to_segments({'events': [
        {'tStartMs': 1200, 'dDurationMs': 2400, 'segs': [{'utf8': 'Hello'}, {'utf8': ' world'}]},
        {'tStartMs': 10, 'dDurationMs': 0, 'segs': [{'utf8': 'empty duration'}]},
        {'segs': [{'utf8': 'untimed'}]},
    ]})
    assert len(segments) == 1
    assert segments[0]['start'] == pytest.approx(1.2)
    assert segments[0]['end'] == pytest.approx(3.6)
    assert segments[0]['text'] == 'Hello world'


def test_fetch_backfills_text_only_cache_with_caption_timestamps(monkeypatch, tmp_path):
    item = ContentItem(id='yt:CETs0u10aSc', kind='video', source='youtube',
                       url='https://youtu.be/CETs0u10aSc')
    youtube._write_cached_transcript(item, 'old cached text', tmp_path, source='legacy')

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, *args, **kwargs):
            return {'subtitles': {'en': [{'ext': 'vtt', 'url': 'https://example.test/subs'}]}}

    monkeypatch.setitem(sys.modules, 'yt_dlp', SimpleNamespace(YoutubeDL=FakeYDL))
    monkeypatch.setattr(youtube.urllib.request, 'urlopen', lambda *args, **kwargs:
                        io.BytesIO(b'WEBVTT\n\n00:00:02.000 --> 00:00:04.500\nnew timed text'))
    assert youtube.fetch_transcript(item, cache_dir=tmp_path, require_segments=True) == 'new timed text'
    assert youtube.read_transcript_segments(item, tmp_path) == [
        {'start': 2.0, 'end': 4.5, 'text': 'new timed text'}]
    monkeypatch.setitem(sys.modules, 'yt_dlp', None)
    assert youtube.fetch_transcript(item, cache_dir=tmp_path, require_segments=True) == 'new timed text'


def test_whisper_records_real_segment_times(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube, '_download_audio', lambda *args, **kwargs: tmp_path / 'audio.m4a')

    class FakeWhisper:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, *args, **kwargs):
            return iter([SimpleNamespace(start=1.5, end=3.0, text=' speech ')]), SimpleNamespace(duration=4)

    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=FakeWhisper))
    item = ContentItem(id='yt:CETs0u10aSc', kind='video', source='youtube', url='https://youtu.be/CETs0u10aSc')
    segments = []
    assert youtube._transcribe_with_whisper(item, segment_sink=segments) == 'speech'
    assert segments == [{'start': 1.5, 'end': 3.0, 'text': 'speech'}]


def test_hls_caption_segments_do_not_assume_transport_times_are_video_offsets(monkeypatch):
    bodies = {
        'https://example.test/index': '#EXTM3U\na.vtt\nb.vtt',
        'https://example.test/a.vtt': 'WEBVTT\n\n00:00:01 --> 00:00:03\nfirst',
        'https://example.test/b.vtt': 'WEBVTT\nX-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:900000\n\n00:00:01 --> 00:00:03\nsecond',
    }
    monkeypatch.setattr(youtube.urllib.request, 'urlopen', lambda url, **kwargs: io.BytesIO(bodies[url].encode()))
    text, segments = youtube._fetch_caption_data('https://example.test/index')
    assert text == 'first\nsecond'
    assert segments == []
    assert youtube.vtt_to_segments(bodies['https://example.test/b.vtt']) == []


def test_segment_cache_rejects_invalid_timings(tmp_path):
    item = ContentItem(id='yt:CETs0u10aSc', kind='video', source='youtube', url='https://youtu.be/CETs0u10aSc')
    youtube._write_cached_transcript(item, 'text', tmp_path, 'test', segments=[
        {'start': -1, 'end': 2, 'text': 'negative'},
        {'start': 1, 'end': float('inf'), 'text': 'infinite'},
        {'start': 3, 'end': 2, 'text': 'reversed'},
    ])
    assert youtube.read_transcript_segments(item, tmp_path) == []


@pytest.mark.parametrize('data', [[], {'events': None}, {'events': [None]},
                                 {'events': [{'segs': None}]},
                                 {'events': [{'segs': [42]}]},
                                 {'events': [{'segs': [{'utf8': 42}]}]}])
def test_malformed_json3_raises_parse_error(monkeypatch, data):
    monkeypatch.setattr(youtube.urllib.request, 'urlopen', lambda *args, **kwargs:
                        io.BytesIO(json.dumps(data).encode()))
    with pytest.raises(ValueError):
        youtube._fetch_caption_data('https://example.test/subs')


def test_concurrent_transcript_cache_writes_use_distinct_temporary_files(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    item = ContentItem(id='yt:CETs0u10aSc', kind='video', source='youtube', url='https://youtu.be/CETs0u10aSc')
    original_replace = youtube.os.replace
    barrier = threading.Barrier(2)
    temporary_paths = []
    thread_state = threading.local()

    def synchronized_replace(source, target):
        if not getattr(thread_state, 'started', False):
            thread_state.started = True
            temporary_paths.append(source)
            barrier.wait(timeout=5)
        original_replace(source, target)

    monkeypatch.setattr(youtube.os, 'replace', synchronized_replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(youtube._write_cached_transcript, item, text, tmp_path, 'test')
                   for text in ['first', 'second']]
        for future in futures:
            future.result()
    assert len(set(temporary_paths)) == 2
    assert youtube._read_cached_transcript(item, tmp_path) in {'first', 'second'}
    assert list(tmp_path.glob('*.tmp')) == []


def test_transcript_cache_retries_transient_windows_replace_failure(monkeypatch, tmp_path):
    item = ContentItem(id='yt:CETs0u10aSc', kind='video', source='youtube', url='https://youtu.be/CETs0u10aSc')
    original_replace = youtube.os.replace
    calls = []
    delays = []

    def transient_replace(source, target):
        calls.append(source)
        if len(calls) == 1:
            raise PermissionError('Windows temporary sharing conflict')
        original_replace(source, target)

    monkeypatch.setattr(youtube.os, 'replace', transient_replace)
    monkeypatch.setattr(youtube.time, 'sleep', delays.append)
    youtube._write_cached_transcript(item, 'complete text', tmp_path, 'test')
    assert len(calls) == 2 and calls[0] == calls[1]
    assert delays == [0.02]
    assert youtube._read_cached_transcript(item, tmp_path) == 'complete text'
    assert list(tmp_path.glob('*.tmp')) == []


def test_transcript_cache_persistent_replace_failure_is_bounded(monkeypatch, tmp_path):
    item = ContentItem(id='yt:CETs0u10aSc', kind='video', source='youtube', url='https://youtu.be/CETs0u10aSc')
    calls = []
    delays = []

    def denied_replace(source, target):
        calls.append(source)
        raise PermissionError('Permanent denial')

    monkeypatch.setattr(youtube.os, 'replace', denied_replace)
    monkeypatch.setattr(youtube.time, 'sleep', delays.append)
    with pytest.raises(PermissionError):
        youtube._write_cached_transcript(item, 'text', tmp_path, 'test')
    assert len(calls) == 6
    assert len(delays) == 5
    assert list(tmp_path.glob('*.tmp')) == []


def test_legacy_entire_transcript_in_short_cue_requires_real_backfill(monkeypatch, tmp_path):
    item = ContentItem(id='yt:TsS_XuOmX7s', kind='video', source='youtube', url='https://youtu.be/TsS_XuOmX7s')
    transcript = 'A complete five minute transcript incorrectly assigned to the first cue. ' * 40
    (tmp_path / 'TsS_XuOmX7s.json').write_text(json.dumps({
        'source': 'caption:en', 'duration_seconds': 315, 'raw_text': transcript,
        'segments': [{'start': .259, 'end': 3.309, 'text': transcript}],
    }), encoding='utf-8')
    assert youtube.read_transcript_segments(item, tmp_path) == []
    assert youtube._read_cached_transcript(item, tmp_path) == transcript

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, *args, **kwargs):
            return {'duration': 315, 'subtitles': {'en': [{'ext': 'vtt', 'url': 'https://example.test/subs'}]}}

    monkeypatch.setitem(sys.modules, 'yt_dlp', SimpleNamespace(YoutubeDL=FakeYDL))
    monkeypatch.setattr(youtube.urllib.request, 'urlopen', lambda *a, **kw: io.BytesIO(
        b'WEBVTT\n\n00:00:00.259 --> 00:00:03.309\nFirst real sentence\n\n00:04:00.000 --> 00:04:05.000\nLater real sentence'))
    youtube.fetch_transcript(item, cache_dir=tmp_path, require_segments=True)
    assert youtube.read_transcript_segments(item, tmp_path) == [
        {'start': .259, 'end': 3.309, 'text': 'First real sentence'},
        {'start': 240, 'end': 245, 'text': 'Later real sentence'},
    ]


def test_plausibility_guard_preserves_short_fast_cues_numbers_and_long_normal_cues():
    segments = [
        {'start': 0, 'end': .1, 'text': '2026 10 02 1234567890'},
        {'start': 1, 'end': 1.01, 'text': '短字幕'},
        {'start': 2, 'end': 22, 'text': ('A reasonably long caption with spoken context. ' * 15).strip()},
    ]
    assert youtube._valid_segments(segments) == segments


def test_corrupted_long_cue_invalidates_whole_timeline_not_partial_clip_selection():
    segments = [{'start': 0, 'end': 2, 'text': 'Normal introduction'},
                {'start': 3, 'end': 6, 'text': 'Entire transcript ' * 100}]
    assert youtube._valid_segments(segments) == []
