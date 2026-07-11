from __future__ import annotations

import sys
import json
from pathlib import Path
from types import SimpleNamespace

from ontokb.models import ContentItem
from ontokb.sources import youtube


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
