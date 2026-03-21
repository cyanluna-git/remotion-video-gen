"""PySceneDetect scene change detection for screen recordings.

Uses AdaptiveDetector to identify scene transitions with
rolling-average filtering, avoiding false positives from
cursor movement and scrolling common in screen recordings.

Usage:
    python scripts/detect_scenes.py <input.mp4> [--output .work/scenes.json] \
        [--threshold 3.0] [--min-scene-len 15] [--min-content-val 15.0]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect scene changes in a video using PySceneDetect AdaptiveDetector.",
    )
    parser.add_argument("input", type=Path, help="Input video file (e.g. recording.mp4)")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".work/scenes.json"),
        help="Output JSON path (default: .work/scenes.json)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=3.0,
        help="Adaptive threshold — lower = more sensitive (default: 3.0)",
    )
    parser.add_argument(
        "--min-scene-len",
        type=int,
        default=15,
        help="Minimum scene length in frames (default: 15)",
    )
    parser.add_argument(
        "--min-content-val",
        type=float,
        default=15.0,
        help="Minimum content value — ignore frames below this score (default: 15.0)",
    )
    return parser.parse_args(argv)


def detect_scenes(
    input_path: Path,
    threshold: float,
    min_scene_len: int,
    min_content_val: float,
) -> list[dict[str, Any]]:
    """Run PySceneDetect on the input video and return scene list."""
    try:
        from scenedetect import AdaptiveDetector, detect, open_video
    except ImportError:
        print(
            "ERROR: scenedetect is not installed.\n"
            "Install with: pip install 'scenedetect[opencv]>=0.6.4'",
            file=sys.stderr,
        )
        sys.exit(1)

    video = open_video(str(input_path))
    raw_scenes = detect(
        video,
        AdaptiveDetector(
            adaptive_threshold=threshold,
            min_scene_len=min_scene_len,
            min_content_val=min_content_val,
        ),
    )

    scenes: list[dict[str, Any]] = []
    for idx, (start, end) in enumerate(raw_scenes):
        scenes.append(
            {
                "index": idx,
                "startSec": round(start.get_seconds(), 3),
                "endSec": round(end.get_seconds(), 3),
                "startTimecode": start.get_timecode(),
                "endTimecode": end.get_timecode(),
            }
        )
    return scenes


def print_summary(scenes: list[dict[str, Any]]) -> None:
    """Print a human-readable summary of detected scenes."""
    count = len(scenes)
    if count == 0:
        print("\nSummary: No scenes detected.")
        return

    total_duration = scenes[-1]["endSec"] - scenes[0]["startSec"]
    avg_length = total_duration / count if count > 0 else 0.0

    print(f"\n{'=' * 50}")
    print(f"Scene Detection Summary")
    print(f"{'=' * 50}")
    print(f"  Scenes detected : {count}")
    print(f"  Total duration  : {total_duration:.3f}s")
    print(f"  Avg scene length: {avg_length:.3f}s")
    print(f"{'=' * 50}")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if not args.input.exists():
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"Detecting scenes in: {args.input}")
    print(f"  threshold={args.threshold}, min_scene_len={args.min_scene_len}, min_content_val={args.min_content_val}")

    scenes = detect_scenes(
        input_path=args.input,
        threshold=args.threshold,
        min_scene_len=args.min_scene_len,
        min_content_val=args.min_content_val,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(scenes, indent=2, ensure_ascii=False) + "\n")
    print(f"Saved {len(scenes)} scenes to: {args.output}")

    print_summary(scenes)


if __name__ == "__main__":
    main()
