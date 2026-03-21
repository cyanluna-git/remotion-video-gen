"""Helpers for AI-assisted scenario generation."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from scenario_contract import ScenarioContractError, normalize_scenario
except ModuleNotFoundError:
    from scripts.scenario_contract import ScenarioContractError, normalize_scenario


def load_json_file(path: Path | None, label: str) -> Optional[dict | list]:
    """Load an optional JSON file."""
    if path is None or not path.exists():
        if path is not None:
            print(f"  Warning: {label} not found at {path}, skipping.")
        return None

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"  Loaded {label}: {path}")
    return data


def get_video_duration(video_path: Path | None) -> Optional[float]:
    """Get video duration in seconds via ffprobe."""
    if video_path is None or not video_path.exists():
        if video_path is not None:
            print(f"  Warning: Video not found at {video_path}, skipping duration detection.")
        return None

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
        print(f"  Video duration: {duration:.3f}s")
        return duration
    except FileNotFoundError:
        print("  Warning: ffprobe not found, skipping duration detection.", file=sys.stderr)
        return None
    except (subprocess.CalledProcessError, ValueError) as exc:
        print(f"  Warning: Failed to get video duration: {exc}", file=sys.stderr)
        return None


def derive_title(title_hint: str | None, source_name: str | None) -> str:
    """Choose a deterministic title for auto-scenario mode."""
    if title_hint and title_hint.strip():
        return title_hint.strip()

    if source_name:
        stem = Path(source_name).stem
        normalized = re.sub(r"[-_]+", " ", stem)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if normalized:
            return normalized

    return "Untitled Recording"


def derive_language(language_hint: str | None, transcript: dict | list | None) -> str:
    """Choose a deterministic language for auto-scenario mode."""
    if language_hint and language_hint.strip():
        return language_hint.strip()

    if isinstance(transcript, dict):
        detected = str(transcript.get("language", "")).strip()
        if detected and detected.lower() != "unknown":
            return detected

    return "auto"


def extract_transcript_segments(transcript: dict | list | None, limit: int = 120) -> list[dict]:
    """Extract transcript segments from Whisper output."""
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


def summarize_clip_ranking(
    clip_ranking: dict[str, Any] | None,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Return a compact ranking summary suitable for prompt context."""
    if not isinstance(clip_ranking, dict):
        return []
    candidates = clip_ranking.get("candidates")
    if not isinstance(candidates, list):
        return []

    summary: list[dict[str, Any]] = []
    for candidate in candidates[:limit]:
        if not isinstance(candidate, dict):
            continue
        compact = {
            "id": candidate.get("id"),
            "rank": candidate.get("rank"),
            "startSec": candidate.get("startSec"),
            "endSec": candidate.get("endSec"),
            "score": candidate.get("score"),
            "sourceSignals": candidate.get("sourceSignals", []),
        }
        transcript_excerpt = str(candidate.get("transcriptExcerpt") or "").strip()
        rationale = str(candidate.get("rationale") or "").strip()
        if transcript_excerpt:
            compact["transcriptExcerpt"] = transcript_excerpt
        if rationale:
            compact["rationale"] = rationale
        summary.append(compact)
    return summary


def build_scenario_prompt(
    *,
    title_hint: str,
    language_hint: str,
    transcript_segments: list[dict],
    scenes: list | None,
    silences: list | None,
    clip_ranking: dict[str, Any] | None,
    video_duration: float | None,
) -> str:
    """Build the prompt for canonical scenario generation."""
    parts: list[str] = []

    parts.append(
        "You are generating a canonical scenario JSON for a Remotion video pipeline.\n"
        "Return ONLY valid JSON. No markdown, no explanation, no comments.\n"
    )

    parts.append("\n## Required Output Schema\n")
    parts.append(
        json.dumps(
            {
                "title": title_hint,
                "language": language_hint,
                "sections": [
                    {
                        "title": "Section title",
                        "description": "What happens in this segment and why it matters.",
                        "timeRange": {"startSec": 0, "endSec": 10},
                    }
                ],
                "style": {
                    "titleCardBackground": "linear-gradient(135deg, #c8102e, #1e1b4b)",
                    "captionPosition": "bottom",
                    "transition": "fade",
                    "transitionDuration": 0.5,
                },
                "options": {
                    "removeSilence": True,
                    "silenceThreshold": 3.0,
                    "autoCaption": True,
                    "correctCaptions": True,
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    parts.append("\n## Instructions\n")
    parts.append(f'- Use "{title_hint}" as the scenario title unless the transcript makes a better title obvious.')
    parts.append(
        f'- Use "{language_hint}" as the language when it is specific; keep "auto" only when the language is genuinely unclear.'
    )
    parts.append("- Infer 1 to 6 sections from the transcript and scene structure.")
    parts.append("- For very short or low-signal videos, prefer one broad section over artificial splits.")
    parts.append("- Sections must be ordered, non-overlapping, and bounded to the source recording.")
    parts.append("- Every section needs a concise title and a description focused on viewer-visible actions.")
    parts.append("- Emit canonical `timeRange.startSec/endSec`; do not emit legacy flat `startSec/endSec` fields.")
    parts.append("- Keep `options.correctCaptions` enabled.")
    parts.append("- When clip-ranking hints are present, prefer top-ranked windows as anchors for representative, high-signal moments without forcing a one-section-per-window mapping.")

    if video_duration is not None:
        parts.append(f"- The source video duration is {video_duration:.3f} seconds. Do not exceed it.")

    if transcript_segments:
        parts.append(f"\n## Transcript Segments ({len(transcript_segments)} segments)\n")
        parts.append(json.dumps(transcript_segments, indent=2, ensure_ascii=False))

    if scenes:
        parts.append(f"\n## Scene Changes ({len(scenes)} detected)\n")
        parts.append(json.dumps(scenes, indent=2, ensure_ascii=False))

    if silences:
        parts.append(f"\n## Silence Segments ({len(silences)} detected)\n")
        parts.append(json.dumps(silences, indent=2, ensure_ascii=False))

    clip_ranking_summary = summarize_clip_ranking(clip_ranking)
    if clip_ranking_summary:
        parts.append(f"\n## Clip Ranking Hints ({len(clip_ranking_summary)} candidates)\n")
        parts.append(json.dumps(clip_ranking_summary, indent=2, ensure_ascii=False))

    return "\n".join(parts)


def validate_generated_scenario(
    payload: Any,
    *,
    video_duration: float | None = None,
) -> dict[str, Any]:
    """Normalize and validate generated scenario semantics."""
    if not isinstance(payload, dict):
        raise ScenarioContractError("Generated scenario must be a JSON object.")

    scenario = normalize_scenario(payload)
    validate_scenario_semantics(scenario, video_duration=video_duration)
    return scenario


def validate_scenario_semantics(
    scenario: dict[str, Any],
    *,
    video_duration: float | None = None,
) -> None:
    """Reject overlapping or out-of-bounds sections."""
    previous_end = 0.0
    for index, section in enumerate(scenario["sections"]):
        time_range = section["timeRange"]
        start_sec = float(time_range["startSec"])
        end_sec = float(time_range["endSec"])

        if start_sec < 0:
            raise ScenarioContractError(f"sections[{index}] starts before 0 seconds.")
        if end_sec <= start_sec:
            raise ScenarioContractError(
                f"sections[{index}] must have endSec greater than startSec."
            )
        if index > 0 and start_sec < previous_end:
            raise ScenarioContractError(
                f"sections[{index}] overlaps the previous section."
            )
        if video_duration is not None and end_sec > video_duration + 1e-6:
            raise ScenarioContractError(
                f"sections[{index}] ends after the source duration ({video_duration:.3f}s)."
            )

        previous_end = end_sec
