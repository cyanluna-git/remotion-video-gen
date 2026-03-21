"""Claude edit.json generator for Remotion video pipeline.

Takes a scenario file plus optional analysis data (transcript, scenes,
silences, video) and calls Claude to generate a structured Remotion
edit script in JSON format.

Supports two engines:
  --engine cli   (default) Uses `claude -p` CLI — no API key needed
  --engine api   Uses Anthropic SDK — requires ANTHROPIC_API_KEY

Usage:
    python scripts/generate_edit.py \\
      --scenario scenarios/demo.json \\
      --transcript .work/transcript.json \\
      --scenes .work/scenes.json \\
      --silences .work/silences.json \\
      --video .work/normalized.mp4 \\
      --output .work/edit.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

try:
    from claude_json import call_claude_json
    from scenario_contract import ScenarioContractError, normalize_scenario
    from scenario_generation import get_video_duration, load_json_file
except ModuleNotFoundError:
    from scripts.claude_json import call_claude_json
    from scripts.scenario_contract import ScenarioContractError, normalize_scenario
    from scripts.scenario_generation import get_video_duration, load_json_file


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a Remotion edit.json via Claude from scenario + analysis data.",
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        required=True,
        help="Scenario JSON file (required)",
    )
    parser.add_argument(
        "--transcript",
        type=Path,
        default=None,
        help="Whisper transcript JSON file (optional)",
    )
    parser.add_argument(
        "--scenes",
        type=Path,
        default=None,
        help="Scene detection JSON file (optional)",
    )
    parser.add_argument(
        "--silences",
        type=Path,
        default=None,
        help="Silence detection JSON file (optional)",
    )
    parser.add_argument(
        "--video",
        type=Path,
        default=None,
        help="Normalized video file for duration detection (optional)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output edit.json path",
    )
    parser.add_argument(
        "--engine",
        choices=["cli", "api"],
        default="cli",
        help="Engine: 'cli' uses claude -p (default), 'api' uses Anthropic SDK",
    )
    return parser.parse_args(argv)

def extract_transcript_segments(transcript: dict | list | None, limit: int = 100) -> list[dict]:
    """Extract transcript segments (up to limit) from Whisper output."""
    if transcript is None:
        return []

    if isinstance(transcript, list):
        segments = transcript
    else:
        segments = transcript.get("segments", [])

    result: list[dict] = []
    for seg in segments[:limit]:
        result.append(
            {
                "start": round(float(seg.get("start", 0.0)), 3),
                "end": round(float(seg.get("end", 0.0)), 3),
                "text": seg.get("text", "").strip(),
            }
        )
    return result


def build_prompt(
    scenario: dict,
    transcript_segments: list[dict],
    scenes: list | None,
    silences: list | None,
    video_duration: float | None,
) -> str:
    """Construct the full prompt from all available inputs."""
    parts: list[str] = []

    parts.append(
        "You are a professional video editor. Generate a Remotion edit script in JSON format.\n"
        "The JSON must conform to the EditScript schema exactly.\n"
        "Return ONLY valid JSON — no explanations, no markdown fencing, no comments.\n"
    )

    parts.append("## Scenario\n")
    parts.append(json.dumps(scenario, indent=2, ensure_ascii=False))

    language = scenario.get("language", "auto")
    parts.append(f"\n## Language\n{language}")

    if video_duration is not None:
        parts.append(f"\n## Video Duration\n{video_duration:.3f} seconds")

    if transcript_segments:
        parts.append(f"\n## Transcript Segments ({len(transcript_segments)} segments)\n")
        parts.append(json.dumps(transcript_segments, indent=2, ensure_ascii=False))

    if scenes:
        parts.append(f"\n## Scene Changes ({len(scenes)} detected)\n")
        parts.append(json.dumps(scenes, indent=2, ensure_ascii=False))

    if silences:
        parts.append(f"\n## Silence Segments ({len(silences)} detected)\n")
        parts.append(json.dumps(silences, indent=2, ensure_ascii=False))

    silence_threshold = scenario.get("options", {}).get("silenceThreshold", 3.0)
    style = scenario.get("style", {})

    parts.append("\n## Instructions\n")
    parts.append("- Arrange clips according to each scenario section's timeRange (startSec, endSec).")
    parts.append(f"- Remove silence segments longer than {silence_threshold} seconds.")
    parts.append("- Insert a title-card entry between sections using the section's title.")
    parts.append("- Place caption overlays from the Whisper transcript at their correct timestamps within the clip.")
    parts.append('- Correct Whisper transcript errors for technical terms (e.g. "모드버스"→"Modbus").')

    transition = style.get("transition", "fade")
    transition_dur = style.get("transitionDuration", 0.5)
    caption_pos = style.get("captionPosition", "bottom")
    title_bg = style.get("titleCardBackground", "linear-gradient(135deg, #c8102e, #1e1b4b)")
    parts.append(f'- Use transition type: "{transition}" with durationSec: {transition_dur}.')
    parts.append(f'- Caption position: "{caption_pos}".')
    parts.append(f'- Title card background: "{title_bg}".')
    parts.append('- Use "main" as the source key for all video clips.')
    parts.append("- sources should be: { \"main\": \"recordings/normalized.mp4\" }")
    parts.append("- The output JSON must include: version (\"1.0\"), fps (30), resolution ({width:1920,height:1080}), sources, timeline.")
    parts.append("- Each title-card must have: type, text, durationSec, background.")
    parts.append("- Each clip must have: type, source, startSec, endSec. Optionally: overlays, transition.")
    parts.append("- Each overlay must have: type, startSec, durationSec. For caption: text, position. For highlight: region, color.")

    return "\n".join(parts)


def validate_edit_script(edit: dict) -> dict:
    """Validate that the edit script contains required fields."""
    required_fields = ["version", "fps", "resolution", "sources", "timeline"]
    missing = [f for f in required_fields if f not in edit]
    if missing:
        raise ValueError(f"Edit script missing required fields: {', '.join(missing)}")
    return edit


# ═══════════════════════════════════════════
# Common
# ═══════════════════════════════════════════

def save_edit_script(edit: dict, output_path: Path) -> None:
    """Save edit script as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(edit, indent=2, ensure_ascii=False) + "\n")


def print_summary(edit: dict) -> None:
    """Print summary of the generated edit script."""
    timeline = edit.get("timeline", [])
    total_entries = len(timeline)

    title_cards = sum(1 for e in timeline if e.get("type") == "title-card")
    clips = sum(1 for e in timeline if e.get("type") == "clip")

    total_duration = 0.0
    for entry in timeline:
        if entry.get("type") == "clip":
            total_duration += entry.get("endSec", 0) - entry.get("startSec", 0)
        else:
            total_duration += entry.get("durationSec", 0)

    minutes = int(total_duration // 60)
    seconds = total_duration % 60

    print(f"\n{'=' * 50}")
    print("Edit Script Generation Summary")
    print(f"{'=' * 50}")
    print(f"  Timeline entries : {total_entries}")
    print(f"  Video clips      : {clips}")
    print(f"  Title cards      : {title_cards}")
    print(f"  Total duration   : {minutes}m {seconds:.1f}s")
    print(f"{'=' * 50}")


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the edit script generator CLI."""
    args = parse_args(argv)

    if not args.scenario.exists():
        print(f"ERROR: Scenario file not found: {args.scenario}", file=sys.stderr)
        sys.exit(1)

    print(f"Generating edit script from scenario: {args.scenario}")
    print(f"Engine: {args.engine}")
    print("Loading inputs:")

    scenario = load_json_file(args.scenario, "scenario")
    if scenario is None:
        print("ERROR: Failed to load scenario file.", file=sys.stderr)
        sys.exit(1)
    try:
        scenario = normalize_scenario(scenario)
    except ScenarioContractError as exc:
        print(f"ERROR: Invalid scenario payload: {exc}", file=sys.stderr)
        sys.exit(1)

    transcript = load_json_file(args.transcript, "transcript") if args.transcript else None
    scenes = load_json_file(args.scenes, "scenes") if args.scenes else None
    silences = load_json_file(args.silences, "silences") if args.silences else None

    video_duration = get_video_duration(args.video) if args.video else None

    transcript_segments = extract_transcript_segments(transcript)

    prompt = build_prompt(
        scenario=scenario,
        transcript_segments=transcript_segments,
        scenes=scenes if isinstance(scenes, list) else None,
        silences=silences if isinstance(silences, list) else None,
        video_duration=video_duration,
    )

    edit = call_claude_json(
        prompt,
        engine=args.engine,
        validate=validate_edit_script,
    )

    # Set sources.main to recordings path for Remotion
    sources = edit.get("sources", {})
    if "main" not in sources:
        sources["main"] = "recordings/normalized.mp4"
    edit["sources"] = sources

    save_edit_script(edit, args.output)
    print(f"Saved edit script to: {args.output}")

    print_summary(edit)


if __name__ == "__main__":
    main()
