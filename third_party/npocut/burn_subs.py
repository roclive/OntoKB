#!/usr/bin/env python3
"""
Generate timestamped subtitles for an MP4 and burn them into a single output MP4.

Usage:
    python3 burn_subs.py <input.mp4> [-o output.mp4] [-m model] [-l lang]

Steps:
    1. Transcribe audio with faster-whisper -> SRT (with timestamps)
    2. Pause for human review/edit of the SRT file
    3. Burn the SRT into the video via ffmpeg subtitles filter -> single MP4
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel

# Homebrew's slim `ffmpeg` lacks libass. Prefer `ffmpeg-full` if installed
# (keg-only at /opt/homebrew/opt/ffmpeg-full/bin), else fall back to PATH.
_FFMPEG_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
FFMPEG = os.environ.get("NPOCUT_FFMPEG") or (_FFMPEG_FULL if os.path.exists(_FFMPEG_FULL) else "ffmpeg")


def fmt_ts(seconds: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def confirm_srt(srt_path: Path) -> bool:
    """Pause for the user to review/edit the SRT before burning.

    Returns True if the user confirms to proceed, False to abort.
    """
    print("", flush=True)
    print("=" * 60, flush=True)
    print(f"[REVIEW] SRT file generated: {srt_path}", flush=True)
    print("  - Open the file in your editor and fix any errors.", flush=True)
    print("  - Save your changes before continuing.", flush=True)
    print("=" * 60, flush=True)
    while True:
        try:
            ans = input("Proceed to burn subtitles? [y/N/r=re-show path]: ").strip().lower()
        except EOFError:
            print("\nAborted (no stdin).", flush=True)
            return False
        if ans in ("y", "yes"):
            return True
        if ans in ("", "n", "no"):
            print("Aborted by user.", flush=True)
            return False
        if ans == "r":
            print(f"  SRT path: {srt_path.resolve()}", flush=True)


def transcribe_to_srt(video_path: Path, srt_path: Path, model_size: str, language: str | None) -> None:
    print(f"[1/3] Loading whisper model: {model_size}", flush=True)
    # CPU + int8 is reliable on Mac without GPU dependencies
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print(f"      Transcribing: {video_path.name}", flush=True)
    segments, info = model.transcribe(
        str(video_path),
        language=language,
        vad_filter=True,
        beam_size=5,
    )
    print(f"      Detected language: {info.language} (p={info.language_probability:.2f})", flush=True)

    with srt_path.open("w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            text = seg.text.strip()
            if not text:
                continue
            f.write(f"{i}\n")
            f.write(f"{fmt_ts(seg.start)} --> {fmt_ts(seg.end)}\n")
            f.write(f"{text}\n\n")
            print(f"  [{fmt_ts(seg.start)} -> {fmt_ts(seg.end)}] {text}", flush=True)
    print(f"      SRT written: {srt_path}", flush=True)


def burn_subs(video_path: Path, srt_path: Path, output_path: Path) -> None:
    print(f"[3/3] Burning subtitles into: {output_path.name}", flush=True)

    # ffmpeg's subtitles filter has fragile quoting rules. To avoid issues with
    # spaces, colons, and single quotes in filenames, copy the SRT to a temp
    # directory with a simple name and run ffmpeg from there.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        local_srt = tmp_path / "subs.srt"
        local_in = tmp_path / "in.mp4"
        local_out = tmp_path / "out.mp4"
        shutil.copy2(srt_path, local_srt)
        shutil.copy2(video_path, local_in)

        # Inside force_style, commas separate ASS style fields, but commas also
        # delimit filter options in ffmpeg — escape them as `\,`.
        style = (
            "FontName=Helvetica,FontSize=18,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
            "Alignment=2,MarginV=40"
        ).replace(",", r"\,")
        vf = f"subtitles=subs.srt:force_style='{style}'"

        cmd = [
            FFMPEG, "-y",
            "-i", "in.mp4",
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-c:a", "copy",
            "-movflags", "+faststart",
            "out.mp4",
        ]
        print(f"      $ (cwd={tmp_path}) {' '.join(cmd)}", flush=True)
        subprocess.run(cmd, check=True, cwd=tmp_path)
        shutil.move(local_out, output_path)
    print(f"      Done: {output_path}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, help="Source MP4 file")
    ap.add_argument("-o", "--output", type=Path, default=None, help="Output MP4 (default: <input>.subbed.mp4)")
    ap.add_argument("-s", "--srt", type=Path, default=None, help="SRT path (default: <input>.srt)")
    ap.add_argument("-m", "--model", default="small",
                    help="Whisper model: tiny|base|small|medium|large-v3 (default: small)")
    ap.add_argument("-l", "--language", default=None,
                    help="Force language code (e.g. en, zh). Default: auto-detect.")
    ap.add_argument("--keep-srt", action="store_true", help="Keep the .srt file after burning (default: keep)")
    ap.add_argument("-y", "--yes", action="store_true",
                    help="Skip the human-confirmation step after SRT generation")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    stem = args.input.with_suffix("")
    srt_path = args.srt or Path(f"{stem}.srt")
    output_path = args.output or Path(f"{stem}.subbed.mp4")

    transcribe_to_srt(args.input, srt_path, args.model, args.language)
    if not args.yes:
        if not confirm_srt(srt_path):
            return 2
    burn_subs(args.input, srt_path, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
