#!/usr/bin/env python3
"""Create a retimed SRT from the same timestamp plan used for video cuts."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import load_segment_plan, require_file, write_srt_for_segments


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("srt", type=Path, help="Source SRT")
    ap.add_argument("plan", type=Path, help="CSV/TXT plan with start,end rows")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output SRT (default: <source>.cut.srt)",
    )
    args = ap.parse_args()

    require_file(args.srt, "SRT")
    segments = load_segment_plan(args.plan)
    output = args.output or Path(f"{args.srt.with_suffix('')}.cut.srt")
    count = write_srt_for_segments(args.srt, segments, output)
    print(f"SRT cues written: {count} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
