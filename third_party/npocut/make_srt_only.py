#!/usr/bin/env python3
"""Generate only an SRT file using the local burn_subs.py transcription code."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video", type=Path, help="Source video")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output SRT (default: <video>.srt)",
    )
    ap.add_argument(
        "-m",
        "--model",
        default="small",
        help="Whisper model: tiny|base|small|medium|large-v3",
    )
    ap.add_argument(
        "-l",
        "--language",
        default=None,
        help="Force language code, e.g. en, ja, zh",
    )
    args = ap.parse_args()

    if not args.video.exists():
        raise SystemExit(f"Video not found: {args.video}")
    if not args.video.is_file():
        raise SystemExit(f"Video is not a file: {args.video}")

    from burn_subs import transcribe_to_srt

    output = args.output or Path(f"{args.video.with_suffix('')}.srt")
    output.parent.mkdir(parents=True, exist_ok=True)
    transcribe_to_srt(args.video, output, args.model, args.language)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
