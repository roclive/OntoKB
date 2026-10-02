#!/usr/bin/env python3
"""Batch export YouTube Shorts-style clips from a long video.

Plan CSV format:

    output,start,end,title
    short_01.mp4,00:01:10,00:01:58,hook
    short_02.mp4,00:12:04,00:12:53,first part
    short_02.mp4,00:13:20,00:13:42,second part

Rows with the same output are concatenated in row order.
"""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from collections import OrderedDict
from pathlib import Path

from common import (
    FFMPEG,
    Cue,
    Segment,
    cut_segments,
    fail,
    format_clock,
    load_segment_plan,
    parse_srt,
    require_file,
    require_ffmpeg,
    run,
    safe_output_name,
    write_srt,
    write_srt_for_segments,
)


def parse_target(value: str) -> tuple[int, int]:
    if "x" not in value.lower():
        fail("--target must look like 1080x1920")
    width_raw, height_raw = value.lower().split("x", 1)
    try:
        width = int(width_raw)
        height = int(height_raw)
    except ValueError:
        fail("--target must use integer dimensions, e.g. 1080x1920")
    if width <= 0 or height <= 0:
        fail("--target dimensions must be positive")
    return width, height


def subtitle_filter(font_size: int, margin_v: int, font_name: str) -> str:
    outline = max(1, min(3, round(font_size / 14)))
    style = (
        f"FontName={font_name},FontSize={font_size},PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,BorderStyle=1,Outline={outline},Shadow=0,"
        f"Alignment=2,MarginV={margin_v}"
    ).replace(",", r"\,")
    return f"subtitles=subs.srt:force_style='{style}'"


def base_video_filter(mode: str, width: int, height: int) -> str:
    if mode == "crop":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )
    if mode == "pad":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
        )
    if mode == "none":
        return ""
    raise ValueError(f"Unsupported simple filter mode: {mode}")


def default_subtitle_style(vertical_mode: str) -> tuple[int, int]:
    if vertical_mode == "none":
        return 18, 40
    return 10, 28


def default_subtitle_line_chars(vertical_mode: str) -> int:
    if vertical_mode == "none":
        return 42
    return 10


def visual_width(text: str) -> float:
    width = 0.0
    for char in text:
        width += 0.55 if char.isascii() else 1.0
    return width


def is_leading_punctuation(text: str) -> bool:
    return bool(text) and text[0] in ",，.。!！?？:：;；、)]}）】」』"


def wrap_subtitle_text(text: str, max_width: int) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9_.-]+|\s+|.", text.strip())
    if not tokens:
        return []

    lines: list[str] = []
    current = ""
    for token in tokens:
        if token.isspace():
            token = " "
        candidate = current + token
        if current and visual_width(candidate) > max_width and not is_leading_punctuation(token):
            lines.append(current.strip())
            current = token.lstrip()
        else:
            current = candidate

        while visual_width(current) > max_width:
            line = ""
            remaining = current
            for idx, char in enumerate(current):
                if line and visual_width(line + char) > max_width:
                    lines.append(line.strip())
                    remaining = current[idx:]
                    break
                line += char
            else:
                remaining = ""
            current = remaining.lstrip()

    if current.strip():
        lines.append(current.strip())

    cleaned: list[str] = []
    for line in lines:
        if cleaned and is_leading_punctuation(line):
            cleaned[-1] += line[0]
            line = line[1:].lstrip()
        if line:
            cleaned.append(line)
    return cleaned


def write_wrapped_srt(source: Path, output: Path, max_width: int) -> None:
    cues = parse_srt(source)
    wrapped = []
    for cue in cues:
        lines: list[str] = []
        for line in cue.lines:
            lines.extend(wrap_subtitle_text(line, max_width))
        wrapped.append(Cue(start=cue.start, end=cue.end, lines=tuple(lines)))
    write_srt(wrapped, output)


def render_short(
    input_clip: Path,
    output_path: Path,
    *,
    srt_path: Path | None,
    burn_srt: bool,
    vertical_mode: str,
    target: tuple[int, int],
    crf: int,
    preset: str,
    font_size: int,
    margin_v: int,
    font_name: str,
    subtitle_line_chars: int,
    dry_run: bool,
) -> None:
    require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = target

    if vertical_mode == "none" and not burn_srt:
        if dry_run:
            print(f"Would copy {input_clip} -> {output_path}")
        else:
            shutil.copy2(input_clip, output_path)
            print(f"Done: {output_path}")
        return

    with tempfile.TemporaryDirectory(prefix="npocut_short_render_") as tmp_raw:
        tmp = Path(tmp_raw)
        local_in = tmp / "in.mp4"
        local_out = tmp / "out.mp4"
        if not dry_run:
            shutil.copy2(input_clip, local_in)
            if burn_srt:
                if not srt_path:
                    fail("--burn-srt requires --srt")
                write_wrapped_srt(srt_path, tmp / "subs.srt", subtitle_line_chars)

        cmd = [FFMPEG, "-y", "-i", "in.mp4"]
        sub_filter = subtitle_filter(font_size, margin_v, font_name) if burn_srt else ""

        if vertical_mode == "blur":
            fc = (
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},gblur=sigma=28[bg];"
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[vbase]"
            )
            if burn_srt:
                fc += f";[vbase]{sub_filter},format=yuv420p[outv]"
            else:
                fc += ";[vbase]null[outv]"
            cmd += ["-filter_complex", fc, "-map", "[outv]", "-map", "0:a?"]
        else:
            filters = []
            base_filter = base_video_filter(vertical_mode, width, height)
            if base_filter:
                filters.append(base_filter)
            if burn_srt:
                filters.append(sub_filter)
            filters.append("format=yuv420p")
            cmd += ["-vf", ",".join(filters), "-map", "0:v:0", "-map", "0:a?"]

        cmd += [
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            "out.mp4",
        ]
        run(cmd, cwd=tmp, dry_run=dry_run)
        if not dry_run:
            shutil.move(local_out, output_path)
            print(f"Done: {output_path}")


def group_segments(segments: list[Segment]) -> OrderedDict[str, list[Segment]]:
    grouped: OrderedDict[str, list[Segment]] = OrderedDict()
    for idx, segment in enumerate(segments, start=1):
        output = safe_output_name(segment.output, f"short_{idx:02d}")
        grouped.setdefault(output, []).append(segment)
    return grouped


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("video", type=Path, help="Source long video")
    ap.add_argument("plan", type=Path, help="CSV plan with output,start,end rows")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=Path("shorts_out"),
        help="Directory for generated shorts",
    )
    ap.add_argument("--srt", type=Path, default=None, help="Source SRT to retime per short")
    ap.add_argument(
        "--burn-srt",
        action="store_true",
        help="Burn the retimed SRT into each short",
    )
    ap.add_argument(
        "--no-srt-output",
        action="store_true",
        help="Do not write sidecar SRT files",
    )
    ap.add_argument(
        "--vertical",
        choices=("crop", "blur", "pad", "none"),
        default="crop",
        help="9:16 conversion mode",
    )
    ap.add_argument(
        "--target",
        default="1080x1920",
        help="Output dimensions for vertical modes",
    )
    ap.add_argument(
        "--max-seconds",
        type=float,
        default=180.0,
        help="Warn when a short exceeds this duration; set 0 to disable",
    )
    ap.add_argument(
        "--strict-duration",
        action="store_true",
        help="Fail instead of warning when --max-seconds is exceeded",
    )
    ap.add_argument("--crf", type=int, default=19, help="x264 CRF for final shorts")
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
    ap.add_argument("--dry-run", action="store_true", help="Print ffmpeg commands only")
    ap.add_argument("--keep-temp", action="store_true", help="Keep temporary timeline files")
    args = ap.parse_args()

    require_file(args.video, "Video")
    if args.burn_srt and not args.srt:
        fail("--burn-srt requires --srt")
    if args.srt:
        require_file(args.srt, "SRT")

    target = parse_target(args.target)
    default_font_size, default_margin_v = default_subtitle_style(args.vertical)
    font_size = args.font_size if args.font_size is not None else default_font_size
    margin_v = args.margin_v if args.margin_v is not None else default_margin_v
    subtitle_line_chars = (
        args.subtitle_line_chars
        if args.subtitle_line_chars is not None
        else default_subtitle_line_chars(args.vertical)
    )
    segments = load_segment_plan(args.plan)
    grouped = group_segments(segments)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="npocut_shorts_"))
    print(f"Temporary directory: {tmp}")
    try:
        for idx, (output_name, short_segments) in enumerate(grouped.items(), start=1):
            output = args.out_dir / output_name
            total_duration = sum(segment.duration for segment in short_segments)
            print(
                f"\n[{idx}/{len(grouped)}] {output.name} "
                f"({len(short_segments)} segment(s), {total_duration:.2f}s)"
            )
            if args.max_seconds and total_duration > args.max_seconds:
                message = (
                    f"{output.name} is {total_duration:.2f}s, above "
                    f"--max-seconds {args.max_seconds:.2f}s"
                )
                if args.strict_duration:
                    fail(message)
                print(f"Warning: {message}")

            timeline_clip = tmp / f"timeline_{idx:03d}.mp4"
            timeline_srt = tmp / f"timeline_{idx:03d}.srt"

            cut_segments(
                args.video,
                short_segments,
                timeline_clip,
                crf=18,
                preset=args.preset,
                dry_run=args.dry_run,
                keep_temp=args.keep_temp,
            )

            final_srt = output.with_suffix(".srt")
            active_srt: Path | None = None
            if args.srt:
                if args.dry_run:
                    print(f"Would write retimed SRT: {final_srt}")
                    active_srt = final_srt
                else:
                    count = write_srt_for_segments(args.srt, short_segments, timeline_srt)
                    active_srt = timeline_srt
                    if not args.no_srt_output:
                        shutil.copy2(timeline_srt, final_srt)
                        print(f"SRT cues written: {count} -> {final_srt}")

            render_short(
                timeline_clip,
                output,
                srt_path=active_srt,
                burn_srt=args.burn_srt,
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

        if args.keep_temp:
            print(f"Kept outer temporary directory: {tmp}")
    finally:
        if not args.keep_temp:
            shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
