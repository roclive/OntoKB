#!/usr/bin/env python3
"""Export and reorder video ranges from a timestamp plan.

Plan CSV formats:

    start,end,title
    00:01:10,00:02:04,opening hook
    00:08:30,00:09:12,best explanation

Rows are exported in file order, so changing row order changes the final video.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import cut_segments, load_segment_plan, require_file, write_srt_for_segments


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("video", type=Path, help="Source video")
    ap.add_argument("plan", type=Path, help="CSV/TXT plan with start,end rows")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output MP4 (default: <video>.cut.mp4)",
    )
    ap.add_argument("--srt", type=Path, default=None, help="Source SRT to retime")
    ap.add_argument(
        "--out-srt",
        type=Path,
        default=None,
        help="Retimed SRT path (default: <output>.srt when --srt is set)",
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
    segments = load_segment_plan(args.plan)
    output = args.output or Path(f"{args.video.with_suffix('')}.cut.mp4")

    if args.srt:
        require_file(args.srt, "SRT")
        out_srt = args.out_srt or output.with_suffix(".srt")
        if args.dry_run:
            print(f"Would write retimed SRT: {out_srt}")
        else:
            count = write_srt_for_segments(args.srt, segments, out_srt)
            print(f"SRT cues written: {count} -> {out_srt}")

    cut_segments(
        args.video,
        segments,
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
