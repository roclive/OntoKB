#!/usr/bin/env python3
"""Shared helpers for the npocut command line video tools."""

from __future__ import annotations

import csv
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


_FFMPEG_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
_FFPROBE_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffprobe"
FFMPEG = os.environ.get("NPOCUT_FFMPEG") or (
    _FFMPEG_FULL if os.path.exists(_FFMPEG_FULL) else "ffmpeg"
)
FFPROBE = os.environ.get("NPOCUT_FFPROBE") or (
    _FFPROBE_FULL if os.path.exists(_FFPROBE_FULL) else "ffprobe"
)


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    title: str = ""
    output: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    lines: tuple[str, ...]


def fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        fail(f"{label} not found: {path}")
    if not path.is_file():
        fail(f"{label} is not a file: {path}")


def require_ffmpeg() -> None:
    for binary, label in ((FFMPEG, "ffmpeg"), (FFPROBE, "ffprobe")):
        if os.path.isabs(binary):
            if not Path(binary).exists():
                fail(f"{label} not found: {binary}")
        elif shutil.which(binary) is None:
            fail(f"{label} not found in PATH")


def run(cmd: Sequence[str], *, cwd: Path | None = None, dry_run: bool = False) -> None:
    location = f" (cwd={cwd})" if cwd else ""
    print(f"$ {shlex.join([str(c) for c in cmd])}{location}", flush=True)
    if dry_run:
        return
    subprocess.run([str(c) for c in cmd], check=True, cwd=cwd)


def parse_timestamp(value: str | int | float) -> float:
    """Parse seconds, MM:SS, HH:MM:SS, or SRT HH:MM:SS,mmm into seconds."""
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds < 0:
            raise ValueError(f"negative timestamp: {value}")
        return seconds

    raw = str(value).strip()
    if not raw:
        raise ValueError("empty timestamp")
    raw = raw.replace(",", ".")
    raw = re.sub(r"\s*(seconds?|secs?|s)\s*$", "", raw, flags=re.I)

    if ":" not in raw:
        seconds = float(raw)
        if seconds < 0:
            raise ValueError(f"negative timestamp: {value}")
        return seconds

    parts = raw.split(":")
    if len(parts) == 2:
        hours = 0.0
        minutes = float(parts[0])
        seconds = float(parts[1])
    elif len(parts) == 3:
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
    else:
        raise ValueError(f"bad timestamp: {value}")

    total = hours * 3600 + minutes * 60 + seconds
    if total < 0:
        raise ValueError(f"negative timestamp: {value}")
    return total


def format_srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    ms_total = int(round(seconds * 1000))
    hours, ms_total = divmod(ms_total, 3_600_000)
    minutes, ms_total = divmod(ms_total, 60_000)
    secs, ms = divmod(ms_total, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def format_clock(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    ms_total = int(round(seconds * 1000))
    hours, ms_total = divmod(ms_total, 3_600_000)
    minutes, ms_total = divmod(ms_total, 60_000)
    secs, ms = divmod(ms_total, 1000)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"
    return f"{minutes:02d}:{secs:02d}.{ms:03d}"


def ffmpeg_seconds(seconds: float) -> str:
    return f"{seconds:.3f}"


def parse_range_line(line: str, *, line_no: int = 0) -> Segment | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    parts: list[str]
    if "," in stripped:
        parts = [part.strip() for part in next(csv.reader([stripped]))]
    elif "-->" in stripped:
        left, right = stripped.split("-->", 1)
        right_parts = right.strip().split(None, 1)
        parts = [left.strip(), right_parts[0].strip()]
        if len(right_parts) > 1:
            parts.append(right_parts[1].strip())
    elif ".." in stripped:
        left, right = stripped.split("..", 1)
        right_parts = right.strip().split(None, 1)
        parts = [left.strip(), right_parts[0].strip()]
        if len(right_parts) > 1:
            parts.append(right_parts[1].strip())
    elif "-" in stripped:
        left, right = re.split(r"\s*-\s*", stripped, maxsplit=1)
        right_parts = right.strip().split(None, 1)
        parts = [left.strip(), right_parts[0].strip()]
        if len(right_parts) > 1:
            parts.append(right_parts[1].strip())
    else:
        parts = stripped.split(None, 2)

    if len(parts) < 2:
        where = f" on line {line_no}" if line_no else ""
        raise ValueError(f"range needs at least start and end{where}: {line!r}")

    start = parse_timestamp(parts[0])
    end = parse_timestamp(parts[1])
    title = parts[2] if len(parts) >= 3 else ""
    if end <= start:
        where = f" on line {line_no}" if line_no else ""
        raise ValueError(f"range end must be after start{where}: {line!r}")
    return Segment(start=start, end=end, title=title)


def _looks_like_header(row: Sequence[str]) -> bool:
    names = {cell.strip().lower() for cell in row}
    return bool(names & {"start", "begin", "from", "in", "end", "stop", "to", "out"})


def _first_present(row: dict[str, str], names: Sequence[str], default: str = "") -> str:
    for name in names:
        if name in row and row[name].strip():
            return row[name].strip()
    return default


def load_segment_plan(path: Path) -> list[Segment]:
    require_file(path, "Plan")
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for raw in csv.reader(f):
            if not raw:
                continue
            if raw[0].strip().startswith("#"):
                continue
            rows.append([cell.strip() for cell in raw])

    if not rows:
        fail(f"Plan is empty: {path}")

    segments: list[Segment] = []
    if _looks_like_header(rows[0]):
        headers = [cell.strip().lower() for cell in rows[0]]
        for idx, row_values in enumerate(rows[1:], start=2):
            row = {headers[i]: row_values[i].strip() for i in range(min(len(headers), len(row_values)))}
            start_raw = _first_present(row, ("start", "begin", "from", "in"))
            end_raw = _first_present(row, ("end", "stop", "to", "out"))
            if not start_raw or not end_raw:
                raise ValueError(f"missing start/end on line {idx}: {row_values}")
            title = _first_present(row, ("title", "name", "label", "note"))
            output = _first_present(row, ("output", "file", "short", "short_id", "id"))
            start = parse_timestamp(start_raw)
            end = parse_timestamp(end_raw)
            if end <= start:
                raise ValueError(f"end must be after start on line {idx}: {row_values}")
            segments.append(Segment(start=start, end=end, title=title, output=output))
        return segments

    for idx, row in enumerate(rows, start=1):
        if len(row) == 1:
            segment = parse_range_line(row[0], line_no=idx)
            if segment:
                segments.append(segment)
            continue
        if len(row) < 2:
            raise ValueError(f"bad plan line {idx}: {row}")
        start = parse_timestamp(row[0])
        end = parse_timestamp(row[1])
        title = row[2] if len(row) >= 3 else ""
        output = row[3] if len(row) >= 4 else ""
        if end <= start:
            raise ValueError(f"end must be after start on line {idx}: {row}")
        segments.append(Segment(start=start, end=end, title=title, output=output))
    return segments


def load_range_file(path: Path) -> list[Segment]:
    require_file(path, "Range file")
    segments: list[Segment] = []
    saw_data = False
    with path.open("r", encoding="utf-8-sig") as f:
        for idx, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not saw_data:
                cells = [cell.strip() for cell in next(csv.reader([stripped]))]
                if _looks_like_header(cells):
                    saw_data = True
                    continue
            saw_data = True
            segment = parse_range_line(line, line_no=idx)
            if segment:
                segments.append(segment)
    if not segments:
        fail(f"Range file has no ranges: {path}")
    return segments


def probe_json(video_path: Path) -> dict:
    require_ffmpeg()
    cmd = [
        FFPROBE,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def probe_duration(video_path: Path) -> float:
    data = probe_json(video_path)
    try:
        return float(data["format"]["duration"])
    except (KeyError, ValueError) as exc:
        raise RuntimeError(f"could not read duration from {video_path}") from exc


def normalize_segments(segments: Iterable[Segment], *, duration: float | None = None) -> list[Segment]:
    normalized: list[Segment] = []
    for segment in segments:
        start = max(0.0, segment.start)
        end = segment.end
        if duration is not None:
            end = min(duration, end)
        if end <= start:
            continue
        normalized.append(Segment(start, end, segment.title, segment.output))
    if not normalized:
        fail("No usable segments after validation")
    return normalized


def subtract_ranges(duration: float, removals: Sequence[Segment]) -> list[Segment]:
    clipped = normalize_segments(removals, duration=duration)
    clipped.sort(key=lambda segment: (segment.start, segment.end))

    merged: list[Segment] = []
    for segment in clipped:
        if not merged or segment.start > merged[-1].end + 0.001:
            merged.append(segment)
        else:
            prev = merged[-1]
            merged[-1] = Segment(prev.start, max(prev.end, segment.end), prev.title)

    keep: list[Segment] = []
    cursor = 0.0
    for segment in merged:
        if segment.start > cursor + 0.001:
            keep.append(Segment(cursor, segment.start, "keep"))
        cursor = max(cursor, segment.end)
    if cursor < duration - 0.001:
        keep.append(Segment(cursor, duration, "keep"))
    if not keep:
        fail("Remove ranges cover the whole video; nothing left to export")
    return keep


def parse_srt(path: Path) -> list[Cue]:
    require_file(path, "SRT")
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n{2,}", text.strip())
    cues: list[Cue] = []
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        timing_idx = next((idx for idx, line in enumerate(lines) if "-->" in line), None)
        if timing_idx is None:
            continue
        timing = lines[timing_idx]
        start_raw, end_raw = timing.split("-->", 1)
        start = parse_timestamp(start_raw.strip().split()[0])
        end = parse_timestamp(end_raw.strip().split()[0])
        body = tuple(lines[timing_idx + 1 :])
        if body and end > start:
            cues.append(Cue(start=start, end=end, lines=body))
    return cues


def slice_cues(cues: Sequence[Cue], segments: Sequence[Segment], *, min_duration: float = 0.04) -> list[Cue]:
    output: list[Cue] = []
    cursor = 0.0
    for segment in segments:
        for cue in cues:
            overlap_start = max(cue.start, segment.start)
            overlap_end = min(cue.end, segment.end)
            if overlap_end - overlap_start < min_duration:
                continue
            new_start = cursor + (overlap_start - segment.start)
            new_end = cursor + (overlap_end - segment.start)
            output.append(Cue(start=new_start, end=new_end, lines=cue.lines))
        cursor += segment.duration
    return output


def write_srt(cues: Sequence[Cue], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for idx, cue in enumerate(cues, start=1):
            f.write(f"{idx}\n")
            f.write(f"{format_srt_timestamp(cue.start)} --> {format_srt_timestamp(cue.end)}\n")
            f.write("\n".join(cue.lines))
            f.write("\n\n")


def write_srt_for_segments(source_srt: Path, segments: Sequence[Segment], output_srt: Path) -> int:
    cues = parse_srt(source_srt)
    new_cues = slice_cues(cues, segments)
    write_srt(new_cues, output_srt)
    return len(new_cues)


def concat_file_line(path: Path) -> str:
    escaped = str(path).replace("'", "'\\''")
    return f"file '{escaped}'\n"


def cut_segments(
    video_path: Path,
    segments: Sequence[Segment],
    output_path: Path,
    *,
    copy_streams: bool = False,
    crf: int = 18,
    preset: str = "veryfast",
    audio_bitrate: str = "160k",
    dry_run: bool = False,
    keep_temp: bool = False,
) -> None:
    require_file(video_path, "Video")
    require_ffmpeg()
    if not segments:
        fail("No segments to export")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="npocut_"))
    print(f"Temporary directory: {tmp}", flush=True)

    try:
        part_paths: list[Path] = []
        for idx, segment in enumerate(segments, start=1):
            part_path = tmp / f"part_{idx:04d}.mp4"
            part_paths.append(part_path)
            print(
                f"[{idx}/{len(segments)}] {format_clock(segment.start)} -> "
                f"{format_clock(segment.end)} ({segment.duration:.2f}s) {segment.title}",
                flush=True,
            )
            cmd = [
                FFMPEG,
                "-y",
                "-ss",
                ffmpeg_seconds(segment.start),
                "-i",
                str(video_path),
                "-t",
                ffmpeg_seconds(segment.duration),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
            ]
            if copy_streams:
                cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
            else:
                cmd += [
                    "-c:v",
                    "libx264",
                    "-preset",
                    preset,
                    "-crf",
                    str(crf),
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    audio_bitrate,
                ]
            cmd += ["-movflags", "+faststart", str(part_path)]
            run(cmd, dry_run=dry_run)

        concat_list = tmp / "concat.txt"
        if not dry_run:
            with concat_list.open("w", encoding="utf-8") as f:
                for part_path in part_paths:
                    f.write(concat_file_line(part_path))

        concat_cmd = [
            FFMPEG,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        run(concat_cmd, dry_run=dry_run)
        if dry_run:
            print(f"Dry run complete. Output would be: {output_path}", flush=True)
        else:
            print(f"Done: {output_path}", flush=True)
    finally:
        if keep_temp:
            print(f"Kept temporary directory: {tmp}", flush=True)
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def safe_output_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", value.strip(), flags=re.UNICODE).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.lower().endswith(".mp4"):
        cleaned += ".mp4"
    return cleaned
