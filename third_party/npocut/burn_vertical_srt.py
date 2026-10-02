#!/usr/bin/env python3
"""Burn an existing SRT into a 9:16 vertical video."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import require_file
from make_shorts import (
    default_subtitle_line_chars,
    default_subtitle_style,
    parse_target,
    render_short,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("video", type=Path, help="Source video")
    ap.add_argument("srt", type=Path, help="Existing SRT subtitle file")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output MP4 (default: <video>.vertical.subbed.mp4)",
    )
    ap.add_argument(
        "--vertical",
        choices=("crop", "blur", "pad"),
        default="crop",
        help="9:16 conversion mode",
    )
    ap.add_argument(
        "--target",
        default="1080x1920",
        help="Output dimensions for vertical modes",
    )
    ap.add_argument("--crf", type=int, default=19, help="x264 CRF")
    ap.add_argument("--preset", default="veryfast", help="x264 preset")
    ap.add_argument("--font-size", type=int, default=None, help="Burned subtitle font size")
    ap.add_argument("--margin-v", type=int, default=None, help="Burned subtitle bottom margin")
    ap.add_argument(
        "--subtitle-line-chars",
        type=int,
        default=None,
        help="Approximate characters per burned subtitle line",
    )
    ap.add_argument("--font-name", default="Helvetica", help="Burned subtitle font")
    ap.add_argument("--dry-run", action="store_true", help="Print ffmpeg command only")
    args = ap.parse_args()

    require_file(args.video, "Video")
    require_file(args.srt, "SRT")

    output_path = args.output or Path(f"{args.video.with_suffix('')}.vertical.subbed.mp4")
    target = parse_target(args.target)
    default_font_size, default_margin_v = default_subtitle_style(args.vertical)
    font_size = args.font_size if args.font_size is not None else default_font_size
    margin_v = args.margin_v if args.margin_v is not None else default_margin_v
    subtitle_line_chars = (
        args.subtitle_line_chars
        if args.subtitle_line_chars is not None
        else default_subtitle_line_chars(args.vertical)
    )

    print(f"Video : {args.video}")
    print(f"SRT   : {args.srt}")
    print(f"Output: {output_path}")
    print(f"Mode  : {args.vertical} / {args.target}")

    render_short(
        args.video,
        output_path,
        srt_path=args.srt,
        burn_srt=True,
        vertical_mode=args.vertical,
        target=target,
        crf=args.crf,
        preset=args.preset,
        font_size=font_size,
        margin_v=margin_v,
        font_name=args.font_name,
        subtitle_line_chars=subtitle_line_chars,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
