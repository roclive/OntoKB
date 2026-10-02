#!/usr/bin/env python3
"""Generate an SRT subtitle file with OpenAI's transcription API.

This uses OpenAI-hosted transcription models instead of local Whisper. The
default model is gpt-4o-transcribe-diarize because it returns timestamped
segments that can be converted into SRT cues.

Set your API key in the environment before running:
    export OPENAI_API_KEY="..."

Usage:
    python3 generate_srt_openai.py "input.mp4"
    python3 generate_srt_openai.py "input.mp4" -l zh -o "input.srt"
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


_FFMPEG_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
_FFPROBE_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffprobe"
FFMPEG = _FFMPEG_FULL if os.path.exists(_FFMPEG_FULL) else "ffmpeg"
FFPROBE = _FFPROBE_FULL if os.path.exists(_FFPROBE_FULL) else "ffprobe"
TRANSCRIPTION_URL = "https://api.openai.com/v1/audio/transcriptions"
DEFAULT_OPENAI_MODEL = "gpt-4o-transcribe-diarize"
OPENAI_MODELS = (
    "gpt-4o-transcribe-diarize",
    "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe",
)
LOCAL_WHISPER_MODEL_NAMES = {"tiny", "base", "small", "medium", "large", "large-v2", "large-v3"}


def fmt_ts(seconds: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def require_binary(binary: str, label: str) -> None:
    if os.path.isabs(binary):
        if not Path(binary).exists():
            raise SystemExit(f"{label} not found: {binary}")
    elif shutil.which(binary) is None:
        raise SystemExit(f"{label} not found in PATH")


def run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)


def probe_duration(video_path: Path) -> float:
    require_binary(FFPROBE, "ffprobe")
    result = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def extract_audio_chunk(
    video_path: Path,
    output_path: Path,
    *,
    start: float,
    duration: float,
    bitrate: str,
) -> None:
    require_binary(FFMPEG, "ffmpeg")
    run(
        [
            FFMPEG,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(video_path),
            "-t",
            f"{duration:.3f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            bitrate,
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )


def multipart_body(fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
    boundary = f"----npocut-{uuid.uuid4().hex}"
    parts: list[bytes] = []

    for name, value in fields.items():
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )

    file_bytes = file_path.read_bytes()
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
            "Content-Type: audio/mp4\r\n\r\n"
        ).encode("utf-8")
        + file_bytes
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), boundary


def transcribe_chunk(
    chunk_path: Path,
    *,
    api_key: str,
    model: str,
    language: str | None,
    prompt: str | None,
    timeout: int,
) -> dict[str, Any]:
    fields = {
        "model": model,
        "response_format": "diarized_json" if model == DEFAULT_OPENAI_MODEL else "json",
    }
    if model == DEFAULT_OPENAI_MODEL:
        fields["chunking_strategy"] = "auto"
    if language:
        fields["language"] = language
    if prompt and model != DEFAULT_OPENAI_MODEL:
        fields["prompt"] = prompt

    body, boundary = multipart_body(fields, chunk_path)
    request = urllib.request.Request(
        TRANSCRIPTION_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error {exc.code}: {detail}") from exc


def response_to_segments(response: dict[str, Any], *, offset: float, fallback_end: float) -> list[dict[str, Any]]:
    raw_segments = response.get("segments") or []
    if raw_segments:
        segments = []
        for item in raw_segments:
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            segments.append(
                {
                    "start": offset + float(item.get("start", 0.0)),
                    "end": offset + float(item.get("end", 0.0)),
                    "text": text,
                }
            )
        return segments

    text = str(response.get("text", "")).strip()
    if not text:
        return []
    return [{"start": offset, "end": fallback_end, "text": text}]


def write_srt(segments: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        index = 1
        for segment in segments:
            text = str(segment["text"]).strip()
            start = float(segment["start"])
            end = float(segment["end"])
            if not text or end <= start:
                continue
            f.write(f"{index}\n")
            f.write(f"{fmt_ts(start)} --> {fmt_ts(end)}\n")
            f.write(f"{text}\n\n")
            index += 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("video", type=Path, help="Source video/audio file")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output SRT path (default: <video>.srt)",
    )
    ap.add_argument(
        "-m",
        "--model",
        default=DEFAULT_OPENAI_MODEL,
        help=(
            "OpenAI transcription model. Old Whisper sizes like medium are accepted "
            "and ignored for compatibility. Default: gpt-4o-transcribe-diarize"
        ),
    )
    ap.add_argument("-l", "--language", default=None, help="Input language code, e.g. zh, ja, en")
    ap.add_argument("--prompt", default=None, help="Optional transcription prompt/context")
    ap.add_argument(
        "--chunk-seconds",
        type=float,
        default=300.0,
        help="Audio chunk length in seconds (default: 300)",
    )
    ap.add_argument("--audio-bitrate", default="48k", help="Temporary audio bitrate (default: 48k)")
    ap.add_argument("--timeout", type=int, default=600, help="API request timeout in seconds")
    ap.add_argument("--keep-temp", action="store_true", help="Keep temporary audio chunks")
    args = ap.parse_args()

    if not args.video.exists():
        print(f"Video not found: {args.video}", file=sys.stderr)
        return 1
    if args.chunk_seconds <= 0:
        print("--chunk-seconds must be positive", file=sys.stderr)
        return 1

    model = args.model
    if model in LOCAL_WHISPER_MODEL_NAMES:
        print(
            f"Note: -m {model} is a local Whisper model size; using {DEFAULT_OPENAI_MODEL} instead.",
            file=sys.stderr,
        )
        model = DEFAULT_OPENAI_MODEL
    elif model not in OPENAI_MODELS:
        print(f"Unsupported OpenAI transcription model: {model}", file=sys.stderr)
        print(f"Supported: {', '.join(OPENAI_MODELS)}", file=sys.stderr)
        return 1

    if model != DEFAULT_OPENAI_MODEL:
        print(
            "Warning: only gpt-4o-transcribe-diarize returns timestamped segments for SRT; "
            "other models will create one cue per audio chunk.",
            file=sys.stderr,
        )

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is not set.", file=sys.stderr)
        print('Run: export OPENAI_API_KEY="your_api_key"', file=sys.stderr)
        return 1

    output_path = args.output or Path(f"{args.video.with_suffix('')}.srt")
    duration = probe_duration(args.video)
    if duration <= 0:
        print(f"Could not read a positive duration from: {args.video}", file=sys.stderr)
        return 1
    chunk_count = max(1, math.ceil(duration / args.chunk_seconds))
    all_segments: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="npocut_openai_srt_") as tmp_raw:
        tmp = Path(tmp_raw)
        print(f"Video duration: {fmt_ts(duration)}")
        print(f"Chunks: {chunk_count} x {args.chunk_seconds:.0f}s")
        print(f"Model: {model}")

        for idx in range(chunk_count):
            start = idx * args.chunk_seconds
            chunk_duration = min(args.chunk_seconds, duration - start)
            chunk_path = tmp / f"chunk_{idx + 1:04d}.m4a"
            print(f"[{idx + 1}/{chunk_count}] Extracting {fmt_ts(start)} -> {fmt_ts(start + chunk_duration)}")
            extract_audio_chunk(
                args.video,
                chunk_path,
                start=start,
                duration=chunk_duration,
                bitrate=args.audio_bitrate,
            )
            if chunk_path.stat().st_size > 24_000_000:
                raise SystemExit(
                    f"Chunk is over 24MB: {chunk_path}. "
                    "Use a smaller --chunk-seconds or lower --audio-bitrate."
                )

            print(f"[{idx + 1}/{chunk_count}] Transcribing with OpenAI")
            response = transcribe_chunk(
                chunk_path,
                api_key=api_key,
                model=model,
                language=args.language,
                prompt=args.prompt,
                timeout=args.timeout,
            )
            all_segments.extend(
                response_to_segments(response, offset=start, fallback_end=start + chunk_duration)
            )

        if args.keep_temp:
            keep_dir = Path(f"{args.video.with_suffix('')}.openai_chunks")
            if keep_dir.exists():
                shutil.rmtree(keep_dir)
            shutil.copytree(tmp, keep_dir)
            print(f"Kept chunks: {keep_dir}")

    write_srt(all_segments, output_path)
    print(f"SRT cues written: {len(all_segments)} -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
