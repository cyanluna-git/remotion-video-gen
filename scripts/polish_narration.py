"""Polish transcript chunks into professional narration text via AI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from claude_json import call_claude_json
except ImportError:
    from scripts.claude_json import call_claude_json


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Polish transcript chunks into professional narration via AI.",
    )
    parser.add_argument("--chunks", type=Path, required=True, help="Input chunks JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output polished chunks JSON")
    parser.add_argument(
        "--engine",
        choices=["cli", "api", "codex"],
        default="codex",
        help="AI engine (default: codex)",
    )
    parser.add_argument("--context", type=str, default="", help="Optional context about the video topic")
    return parser.parse_args(argv)


def build_prompt(chunks: list[dict[str, Any]], context: str) -> str:
    parts: list[str] = []
    parts.append(
        "You are a professional script writer. Below are transcript chunks from a product demo video.\n"
        "For each chunk, rewrite the text into clean, confident, professional narration.\n\n"
        "Rules:\n"
        "- Keep the same meaning and technical terms\n"
        "- Remove filler words (so, yeah, uh, and then), hesitations, and repetitions\n"
        "- Fix grammar and make sentences natural\n"
        "- Keep it concise — the TTS should fit within the original time window\n"
        "- Return ONLY a valid JSON array of objects: {\"index\": number, \"text\": string}\n"
    )
    if context:
        parts.append(f"\nContext: {context}\n")
    parts.append("\nChunks:\n")
    parts.append(json.dumps(chunks, indent=2, ensure_ascii=False))
    return "\n".join(parts)


def validate_polished(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array")
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(f"Each item must be an object, got {type(item)}")
        if "index" not in item or "text" not in item:
            raise ValueError(f"Each item must have 'index' and 'text', got keys: {list(item.keys())}")
    return data


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if not args.chunks.exists():
        print(f"ERROR: Chunks file not found: {args.chunks}", file=sys.stderr)
        raise SystemExit(1)

    with args.chunks.open("r", encoding="utf-8") as f:
        chunks = json.load(f)

    print(f"Polishing {len(chunks)} chunks via {args.engine}...")

    prompt = build_prompt(chunks, args.context)
    polished = call_claude_json(prompt, engine=args.engine, validate=validate_polished)

    if len(polished) != len(chunks):
        print(f"WARNING: Got {len(polished)} polished chunks, expected {len(chunks)}", file=sys.stderr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(polished, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Polished {len(polished)} chunks")
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
