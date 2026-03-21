"""Silence detection using ffmpeg silencedetect filter.

Runs ffmpeg's silencedetect audio filter on an input video,
parses the stderr output for silence_start/silence_end markers,
and writes structured JSON for downstream pipeline consumption.

Usage:
    python scripts/detect_silence.py <input.mp4> [--output .work/silences.json] \
        [--noise -30] [--min-duration 2.0]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect silence regions in a video using ffmpeg silencedetect.",
    )
    parser.add_argument("input", type=Path, help="Input video file (e.g. recording.mp4)")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".work/silences.json"),
        help="Output JSON path (default: .work/silences.json)",
    )
    parser.add_argument(
        "--noise",
        type=int,
        default=-30,
        help="Noise floor in dB — silence threshold (default: -30)",
    )
    parser.add_argument(
        "--min-duration",
        type=float,
        default=2.0,
        help="Minimum silence duration in seconds (default: 2.0)",
    )
    return parser.parse_args(argv)


def get_video_duration(input_path: Path) -> float:
    """Get total video duration in seconds via ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except FileNotFoundError:
        print(
            "ERROR: ffprobe not found. Install ffmpeg (includes ffprobe).",
            file=sys.stderr,
        )
        sys.exit(1)
    except (subprocess.CalledProcessError, ValueError) as exc:
        print(f"ERROR: Failed to get video duration: {exc}", file=sys.stderr)
        sys.exit(1)


def detect_silence(input_path: Path, noise_db: int, min_duration: float) -> list[dict[str, Any]]:
    """Run ffmpeg silencedetect and parse results from stderr."""
    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
        "-f", "null",
        "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print(
            "ERROR: ffmpeg not found. Install ffmpeg to use silence detection.",
            file=sys.stderr,
        )
        sys.exit(1)

    stderr = result.stderr

    starts = re.findall(r"silence_start:\s*([\d.]+)", stderr)
    ends = re.findall(r"silence_end:\s*([\d.]+)", stderr)

    silences: list[dict[str, Any]] = []
    for i, start_str in enumerate(starts):
        start_sec = float(start_str)
        if i < len(ends):
            end_sec = float(ends[i])
        else:
            end_sec = start_sec + min_duration

        duration_sec = round(end_sec - start_sec, 3)
        silences.append(
            {
                "startSec": round(start_sec, 3),
                "endSec": round(end_sec, 3),
                "durationSec": duration_sec,
            }
        )

    return silences


def print_summary(silences: list[dict[str, Any]], total_duration: float) -> None:
    """Print a human-readable summary of detected silence regions."""
    count = len(silences)
    total_silence = sum(s["durationSec"] for s in silences)
    pct = (total_silence / total_duration * 100) if total_duration > 0 else 0.0

    print(f"\n{'=' * 50}")
    print(f"Silence Detection Summary")
    print(f"{'=' * 50}")
    print(f"  Silence regions : {count}")
    print(f"  Total silence   : {total_silence:.3f}s")
    print(f"  Video duration  : {total_duration:.3f}s")
    print(f"  Silence ratio   : {pct:.1f}%")
    print(f"{'=' * 50}")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if not args.input.exists():
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"Detecting silence in: {args.input}")
    print(f"  noise={args.noise}dB, min_duration={args.min_duration}s")

    total_duration = get_video_duration(args.input)

    silences = detect_silence(
        input_path=args.input,
        noise_db=args.noise,
        min_duration=args.min_duration,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(silences, indent=2, ensure_ascii=False) + "\n")
    print(f"Saved {len(silences)} silence regions to: {args.output}")

    print_summary(silences, total_duration)


if __name__ == "__main__":
    main()
