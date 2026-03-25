"""Generate per-chunk TTS audio files and voiceover manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from multimodal_contracts import normalize_voiceover_manifest
    from tts_providers import TtsProviderError, TtsRequest, build_tts_provider, probe_audio_duration
except ImportError:
    from scripts.multimodal_contracts import normalize_voiceover_manifest
    from scripts.tts_providers import (
        TtsProviderError,
        TtsRequest,
        build_tts_provider,
        probe_audio_duration,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate per-chunk TTS audio and voiceover manifest.",
    )
    parser.add_argument("--chunks", type=Path, required=True, help="Original timed chunks JSON")
    parser.add_argument("--polished", type=Path, required=True, help="Polished narration chunks JSON")
    parser.add_argument("--output", type=Path, required=True, help="Voiceover manifest JSON output path")
    parser.add_argument("--provider", type=str, required=True, help="TTS provider (edge/openai/mock)")
    parser.add_argument("--model", type=str, default="edge-tts", help="TTS model (default: edge-tts)")
    parser.add_argument("--voice", type=str, required=True, help="TTS voice name")
    parser.add_argument("--audio-format", type=str, default="mp3", help="Audio format (default: mp3)")
    parser.add_argument("--instructions", type=str, default="", help="Optional narration style instructions")
    parser.add_argument("--error-output", type=Path, default=None, help="Error output path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    for path, label in [(args.chunks, "Chunks"), (args.polished, "Polished")]:
        if not path.exists():
            print(f"ERROR: {label} file not found: {path}", file=sys.stderr)
            raise SystemExit(1)

    with args.chunks.open("r", encoding="utf-8") as f:
        chunks = json.load(f)
    with args.polished.open("r", encoding="utf-8") as f:
        polished = json.load(f)

    if len(polished) != len(chunks):
        print(
            f"WARNING: {len(polished)} polished chunks vs {len(chunks)} chunks",
            file=sys.stderr,
        )

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

    tracks: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for chunk, pol in zip(chunks, polished):
        index = chunk["index"]
        track_id = f"chunk-{index + 1:03d}"
        output_path = voiceover_dir / f"{track_id}.{provider.file_extension}"
        text = pol.get("text", chunk.get("text", ""))

        request = TtsRequest(
            text=text,
            output_path=output_path,
            language="auto",
            label=track_id,
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

        tracks.append({
            "id": track_id,
            "label": track_id,
            "src": f"voiceover/{output_path.name}",
            "startSec": float(chunk["startSec"]),
            "durationSec": round(float(duration_sec), 3),
            "text": text,
            "volume": 1.0,
            "provider": synthesis.get("provider"),
        })

        if (index + 1) % 10 == 0 or index == len(chunks) - 1:
            print(f"  Generated {index + 1}/{len(chunks)} tracks")

    if not tracks:
        error_data = {"status": "failed", "message": "No voiceover tracks were generated."}
        if args.error_output:
            args.error_output.parent.mkdir(parents=True, exist_ok=True)
            args.error_output.write_text(json.dumps(error_data, indent=2))
        raise TtsProviderError("No voiceover tracks were generated.")

    summary_status = "partial" if failures else "ready"
    manifest = normalize_voiceover_manifest({
        "status": summary_status,
        "provider": {"name": args.provider, "model": args.model, "voice": args.voice},
        "tracks": tracks,
        "summary": {"status": summary_status, "trackCount": len(tracks)},
        "revision": {
            "requestedTrackCount": len(chunks),
            "failedTracks": failures,
        },
    })

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    total_dur = sum(t["durationSec"] for t in tracks)
    print(f"\nGenerated {len(tracks)} tracks ({total_dur:.0f}s total)")
    if failures:
        print(f"  Failed: {len(failures)}")
    print(f"Saved manifest to: {manifest_path}")


if __name__ == "__main__":
    main()
