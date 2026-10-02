#!/usr/bin/env python3
"""Print video duration, size, frame rate, and audio stream summary."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import format_clock, probe_json, require_file


def _fps(value: str) -> str:
    if not value or value == "0/0":
        return "-"
    if "/" not in value:
        return value
    num, den = value.split("/", 1)
    try:
        return f"{float(num) / float(den):.3f}"
    except (ValueError, ZeroDivisionError):
        return value


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video", type=Path, help="Video file")
    args = ap.parse_args()

    require_file(args.video, "Video")
    data = probe_json(args.video)
    duration = float(data.get("format", {}).get("duration", 0.0))
    print(f"File     : {args.video}")
    print(f"Duration : {format_clock(duration)} ({duration:.3f}s)")
    print(f"Container: {data.get('format', {}).get('format_long_name', '-')}")

    for stream in data.get("streams", []):
        kind = stream.get("codec_type")
        if kind == "video":
            print(
                "Video    : "
                f"{stream.get('codec_name', '-')} "
                f"{stream.get('width', '-')}x{stream.get('height', '-')} "
                f"{_fps(stream.get('avg_frame_rate', ''))} fps"
            )
        elif kind == "audio":
            print(
                "Audio    : "
                f"{stream.get('codec_name', '-')} "
                f"{stream.get('sample_rate', '-')} Hz "
                f"{stream.get('channels', '-')} ch"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
