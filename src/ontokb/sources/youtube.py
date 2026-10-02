"""YouTube source: watch-later via Google Takeout CSV or a yt-dlp readable
playlist. Subtitle-first; audio+Whisper transcription is a later fallback (M2).
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import tempfile
import html
import math
import os
import time
import urllib.request
from urllib.parse import urljoin
from pathlib import Path

from ..models import ContentItem

DEFAULT_WHISPER_LANGUAGE = "zh"


def _vid(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url)
    return m.group(1) if m else hashlib.sha1(url.encode()).hexdigest()[:11]


def items_from_takeout_csv(path: str | Path) -> list[ContentItem]:
    """Parse a YouTube watch-later video list.

    Accepts two shapes in the same reader, since both are common in practice:
    - Real Google Takeout export: header rows + a table whose first column is
      an 11-char video ID (column name varies by export locale).
    - A plain list of one YouTube URL per line (e.g. hand-collected or
      exported by a browser extension) — every cell is scanned for a
      recognizable video ID.
    Deduplicates by video ID; skips cells that match neither shape.
    """
    items: list[ContentItem] = []
    seen: set[str] = set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            for cell in row:
                cell = cell.strip()
                if not cell:
                    continue
                vid = None
                if re.fullmatch(r"[\w-]{11}", cell):
                    vid = cell
                elif "youtube.com" in cell or "youtu.be" in cell:
                    m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", cell)
                    if m:
                        vid = m.group(1)
                if vid and vid not in seen:
                    seen.add(vid)
                    items.append(ContentItem(
                        id=f"yt:{vid}", kind="video", source="youtube",
                        url=f"https://www.youtube.com/watch?v={vid}",
                    ))
    return items


def items_from_playlist(playlist_url: str, cookies_file: str | None = None) -> list[ContentItem]:
    """Read a playlist with yt-dlp (flat, no downloads)."""
    import yt_dlp  # optional dependency: pip install ontokb[youtube]

    opts = {"extract_flat": True, "quiet": True, "skip_download": True}
    if cookies_file:
        opts["cookiefile"] = cookies_file
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(playlist_url, download=False)
    items = []
    for entry in info.get("entries") or []:
        vid = entry.get("id") or _vid(entry.get("url", ""))
        items.append(ContentItem(
            id=f"yt:{vid}",
            kind="video",
            source="youtube",
            url=f"https://www.youtube.com/watch?v={vid}",
            title=entry.get("title") or "",
            duration_seconds=int(entry["duration"]) if entry.get("duration") else None,
        ))
    return items


def fetch_transcript(
    item: ContentItem,
    cookies_file: str | None = None,
    langs: tuple[str, ...] = ("zh-Hans", "zh", "en"),
    whisper_model: str = "small",
    whisper_language: str | None = DEFAULT_WHISPER_LANGUAGE,
    whisper_device: str = "cpu",
    whisper_compute_type: str = "int8",
    cache_dir: str | Path | None = None,
    progress=None,
    require_segments: bool = False,
) -> str:
    """Fetch official or auto captions for a video and return plain text.
    Falls back to local faster-whisper transcription when captions are absent.
    With require_segments, backfill legacy caches and require real cue timing.
    """
    cached = _read_cached_transcript(item, cache_dir)
    if cached and (not require_segments or read_transcript_segments(item, cache_dir)):
        if progress:
            progress('已读取缓存文字稿。')
        return cached

    import yt_dlp

    opts = {
        "js_runtimes": {"node": {}},
        "noplaylist": True,
        "socket_timeout": 30,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": list(langs),
        "subtitlesformat": "vtt",
        "quiet": True,
    }
    if cookies_file:
        opts["cookiefile"] = cookies_file
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(item.url, download=False)
        item.title = item.title or info.get("title", "")
        item.duration_seconds = int(info.get("duration") or 0) or None
        for subs in (info.get("subtitles") or {}, info.get("automatic_captions") or {}):
            for lang in langs:
                for track in subs.get(lang) or []:
                    if track.get("ext") not in {"vtt", "json3"}:
                        continue
                    try:
                        text, timed_segments = _fetch_caption_data(track["url"])
                        if not valid_transcript(text):
                            raise ValueError("字幕响应不含有效正文")
                        if require_segments and not timed_segments:
                            raise ValueError("字幕缺少时间戳")
                    except (OSError, ValueError, KeyError):
                        if progress:
                            progress('字幕下载或解析失败，正在尝试其他字幕或音频转写…')
                        continue
                    _write_cached_transcript(item, text, cache_dir, source=f"caption:{lang}", segments=timed_segments)
                    return text
    timed_segments = []
    text = _transcribe_with_whisper(
        item,
        cookies_file=cookies_file,
        model_size=whisper_model,
        language=whisper_language,
        device=whisper_device,
        compute_type=whisper_compute_type,
        progress=progress,
        segment_sink=timed_segments,
    )
    if not valid_transcript(text):
        raise ValueError('音频转写未返回有效正文，未入库。')
    if require_segments and not timed_segments:
        raise ValueError('转写未返回时间戳，无法生成原声摘要。')
    _write_cached_transcript(item, text, cache_dir, source=f"faster-whisper:{whisper_model}", segments=timed_segments)
    return text


def valid_transcript(text: str) -> bool:
    """Reject transport payloads accidentally cached as spoken content."""
    stripped = text.lstrip('\ufeff \r\n\t')
    return bool(stripped) and not (
        stripped.startswith(('#EXTM3U', '#EXT-X-', '{', '[', '<?xml'))
        or re.match(r'(?i)<(?:!doctype|html|head|body|error)\b', stripped)
        or all(re.match(r'https?://', line.strip()) for line in stripped.splitlines() if line.strip())
    )


def _fetch_caption_text(url: str, depth: int = 0) -> str:
    return _fetch_caption_data(url, depth)[0]


def _fetch_caption_data(url: str, depth: int = 0) -> tuple[str, list[dict]]:
    """YouTube may serve an HLS playlist at a URL labelled as VTT."""
    if depth > 2:
        raise ValueError('字幕索引嵌套过深')
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = response.read().decode('utf-8-sig', errors='replace').strip()
    if payload.startswith('#EXTM3U'):
        segments = [line.strip() for line in payload.splitlines()
                    if line.strip() and not line.lstrip().startswith('#')]
        if not segments or len(segments) > 256 or '#EXT-X-STREAM-INF' in payload:
            raise ValueError('不支持的字幕索引')
        # Fetch every segment; never accept a partially downloaded transcript.
        parts = [_fetch_caption_data(urljoin(url, segment), depth + 1)
                 for segment in segments]
        text = '\n'.join(part[0] for part in parts)
        # HLS cue times belong to the transport timeline. Without the video
        # stream's presentation origin, MPEGTS cannot identify video offsets.
        # Retain text, but let timestamp-required callers try another track or
        # Whisper rather than silently clipping unrelated audio.
        timed_segments = []
    elif payload.startswith('{'):
        data = json.loads(payload)
        events = _json3_events(data)
        text = '\n'.join(_json3_event_text(event) for event in events)
        timed_segments = json3_to_segments(data)
    elif payload.startswith('WEBVTT') or '-->' in payload:
        text = vtt_to_text(payload)
        timed_segments = vtt_to_segments(payload)
    else:
        raise ValueError('字幕格式无法识别')
    if not valid_transcript(text):
        raise ValueError('字幕为空或仍是索引')
    return text, _valid_segments(timed_segments)


def _valid_segments(segments) -> list[dict]:
    """Normalize real time cues; never infer timing from plain transcript text."""
    result = []
    seen = set()
    if not isinstance(segments, list):
        return result
    for segment in segments:
        try:
            start, end = float(segment['start']), float(segment['end'])
            text = str(segment['text']).strip()
        except (TypeError, ValueError, KeyError):
            continue
        key = (start, end, text)
        if (math.isfinite(start) and math.isfinite(end) and 0 <= start < end
                and text and key not in seen):
            # Some legacy captions attached an entire transcript to the first
            # short cue. Such text is useful for reading, but cannot locate
            # speech. Invalidate the timeline so require_segments refetches real
            # cues; never manufacture evenly spaced timings from the text.
            characters = sum(not char.isspace() for char in text)
            if characters > 500 and characters / (end - start) > 100:
                return []
            result.append({'start': start, 'end': end, 'text': text})
            seen.add(key)
    return sorted(result, key=lambda segment: (segment['start'], segment['end']))


def _timestamp_seconds(value: str) -> float:
    parts = value.replace(',', '.').split(':')
    if len(parts) not in (2, 3):
        raise ValueError('Invalid subtitle timestamp')
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def vtt_to_segments(vtt: str) -> list[dict]:
    """Parse video-relative cues; reject ambiguous HLS transport offsets."""
    cues = []
    offset = 0.0
    if 'X-TIMESTAMP-MAP' in vtt:
        timestamp_map = re.search(r'X-TIMESTAMP-MAP=LOCAL:([^,\s]+),MPEGTS:(\d+)', vtt)
        if not timestamp_map:
            return []
        try:
            # Nonzero transport origins require stream-level synchronization.
            if int(timestamp_map[2]) != 0 or _timestamp_seconds(timestamp_map[1]) != 0:
                return []
        except ValueError:
            return []
    lines = vtt.splitlines()
    index = 0
    while index < len(lines):
        match = re.match(r'\s*([\d:.,]+)\s+-->\s+([\d:.,]+)', lines[index])
        index += 1
        if not match:
            continue
        body = []
        while index < len(lines) and lines[index].strip() and '-->' not in lines[index]:
            body.append(lines[index].strip())
            index += 1
        text = html.unescape(re.sub(r'<[^>]+>', '', '\n'.join(body))).strip()
        try:
            cues.append({'start': _timestamp_seconds(match[1]) + offset,
                         'end': _timestamp_seconds(match[2]) + offset, 'text': text})
        except ValueError:
            continue
    return _valid_segments(cues)


def _json3_events(data) -> list[dict]:
    if not isinstance(data, dict) or not isinstance(data.get('events', []), list):
        raise ValueError('字幕 JSON 格式无效')
    events = data.get('events', [])
    if not all(isinstance(event, dict) for event in events):
        raise ValueError('字幕 JSON 事件格式无效')
    return events


def _json3_event_text(event: dict) -> str:
    segments = event.get('segs', [])
    if not isinstance(segments, list) or not all(
        isinstance(segment, dict) and isinstance(segment.get('utf8', ''), str)
        for segment in segments
    ):
        raise ValueError('字幕 JSON 文本格式无效')
    return ''.join(segment.get('utf8', '') for segment in segments)


def json3_to_segments(data: dict) -> list[dict]:
    cues = []
    for event in _json3_events(data):
        text = _json3_event_text(event)
        try:
            start = float(event['tStartMs']) / 1000
            end = start + float(event['dDurationMs']) / 1000
            cues.append({'start': start, 'end': end, 'text': html.unescape(text)})
        except (KeyError, TypeError, ValueError):
            continue
    return _valid_segments(cues)


def read_transcript_segments(item: ContentItem, cache_dir: str | Path | None) -> list[dict]:
    path = _cache_path(item, cache_dir)
    if path is None:
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return _valid_segments(data.get('segments', [])) if isinstance(data, dict) else []
    except (OSError, ValueError):
        return []


def _cache_path(item: ContentItem, cache_dir: str | Path | None) -> Path | None:
    if cache_dir is None:
        return None
    return Path(cache_dir) / f"{_vid(item.url)}.json"


def _read_cached_transcript(item: ContentItem, cache_dir: str | Path | None) -> str:
    path = _cache_path(item, cache_dir)
    if path is None or not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    text = str(data.get("raw_text") or "")
    if not valid_transcript(text):
        return ""
    item.title = item.title or data.get("title", "")
    if data.get("duration_seconds") and not item.duration_seconds:
        item.duration_seconds = int(data["duration_seconds"])
    return text


def _write_cached_transcript(
    item: ContentItem,
    text: str,
    cache_dir: str | Path | None,
    source: str,
    segments: list[dict] | None = None,
) -> None:
    path = _cache_path(item, cache_dir)
    if path is None or not text.strip():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": item.id,
        "url": item.url,
        "title": item.title,
        "duration_seconds": item.duration_seconds,
        "source": source,
        "raw_text": text,
        "segments": _valid_segments(segments or []),
    }
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         prefix=path.stem + '-', suffix='.tmp',
                                         dir=path.parent, delete=False) as stream:
            tmp = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        # Windows can briefly deny replacement while another process or an
        # antivirus scanner holds the destination. Keep the completed temp
        # file intact during a bounded retry, then propagate persistent errors.
        for attempt in range(6):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.02 * (2 ** attempt))
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def _download_audio(item: ContentItem, target_dir: Path, cookies_file: str | None = None) -> Path:
    import yt_dlp

    opts = {
        "js_runtimes": {"node": {}},
        "socket_timeout": 30,
        "format": "bestaudio/best",
        "outtmpl": str(target_dir / "%(id)s.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
    }
    if cookies_file:
        opts["cookiefile"] = cookies_file
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(item.url, download=True)
        item.title = item.title or info.get("title", "")
        if info.get("duration") and not item.duration_seconds:
            item.duration_seconds = int(info["duration"])

    files = [p for p in target_dir.iterdir() if p.is_file() and not p.name.endswith(".part")]
    if not files:
        raise RuntimeError(f"failed to download audio for {item.url}")
    return max(files, key=lambda p: p.stat().st_size)


def _transcribe_with_whisper(
    item: ContentItem,
    cookies_file: str | None = None,
    model_size: str = "small",
    language: str | None = DEFAULT_WHISPER_LANGUAGE,
    device: str = "cpu",
    compute_type: str = "int8",
    progress=None,
    segment_sink: list[dict] | None = None,
) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            f"no captions for {item.url}; install faster-whisper for local transcription"
        ) from exc

    language = _normalize_whisper_language(language)
    with tempfile.TemporaryDirectory(prefix="ontokb-youtube-") as tmp:
        if progress:
            progress('未找到字幕，正在下载音频…')
        audio_path = _download_audio(item, Path(tmp), cookies_file=cookies_file)
        if progress:
            progress('音频已下载，正在加载本地转写模型（首次运行需下载模型）…')
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
        )
        if getattr(info, "duration", None) and not item.duration_seconds:
            item.duration_seconds = int(info.duration)
        lines = []
        last_minute = -1
        for segment in segments:
            if segment.text.strip():
                lines.append(segment.text.strip())
                if segment_sink is not None:
                    segment_sink.extend(_valid_segments([{
                        'start': getattr(segment, 'start', None),
                        'end': getattr(segment, 'end', None),
                        'text': segment.text.strip(),
                    }]))
            minute = int(getattr(segment, 'end', 0) / 60)
            if progress and minute != last_minute:
                total = (item.duration_seconds or 0) / 60
                progress(f'本地转写：已处理 {minute} / {total:.0f} 分钟音频…')
                last_minute = minute

    if not lines:
        raise RuntimeError(f"Whisper produced no transcript for {item.url}")
    return "\n".join(lines)


def _normalize_whisper_language(language: str | None) -> str | None:
    if language is None:
        return None
    language = language.strip()
    if not language or language.lower() == "auto":
        return None
    return language


def vtt_to_text(vtt: str) -> str:
    lines, seen = [], set()
    for line in vtt.splitlines():
        line = line.strip()
        if (not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
                or line.startswith(('X-TIMESTAMP-MAP', 'STYLE', 'REGION'))
                or "-->" in line or line.isdigit()):
            continue
        line = html.unescape(re.sub(r"<[^>]+>", "", line))
        if line and line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n".join(lines)
