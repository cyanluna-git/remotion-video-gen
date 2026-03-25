"""Group Whisper transcript segments into timed chunks for granular TTS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Group Whisper transcript segments into timed chunks.",
    )
    parser.add_argument("--transcript", type=Path, required=True, help="Whisper transcript JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output chunks JSON")
    parser.add_argument(
        "--max-duration",
        type=float,
        default=12.0,
        help="Maximum chunk duration in seconds (default: 12.0)",
    )
    parser.add_argument(
        "--min-gap",
        type=float,
        default=0.8,
        help="Minimum gap between segments to force chunk boundary (default: 0.8)",
    )
    return parser.parse_args(argv)


def load_segments(transcript_path: Path) -> list[dict[str, Any]]:
    with transcript_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return data.get("segments", [])


def chunk_segments(
    segments: list[dict[str, Any]],
    *,
    max_duration: float,
    min_gap: float,
) -> list[dict[str, Any]]:
    if not segments:
        return []

    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    chunk_start: float = 0.0

    for seg in segments:
        seg_start = float(seg.get("start", 0.0))
        seg_end = float(seg.get("end", 0.0))
        seg_text = str(seg.get("text", "")).strip()
        if not seg_text:
            continue

        if not current:
            chunk_start = seg_start
            current.append(seg)
            continue

        prev_end = float(current[-1].get("end", 0.0))
        gap = seg_start - prev_end
        duration_if_added = seg_end - chunk_start

        if gap >= min_gap or duration_if_added > max_duration:
            chunks.append(_finalize_chunk(current, chunk_start, len(chunks)))
            chunk_start = seg_start
            current = [seg]
        else:
            current.append(seg)

    if current:
        chunks.append(_finalize_chunk(current, chunk_start, len(chunks)))

    return chunks


def _finalize_chunk(
    segments: list[dict[str, Any]],
    chunk_start: float,
    index: int,
) -> dict[str, Any]:
    text = " ".join(str(s.get("text", "")).strip() for s in segments)
    return {
        "index": index,
        "startSec": round(chunk_start, 3),
        "endSec": round(float(segments[-1].get("end", 0.0)), 3),
        "text": text,
        "segCount": len(segments),
    }


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if not args.transcript.exists():
        print(f"ERROR: Transcript not found: {args.transcript}")
        raise SystemExit(1)

    segments = load_segments(args.transcript)
    chunks = chunk_segments(segments, max_duration=args.max_duration, min_gap=args.min_gap)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(chunks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    total_dur = sum(c["endSec"] - c["startSec"] for c in chunks)
    print(f"Chunked {len(segments)} segments -> {len(chunks)} chunks ({total_dur:.0f}s)")
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
