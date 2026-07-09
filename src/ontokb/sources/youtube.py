"""YouTube source: watch-later via Google Takeout CSV or a yt-dlp readable
playlist. Subtitle-first; audio+Whisper transcription is a later fallback (M2).
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

from ..models import ContentItem


def _vid(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url)
    return m.group(1) if m else hashlib.sha1(url.encode()).hexdigest()[:11]


def items_from_takeout_csv(path: str | Path) -> list[ContentItem]:
    """Parse a Google Takeout 'Watch later' playlist CSV.

    Takeout format: header rows describing the playlist, then a table whose
    first column is the video ID (column name varies by export locale), so we
    fall back to positional parsing.
    """
    items: list[ContentItem] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if not row:
                continue
            candidate = row[0].strip()
            if re.fullmatch(r"[\w-]{11}", candidate):
                url = f"https://www.youtube.com/watch?v={candidate}"
                items.append(ContentItem(
                    id=f"yt:{candidate}", kind="video", source="youtube", url=url,
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


def fetch_transcript(item: ContentItem, cookies_file: str | None = None,
                     langs: tuple[str, ...] = ("zh-Hans", "zh", "en")) -> str:
    """Fetch official or auto captions for a video and return plain text.
    Raises RuntimeError when no captions exist (M2 adds the Whisper fallback).
    """
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
                return vtt_to_text(resp.read().decode("utf-8", errors="replace"))
    raise RuntimeError(f"no captions for {item.url}; Whisper fallback not yet wired (M2)")


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
