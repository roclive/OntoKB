#!/usr/bin/env python3
"""
Burn an existing SRT subtitle file into an MP4 video (no transcription).

Use this when you already have a hand-edited or externally-generated SRT
and just want to render it into the video as a single output MP4.

Usage:
    python3 burn_existing_srt.py <input.mp4> <input.srt> [-o output.mp4]
"""

import argparse
import sys
from pathlib import Path

from burn_subs import burn_subs


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("video", type=Path, help="Source MP4 file")
    ap.add_argument("srt", type=Path, help="Existing SRT subtitle file")
    ap.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output MP4 (default: <video>.subbed.mp4)",
    )
    args = ap.parse_args()

    if not args.video.exists():
        print(f"Video not found: {args.video}", file=sys.stderr)
        return 1
    if not args.srt.exists():
        print(f"SRT not found: {args.srt}", file=sys.stderr)
        return 1

    output_path = args.output or Path(f"{args.video.with_suffix('')}.subbed.mp4")

    print(f"Video : {args.video}")
    print(f"SRT   : {args.srt}")
    print(f"Output: {output_path}")
    burn_subs(args.video, args.srt, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
