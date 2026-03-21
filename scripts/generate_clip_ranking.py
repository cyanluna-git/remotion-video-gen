"""Generate a canonical clip-ranking artifact from Step 2 analysis outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from clip_ranking import build_clip_ranking_artifact
    from multimodal_contracts import MultimodalContractError
    from scenario_generation import extract_transcript_segments, get_video_duration, load_json_file
except ModuleNotFoundError:
    from scripts.clip_ranking import build_clip_ranking_artifact
    from scripts.multimodal_contracts import MultimodalContractError
    from scripts.scenario_generation import (
        extract_transcript_segments,
        get_video_duration,
        load_json_file,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a canonical clip-ranking artifact from analysis data.",
    )
    parser.add_argument("--transcript", type=Path, default=None, help="Whisper transcript JSON file")
    parser.add_argument("--scenes", type=Path, default=None, help="Scene detection JSON file")
    parser.add_argument("--silences", type=Path, default=None, help="Silence detection JSON file")
    parser.add_argument("--video", type=Path, default=None, help="Video file for duration fallback")
    parser.add_argument(
        "--provider",
        default="heuristic",
        choices=["heuristic"],
        help="Clip-ranking provider (default: heuristic)",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output clip-ranking.json path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    transcript = load_json_file(args.transcript, "transcript") if args.transcript else None
    scenes = load_json_file(args.scenes, "scenes") if args.scenes else None
    silences = load_json_file(args.silences, "silences") if args.silences else None
    video_duration = get_video_duration(args.video) if args.video else None

    try:
        artifact = build_clip_ranking_artifact(
            transcript_segments=extract_transcript_segments(transcript),
            scenes=scenes if isinstance(scenes, list) else None,
            silences=silences if isinstance(silences, list) else None,
            video_duration=video_duration,
            provider_name=args.provider,
        )
    except (MultimodalContractError, ValueError) as exc:
        print(f"ERROR: Failed to build clip ranking artifact: {exc}", file=sys.stderr)
        sys.exit(1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved clip ranking to: {args.output}")
    print(f"  Candidates: {artifact['summary']['candidateCount']}")


if __name__ == "__main__":
    main()
