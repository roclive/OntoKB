#!/usr/bin/env python3
"""Generate only an SRT subtitle file from a video.

This is the transcription-only version of burn_subs.py. It reuses
burn_subs.transcribe_to_srt, so timestamp formatting and Whisper settings stay
consistent with the subtitle-burning workflow.

Usage:
    python3 generate_srt.py "input.mp4"
    python3 generate_srt.py "input.mp4" -o "input.srt" -m medium -l ja
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("video", type=Path, help="Source video file")
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
        default="small",
        help="Whisper model: tiny|base|small|medium|large-v3 (default: small)",
    )
    ap.add_argument(
        "-l",
        "--language",
        default=None,
        help="Force language code, e.g. en, ja, zh. Default: auto-detect.",
    )
    args = ap.parse_args()

    if not args.video.exists():
        print(f"Video not found: {args.video}", file=sys.stderr)
        return 1
    if not args.video.is_file():
        print(f"Video is not a file: {args.video}", file=sys.stderr)
        return 1

    output = args.output or Path(f"{args.video.with_suffix('')}.srt")
    output.parent.mkdir(parents=True, exist_ok=True)

    from burn_subs import transcribe_to_srt

    transcribe_to_srt(args.video, output, args.model, args.language)
    print(f"Subtitle file ready: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
