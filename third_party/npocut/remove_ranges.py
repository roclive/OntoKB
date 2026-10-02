#!/usr/bin/env python3
"""Remove timestamp ranges from a video and stitch the remaining timeline.

Range examples:

    00:03:12-00:03:28
    00:10:00,00:10:20,dead air
    00:24:15 --> 00:24:40 off-topic aside
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    Segment,
    cut_segments,
    format_clock,
    load_range_file,
    parse_range_line,
    probe_duration,
    require_file,
    subtract_ranges,
    write_srt_for_segments,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("video", type=Path, help="Source video")
    ap.add_argument(
        "-p",
        "--plan",
        type=Path,
        default=None,
        help="Text/CSV file with ranges to remove",
    )
    ap.add_argument(
        "-r",
        "--remove",
        action="append",
        default=[],
        help="Range to remove, repeatable. Example: -r 00:01:00-00:01:20",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output MP4 (default: <video>.clean.mp4)",
    )
    ap.add_argument("--srt", type=Path, default=None, help="Source SRT to retime")
    ap.add_argument(
        "--out-srt",
        type=Path,
        default=None,
        help="Retimed SRT path (default: <output>.srt when --srt is set)",
    )
    ap.add_argument(
        "--write-keep-plan",
        type=Path,
        default=None,
        help="Write the computed keep ranges as a CSV plan",
    )
    ap.add_argument(
        "--copy",
        action="store_true",
        help="Use stream copy for speed. Faster but less frame-accurate around cuts.",
    )
    ap.add_argument("--crf", type=int, default=18, help="x264 CRF when re-encoding")
    ap.add_argument("--preset", default="veryfast", help="x264 preset when re-encoding")
    ap.add_argument("--dry-run", action="store_true", help="Print ffmpeg commands only")
    ap.add_argument("--keep-temp", action="store_true", help="Keep temporary segment files")
    args = ap.parse_args()

    require_file(args.video, "Video")
    removals: list[Segment] = []
    if args.plan:
        removals.extend(load_range_file(args.plan))
    for spec in args.remove:
        segment = parse_range_line(spec)
        if segment:
            removals.append(segment)
    if not removals:
        raise SystemExit("No remove ranges supplied. Use --plan or --remove.")

    duration = probe_duration(args.video)
    keep_segments = subtract_ranges(duration, removals)
    print(f"Video duration: {format_clock(duration)}")
    print(f"Remove ranges : {len(removals)}")
    print(f"Keep segments : {len(keep_segments)}")

    if args.write_keep_plan and not args.dry_run:
        args.write_keep_plan.parent.mkdir(parents=True, exist_ok=True)
        with args.write_keep_plan.open("w", encoding="utf-8") as f:
            f.write("start,end,title\n")
            for idx, segment in enumerate(keep_segments, start=1):
                f.write(f"{format_clock(segment.start)},{format_clock(segment.end)},keep_{idx:02d}\n")
        print(f"Keep plan written: {args.write_keep_plan}")

    output = args.output or Path(f"{args.video.with_suffix('')}.clean.mp4")
    if args.srt:
        require_file(args.srt, "SRT")
        out_srt = args.out_srt or output.with_suffix(".srt")
        if args.dry_run:
            print(f"Would write retimed SRT: {out_srt}")
        else:
            count = write_srt_for_segments(args.srt, keep_segments, out_srt)
            print(f"SRT cues written: {count} -> {out_srt}")

    cut_segments(
        args.video,
        keep_segments,
        output,
        copy_streams=args.copy,
        crf=args.crf,
        preset=args.preset,
        dry_run=args.dry_run,
        keep_temp=args.keep_temp,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
