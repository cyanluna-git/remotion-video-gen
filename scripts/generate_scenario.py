"""Claude scenario.json generator from Step 2 analysis artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from claude_json import call_claude_json
    from scenario_contract import ScenarioContractError
    from scenario_generation import (
        build_scenario_prompt,
        derive_language,
        derive_title,
        extract_transcript_segments,
        get_video_duration,
        load_json_file,
        validate_generated_scenario,
    )
except ModuleNotFoundError:
    from scripts.claude_json import call_claude_json
    from scripts.scenario_contract import ScenarioContractError
    from scripts.scenario_generation import (
        build_scenario_prompt,
        derive_language,
        derive_title,
        extract_transcript_segments,
        get_video_duration,
        load_json_file,
        validate_generated_scenario,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a canonical scenario.json from analysis artifacts.",
    )
    parser.add_argument("--transcript", type=Path, default=None, help="Whisper transcript JSON file")
    parser.add_argument("--scenes", type=Path, default=None, help="Scene detection JSON file")
    parser.add_argument("--silences", type=Path, default=None, help="Silence detection JSON file")
    parser.add_argument("--video", type=Path, default=None, help="Video file for duration and title fallback")
    parser.add_argument("--title", default=None, help="Optional title hint")
    parser.add_argument("--language", default=None, help="Optional language hint")
    parser.add_argument("--source-name", default=None, help="Optional source filename for title fallback")
    parser.add_argument("--prompt-output", type=Path, default=None, help="Optional path to save rendered prompt text")
    parser.add_argument("--error-output", type=Path, default=None, help="Optional path to save generation error text")
    parser.add_argument("--output", type=Path, required=True, help="Output scenario.json path")
    parser.add_argument(
        "--engine",
        choices=["cli", "api"],
        default="cli",
        help="Engine: 'cli' uses claude -p (default), 'api' uses Anthropic SDK",
    )
    return parser.parse_args(argv)


def write_text_artifact(path: Path | None, content: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    print("Generating scenario from analysis artifacts")
    print(f"Engine: {args.engine}")
    print("Loading inputs:")

    transcript = load_json_file(args.transcript, "transcript") if args.transcript else None
    scenes = load_json_file(args.scenes, "scenes") if args.scenes else None
    silences = load_json_file(args.silences, "silences") if args.silences else None
    video_duration = get_video_duration(args.video) if args.video else None

    source_name = args.source_name or (args.video.name if args.video else None)
    title = derive_title(args.title, source_name)
    language = derive_language(args.language, transcript)

    transcript_segments = extract_transcript_segments(transcript)
    prompt = build_scenario_prompt(
        title_hint=title,
        language_hint=language,
        transcript_segments=transcript_segments,
        scenes=scenes if isinstance(scenes, list) else None,
        silences=silences if isinstance(silences, list) else None,
        video_duration=video_duration,
    )
    write_text_artifact(args.prompt_output, prompt)

    try:
        scenario = call_claude_json(
            prompt,
            engine=args.engine,
            validate=lambda payload: validate_generated_scenario(
                payload,
                video_duration=video_duration,
            ),
        )
    except (ScenarioContractError, ValueError) as exc:
        write_text_artifact(args.error_output, f"{exc}\n")
        print(f"ERROR: Failed to generate valid scenario: {exc}", file=sys.stderr)
        sys.exit(1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(scenario, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved scenario to: {args.output}")


if __name__ == "__main__":
    main()
