"""YouTube source: watch-later via Google Takeout CSV or a yt-dlp readable
playlist. Subtitle-first; audio+Whisper transcription is a later fallback (M2).
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import tempfile
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
) -> str:
    """Fetch official or auto captions for a video and return plain text.
    Falls back to local faster-whisper transcription when captions are absent.
    """
    cached = _read_cached_transcript(item, cache_dir)
    if cached:
        return cached

    import yt_dlp

    opts = {
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
        subs = {**(info.get("subtitles") or {}), **(info.get("automatic_captions") or {})}
        for lang in langs:
            tracks = subs.get(lang)
            if not tracks:
                continue
            vtt = next((t for t in tracks if t.get("ext") == "vtt"), tracks[0])
            import urllib.request

            with urllib.request.urlopen(vtt["url"]) as resp:
                text = vtt_to_text(resp.read().decode("utf-8", errors="replace"))
                _write_cached_transcript(item, text, cache_dir, source=f"caption:{lang}")
                return text
    text = _transcribe_with_whisper(
        item,
        cookies_file=cookies_file,
        model_size=whisper_model,
        language=whisper_language,
        device=whisper_device,
        compute_type=whisper_compute_type,
    )
    _write_cached_transcript(item, text, cache_dir, source=f"faster-whisper:{whisper_model}")
    return text


def _cache_path(item: ContentItem, cache_dir: str | Path | None) -> Path | None:
    if cache_dir is None:
        return None
    return Path(cache_dir) / f"{_vid(item.url)}.json"


def _read_cached_transcript(item: ContentItem, cache_dir: str | Path | None) -> str:
    path = _cache_path(item, cache_dir)
    if path is None or not path.exists():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    text = str(data.get("raw_text") or "")
    if not text.strip():
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
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _download_audio(item: ContentItem, target_dir: Path, cookies_file: str | None = None) -> Path:
    import yt_dlp

    opts = {
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
) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            f"no captions for {item.url}; install faster-whisper for local transcription"
        ) from exc

    language = _normalize_whisper_language(language)
    with tempfile.TemporaryDirectory(prefix="ontokb-youtube-") as tmp:
        audio_path = _download_audio(item, Path(tmp), cookies_file=cookies_file)
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
        )
        if getattr(info, "duration", None) and not item.duration_seconds:
            item.duration_seconds = int(info.duration)
        lines = [segment.text.strip() for segment in segments if segment.text.strip()]

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
                or "-->" in line or line.isdigit()):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line and line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n".join(lines)
