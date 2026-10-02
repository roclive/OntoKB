#!/usr/bin/env python3
"""Search or list SRT cues with timestamps for picking cut points."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import format_clock, parse_srt, require_file


def cue_text(lines: tuple[str, ...]) -> str:
    return " ".join(line.strip() for line in lines if line.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("srt", type=Path, help="Source SRT")
    ap.add_argument("-q", "--query", default=None, help="Text or regex to search")
    ap.add_argument(
        "-c",
        "--context",
        type=int,
        default=1,
        help="Neighbor cues to show around matches",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="List all cues. Default when --query is omitted.",
    )
    ap.add_argument(
        "--ignore-case",
        action="store_true",
        default=True,
        help="Case-insensitive search (default)",
    )
    args = ap.parse_args()

    require_file(args.srt, "SRT")
    cues = parse_srt(args.srt)
    if not cues:
        raise SystemExit(f"No cues found in {args.srt}")

    if args.query:
        flags = re.I if args.ignore_case else 0
        pattern = re.compile(args.query, flags)
        matched = {idx for idx, cue in enumerate(cues) if pattern.search(cue_text(cue.lines))}
        show: set[int] = set()
        for idx in matched:
            for neighbor in range(idx - args.context, idx + args.context + 1):
                if 0 <= neighbor < len(cues):
                    show.add(neighbor)
    else:
        show = set(range(len(cues)))

    for idx in sorted(show):
        cue = cues[idx]
        mark = "*" if args.query and idx in matched else " "
        print(
            f"{mark} {idx + 1:04d}  {format_clock(cue.start)} -> "
            f"{format_clock(cue.end)}  {cue_text(cue.lines)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
