#!/usr/bin/env python3
"""Merge two animations/videos into one longer animation.

The script normalizes both inputs to the same size and FPS before concatenating,
so it works even when the two source animations have different dimensions.

Examples:
    python3 merge_animations.py "intro.mp4" "main.mp4" -o "combined.mp4"
    python3 merge_animations.py "a.gif" "b.gif" -o "combined.gif" --fps 24
    python3 merge_animations.py "a.mov" "b.mov" -o "combined.mp4" --target 1920x1080 --fit crop
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import FFMPEG, probe_json, require_ffmpeg, require_file, run


def parse_target(value: str) -> tuple[int, int]:
    raw = str(value or "").strip().lower()
    if "x" not in raw:
        raise argparse.ArgumentTypeError("--target must look like 1920x1080")
    left, right = raw.split("x", 1)
    try:
        width = int(left)
        height = int(right)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--target must use integer dimensions") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("--target dimensions must be positive")
    return make_even(width), make_even(height)


def make_even(value: int) -> int:
    return value if value % 2 == 0 else value - 1


def video_stream_info(path: Path) -> tuple[int, int, float]:
    data = probe_json(path)
    stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not stream:
        raise SystemExit(f"No video stream found: {path}")

    width = make_even(int(stream.get("width") or 0))
    height = make_even(int(stream.get("height") or 0))
    if width <= 0 or height <= 0:
        raise SystemExit(f"Could not read video dimensions: {path}")

    fps = parse_rate(stream.get("avg_frame_rate")) or parse_rate(stream.get("r_frame_rate")) or 30.0
    return width, height, fps


def parse_rate(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    if "/" in value:
        left, right = value.split("/", 1)
        try:
            numerator = float(left)
            denominator = float(right)
        except ValueError:
            return None
        if denominator == 0:
            return None
        return numerator / denominator
    try:
        return float(value)
    except ValueError:
        return None


def fit_filter(label: str, width: int, height: int, fps: float, fit: str, background: str) -> str:
    if fit == "crop":
        body = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )
    elif fit == "stretch":
        body = f"scale={width}:{height}"
    else:
        body = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={background}"
        )
    return f"[{label}:v]{body},setsar=1,fps={fps:.3f}[v{label}]"


def build_filter(width: int, height: int, fps: float, fit: str, background: str, gif: bool) -> str:
    first = fit_filter("0", width, height, fps, fit, background)
    second = fit_filter("1", width, height, fps, fit, background)
    if gif:
        return (
            f"{first};{second};"
            "[v0][v1]concat=n=2:v=1:a=0,split[base][palette_src];"
            "[palette_src]palettegen[palette];"
            "[base][palette]paletteuse[v]"
        )
    return f"{first};{second};[v0][v1]concat=n=2:v=1:a=0,format=yuv420p[v]"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("first", type=Path, help="First animation/video")
    ap.add_argument("second", type=Path, help="Second animation/video appended after the first")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output file (default: <first>.merged.mp4)",
    )
    ap.add_argument(
        "--target",
        type=parse_target,
        default=None,
        help="Output dimensions, e.g. 1920x1080. Default: first input dimensions",
    )
    ap.add_argument(
        "--fps",
        type=float,
        default=None,
        help="Output frame rate. Default: first input frame rate",
    )
    ap.add_argument(
        "--fit",
        choices=("contain", "crop", "stretch"),
        default="contain",
        help="How to fit mismatched aspect ratios (default: contain)",
    )
    ap.add_argument(
        "--background",
        default="black",
        help="Pad color for --fit contain (default: black)",
    )
    ap.add_argument("--crf", type=int, default=18, help="x264 CRF for MP4/MOV output")
    ap.add_argument("--preset", default="veryfast", help="x264 preset for MP4/MOV output")
    ap.add_argument("--gif-loop", type=int, default=0, help="GIF loop count; 0 means forever")
    ap.add_argument("--dry-run", action="store_true", help="Print ffmpeg command only")
    args = ap.parse_args()

    require_file(args.first, "First animation")
    require_file(args.second, "Second animation")
    require_ffmpeg()

    first_width, first_height, first_fps = video_stream_info(args.first)
    width, height = args.target or (first_width, first_height)
    fps = args.fps if args.fps and args.fps > 0 else first_fps
    output = args.output or Path(f"{args.first.with_suffix('')}.merged.mp4")
    output.parent.mkdir(parents=True, exist_ok=True)

    gif_output = output.suffix.lower() == ".gif"
    filter_graph = build_filter(width, height, fps, args.fit, args.background, gif_output)

    cmd = [
        FFMPEG,
        "-y",
        "-i",
        str(args.first),
        "-i",
        str(args.second),
        "-filter_complex",
        filter_graph,
        "-map",
        "[v]",
    ]
    if gif_output:
        cmd += ["-loop", str(args.gif_loop), str(output)]
    else:
        cmd += [
            "-c:v",
            "libx264",
            "-preset",
            args.preset,
            "-crf",
            str(args.crf),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]

    print(f"First : {args.first}")
    print(f"Second: {args.second}")
    print(f"Output: {output}")
    print(f"Size  : {width}x{height} / {fps:.3f} fps / fit={args.fit}")
    run(cmd, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"Done: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
