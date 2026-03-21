"""Generate provider-agnostic voiceover assets and manifest from scenario JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from multimodal_contracts import (
        MultimodalContractError,
        normalize_voiceover_manifest,
        utcnow_iso,
    )
    from scenario_contract import ScenarioContractError, normalize_scenario
    from tts_providers import TtsProviderError, TtsRequest, build_tts_provider, probe_audio_duration
except ModuleNotFoundError:
    from scripts.multimodal_contracts import (
        MultimodalContractError,
        normalize_voiceover_manifest,
        utcnow_iso,
    )
    from scripts.scenario_contract import ScenarioContractError, normalize_scenario
    from scripts.tts_providers import (
        TtsProviderError,
        TtsRequest,
        build_tts_provider,
        probe_audio_duration,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate voiceover assets + provider-agnostic manifest from a scenario.",
    )
    parser.add_argument("--scenario", type=Path, required=True, help="Canonical scenario JSON path")
    parser.add_argument("--output", type=Path, required=True, help="voiceover/manifest.json path")
    parser.add_argument(
        "--provider",
        required=True,
        choices=["mock", "openai"],
        help="TTS provider name",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini-tts",
        help="Provider model name (default: gpt-4o-mini-tts)",
    )
    parser.add_argument(
        "--voice",
        default="alloy",
        help="Provider voice name (default: alloy)",
    )
    parser.add_argument(
        "--audio-format",
        default="wav",
        help="Output audio format/extension (default: wav)",
    )
    parser.add_argument(
        "--instructions",
        default="",
        help="Optional provider-specific narration instructions",
    )
    parser.add_argument(
        "--error-output",
        type=Path,
        default=None,
        help="Optional error JSON path (default: <manifest-dir>/error.json)",
    )
    return parser.parse_args(argv)


def load_scenario(scenario_path: Path) -> dict[str, Any]:
    with scenario_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return normalize_scenario(payload)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = slug.strip("-")
    return slug or "track"


def build_track_text(section: dict[str, Any]) -> str:
    title = str(section.get("title") or "").strip()
    description = str(section.get("description") or "").strip()
    if description.lower().startswith(title.lower()) or not title:
        return description
    return f"{title}. {description}"


def build_revision_hash(
    scenario: dict[str, Any],
    *,
    provider: str,
    model: str,
    voice: str,
    audio_format: str,
    instructions: str,
) -> str:
    raw = json.dumps(
        {
            "scenario": scenario,
            "provider": provider,
            "model": model,
            "voice": voice,
            "audioFormat": audio_format,
            "instructions": instructions,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_voiceover_manifest(args: argparse.Namespace) -> dict[str, Any]:
    scenario = load_scenario(args.scenario)
    provider = build_tts_provider(
        args.provider,
        model=args.model,
        voice=args.voice,
        audio_format=args.audio_format,
        instructions=args.instructions,
    )

    manifest_path = args.output.resolve()
    voiceover_dir = manifest_path.parent
    voiceover_dir.mkdir(parents=True, exist_ok=True)

    revision_hash = build_revision_hash(
        scenario,
        provider=args.provider,
        model=args.model,
        voice=args.voice,
        audio_format=args.audio_format,
        instructions=args.instructions,
    )

    tracks: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    requested_count = len(scenario["sections"])

    for index, section in enumerate(scenario["sections"], start=1):
        track_id = f"section-{index:02d}-{slugify(section['title'])}"
        output_path = voiceover_dir / f"{track_id}.{provider.file_extension}"
        request = TtsRequest(
            text=build_track_text(section),
            output_path=output_path,
            language=str(scenario.get("language") or "auto"),
            label=section["title"],
        )

        try:
            synthesis = provider.synthesize(request)
            duration_sec = synthesis.get("durationSec") or probe_audio_duration(output_path)
            if duration_sec is None or duration_sec <= 0:
                raise TtsProviderError(f"Failed to determine duration for {output_path.name}.")
        except (OSError, TtsProviderError) as exc:
            failures.append({"trackId": track_id, "message": str(exc)})
            if output_path.exists():
                output_path.unlink()
            continue

        tracks.append(
            {
                "id": track_id,
                "label": section["title"],
                "src": f"voiceover/{output_path.name}",
                "startSec": float(section["timeRange"]["startSec"]),
                "durationSec": round(float(duration_sec), 3),
                "text": request.text,
                "provider": synthesis.get("provider"),
            }
        )

    if not tracks:
        raise TtsProviderError("No voiceover tracks were generated.")

    summary_status = "partial" if failures else "ready"
    manifest = normalize_voiceover_manifest(
        {
            "generatedAt": utcnow_iso(),
            "status": summary_status,
            "provider": {
                "name": args.provider,
                "model": args.model,
                "voice": args.voice,
            },
            "tracks": tracks,
            "summary": {
                "status": summary_status,
                "trackCount": len(tracks),
            },
            "revision": {
                "hash": revision_hash,
                "scenarioPath": str(args.scenario),
                "requestedTrackCount": requested_count,
                "failedTracks": failures,
            },
        }
    )

    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def write_error_payload(error_path: Path, message: str) -> None:
    error_path.parent.mkdir(parents=True, exist_ok=True)
    error_path.write_text(
        json.dumps(
            {
                "status": "failed",
                "generatedAt": utcnow_iso(),
                "message": message,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    error_path = args.error_output or (args.output.parent / "error.json")

    try:
        manifest = generate_voiceover_manifest(args)
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        MultimodalContractError,
        ScenarioContractError,
        TtsProviderError,
    ) as exc:
        write_error_payload(error_path, str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if error_path.exists():
        error_path.unlink()

    summary = manifest.get("summary", {})
    print(f"Generated voiceover manifest: {args.output}")
    print(f"  Provider : {args.provider}")
    print(f"  Tracks   : {summary.get('trackCount', 0)}")
    print(f"  Status   : {summary.get('status', manifest.get('status', 'ready'))}")


if __name__ == "__main__":
    main()
