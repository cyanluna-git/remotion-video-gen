"""Whisper transcript to Remotion caption format converter.

Reads a Whisper transcript JSON (segments[]), strips whitespace,
splits long lines at word boundaries, merges nearby captions,
and outputs a flat JSON array of {startSec, endSec, text} objects.

Usage:
    python scripts/convert_captions.py <transcript.json>
    python scripts/convert_captions.py transcript.json --output .work/captions.json
    python scripts/convert_captions.py transcript.json --max-chars 40 --merge-gap 0.5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert Whisper transcript JSON to Remotion-compatible caption format.",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Input Whisper transcript JSON file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".work/captions.json"),
        help="Output JSON path (default: .work/captions.json)",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=40,
        help="Maximum characters per caption line (default: 40)",
    )
    parser.add_argument(
        "--merge-gap",
        type=float,
        default=0.5,
        help="Merge captions within this gap in seconds (default: 0.5)",
    )
    return parser.parse_args(argv)


def load_transcript(input_path: Path) -> list[dict]:
    """Load Whisper transcript JSON and extract segments."""
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data

    segments = data.get("segments")
    if segments is None:
        print(f"ERROR: No 'segments' key found in {input_path}", file=sys.stderr)
        sys.exit(1)

    return segments


def split_text_at_word_boundary(text: str, max_chars: int) -> list[str]:
    """Split text into chunks at word boundaries, each within max_chars."""
    if len(text) <= max_chars:
        return [text]

    words = text.split()
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for word in words:
        word_len = len(word)
        separator_len = 1 if current_chunk else 0
        new_len = current_len + separator_len + word_len

        if new_len > max_chars and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]
            current_len = word_len
        else:
            current_chunk.append(word)
            current_len = new_len

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def segments_to_captions(segments: list[dict], max_chars: int) -> tuple[list[dict], int]:
    """Convert Whisper segments to caption objects, splitting long text.

    Returns a tuple of (captions list, split count).
    """
    captions: list[dict] = []
    split_count = 0

    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue

        start_sec = float(seg.get("start", 0.0))
        end_sec = float(seg.get("end", 0.0))

        chunks = split_text_at_word_boundary(text, max_chars)

        if len(chunks) > 1:
            split_count += 1
            total_duration = end_sec - start_sec
            chunk_duration = total_duration / len(chunks) if len(chunks) > 0 else total_duration

            for i, chunk in enumerate(chunks):
                captions.append(
                    {
                        "startSec": round(start_sec + i * chunk_duration, 3),
                        "endSec": round(start_sec + (i + 1) * chunk_duration, 3),
                        "text": chunk,
                    }
                )
        else:
            captions.append(
                {
                    "startSec": round(start_sec, 3),
                    "endSec": round(end_sec, 3),
                    "text": chunks[0],
                }
            )

    return captions, split_count


def merge_nearby_captions(captions: list[dict], merge_gap: float) -> tuple[list[dict], int]:
    """Merge captions that are within merge_gap seconds of each other.

    Returns a tuple of (merged captions list, merge count).
    """
    if not captions:
        return captions, 0

    merged: list[dict] = [captions[0].copy()]
    merge_count = 0

    for caption in captions[1:]:
        prev = merged[-1]
        gap = caption["startSec"] - prev["endSec"]

        if gap <= merge_gap:
            prev["endSec"] = caption["endSec"]
            prev["text"] = prev["text"] + " " + caption["text"]
            merge_count += 1
        else:
            merged.append(caption.copy())

    return merged, merge_count


def save_captions(captions: list[dict], output_path: Path) -> None:
    """Save captions as JSON array."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(captions, indent=2, ensure_ascii=False) + "\n")


def print_summary(input_count: int, output_count: int, split_count: int, merge_count: int) -> None:
    """Print conversion summary."""
    print(f"\n{'=' * 50}")
    print("Caption Conversion Summary")
    print(f"{'=' * 50}")
    print(f"  Input segments  : {input_count}")
    print(f"  Output captions : {output_count}")
    print(f"  Segments split  : {split_count}")
    print(f"  Captions merged : {merge_count}")
    print(f"{'=' * 50}")


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the caption conversion CLI."""
    args = parse_args(argv)

    input_path: Path = args.input
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Converting captions from: {input_path}")
    print(f"  max-chars={args.max_chars}, merge-gap={args.merge_gap}s")

    segments = load_transcript(input_path)
    input_count = len(segments)

    captions, split_count = segments_to_captions(segments, args.max_chars)
    captions, merge_count = merge_nearby_captions(captions, args.merge_gap)

    save_captions(captions, args.output)
    print(f"Saved {len(captions)} captions to: {args.output}")

    print_summary(input_count, len(captions), split_count, merge_count)


if __name__ == "__main__":
    main()
