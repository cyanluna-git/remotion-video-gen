"""Export edit.json to a CapCut desktop draft via pyCapCut.

Reads an edit.json produced by the Remotion video-gen pipeline and creates
a CapCut draft directory that can be opened in CapCut desktop for further
editing with AI effects, captions, and transitions.

Usage:
    python scripts/export_capcut.py \
      --input .work/edit.json \
      --drafts-dir ~/Movies/CapCut/Drafts \
      --video-dir remotion/public/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from pycapcut import (
    DraftFolder,
    SEC,
    Timerange,
    TrackType,
    TransitionType,
    VideoMaterial,
    VideoSegment,
)

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None  # type: ignore[assignment,misc]
    ImageDraw = None  # type: ignore[assignment,misc]

# ── Transition mapping ────────────────────────────────────────────────────────

TRANSITION_MAP: dict[str, TransitionType] = {
    "fade": TransitionType.叠化,
    "slide-left": TransitionType.向左,
    "slide-right": TransitionType.向右,
    "wipe": TransitionType.向右擦除,
}

# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export edit.json to a CapCut desktop draft.",
    )
    parser.add_argument("--input", type=Path, required=True, help="Path to edit.json")
    parser.add_argument(
        "--drafts-dir",
        type=Path,
        default=Path.home() / "Movies" / "CapCut" / "Drafts",
        help="CapCut drafts folder (default: ~/Movies/CapCut/Drafts)",
    )
    parser.add_argument(
        "--draft-name",
        type=str,
        default=None,
        help="Draft name (default: edit_YYYYMMDD_HHMMSS)",
    )
    parser.add_argument(
        "--video-dir",
        type=Path,
        default=Path(".work"),
        help="Base directory for resolving relative source paths (default: .work/)",
    )
    return parser.parse_args(argv)


# ── Helpers ───────────────────────────────────────────────────────────────────


def load_edit_json(path: Path) -> dict[str, Any]:
    """Load and validate edit.json."""
    if not path.exists():
        print(f"ERROR: edit.json not found: {path}", file=sys.stderr)
        raise SystemExit(1)
    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    for field in ("version", "fps", "resolution", "sources", "timeline"):
        if field not in data:
            print(f"ERROR: edit.json missing required field '{field}'", file=sys.stderr)
            raise SystemExit(1)
    return data


def resolve_sources(sources: dict[str, str], video_dir: Path) -> dict[str, Path]:
    """Resolve source paths to absolute paths, validating existence."""
    resolved: dict[str, Path] = {}
    for key, rel_path in sources.items():
        p = Path(rel_path)
        if not p.is_absolute():
            p = (video_dir / p).resolve()
        else:
            p = p.resolve()
        if not p.exists():
            raise FileNotFoundError(f"Source '{key}' not found: {p}")
        resolved[key] = p
    return resolved


def extract_hex_color(css_value: str) -> str:
    """Extract the first hex color from a CSS value string."""
    match = re.search(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", css_value)
    if match:
        return f"#{match.group(1)}"
    return "#1e1b4b"


def generate_title_card(
    text: str,
    subtitle: str | None,
    background: str,
    width: int,
    height: int,
    output_path: Path,
) -> Path:
    """Generate a solid-color PNG with text overlay for a title card."""
    if Image is None:
        print("ERROR: Pillow is required for title card generation. Install with: pip install Pillow", file=sys.stderr)
        raise SystemExit(1)

    color = extract_hex_color(background)
    img = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(img)

    cx, cy = width // 2, height // 2
    draw.text((cx, cy), text, fill="white", anchor="mm")
    if subtitle:
        draw.text((cx, cy + 50), subtitle, fill="#cccccc", anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path))
    return output_path


# ── Main export logic ─────────────────────────────────────────────────────────


def export_capcut(args: argparse.Namespace) -> Path:
    """Export edit.json to a CapCut draft. Returns the draft directory path."""
    edit_data = load_edit_json(args.input)

    fps: int = edit_data["fps"]
    resolution: dict[str, int] = edit_data["resolution"]
    width: int = resolution["width"]
    height: int = resolution["height"]
    sources_raw: dict[str, str] = edit_data["sources"]
    timeline: list[dict[str, Any]] = edit_data["timeline"]

    # Resolve source paths
    resolved_sources = resolve_sources(sources_raw, args.video_dir)

    # Draft name
    draft_name: str = args.draft_name or f"edit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Ensure drafts directory exists (pyCapCut raises FileNotFoundError otherwise)
    drafts_dir: Path = args.drafts_dir
    drafts_dir.mkdir(parents=True, exist_ok=True)

    # Create draft
    df = DraftFolder(str(drafts_dir))
    script = df.create_draft(draft_name, width, height, fps=fps, allow_replace=True)

    # Add a video track to the script
    script.add_track(TrackType.video)

    # Warn on empty timeline
    if not timeline:
        print("WARNING: timeline is empty — creating empty draft", file=sys.stderr)
        script.save()
        draft_path = drafts_dir / draft_name
        _print_instructions(draft_path)
        return draft_path

    # Pre-register unique video materials (one per source path)
    materials: dict[str, VideoMaterial] = {}
    for key, abs_path in resolved_sources.items():
        mat = VideoMaterial(str(abs_path))
        script.add_material(mat)
        materials[key] = mat

    # Process timeline entries
    segments: list[VideoSegment] = []
    timeline_cursor: int = 0  # microseconds
    title_card_idx: int = 0
    draft_dir = drafts_dir / draft_name

    for i, entry in enumerate(timeline):
        entry_type: str = entry.get("type", "")

        if entry_type == "clip":
            source_key: str = entry.get("source", "")
            if source_key not in materials:
                print(
                    f"WARNING: clip at index {i} references unknown source '{source_key}' — skipping",
                    file=sys.stderr,
                )
                continue

            start_us = int(entry["startSec"] * SEC)
            end_us = int(entry["endSec"] * SEC)
            duration_us = end_us - start_us
            speed: float = entry.get("speed", 1.0)

            source_tr = Timerange(start_us, duration_us)
            target_duration = int(duration_us / speed) if speed != 1.0 else duration_us
            target_tr = Timerange(timeline_cursor, target_duration)

            seg = VideoSegment(
                materials[source_key],
                target_tr,
                source_timerange=source_tr,
                speed=speed,
            )

            # Handle transition from previous entry
            _apply_transition(seg, entry, i, timeline)

            segments.append(seg)
            timeline_cursor += target_duration

        elif entry_type == "title-card":
            text: str = entry.get("text", "")
            subtitle: str | None = entry.get("subtitle")
            background: str = entry.get("background", "#1e1b4b")
            duration_sec: float = entry.get("durationSec", 3.0)

            card_path = draft_dir / f"title_card_{title_card_idx}.png"
            generate_title_card(text, subtitle, background, width, height, card_path)
            title_card_idx += 1

            card_mat = VideoMaterial(str(card_path))
            script.add_material(card_mat)

            card_duration_us = int(duration_sec * SEC)
            target_tr = Timerange(timeline_cursor, card_duration_us)
            source_tr = Timerange(0, card_duration_us)

            seg = VideoSegment(card_mat, target_tr, source_timerange=source_tr)

            _apply_transition(seg, entry, i, timeline)

            segments.append(seg)
            timeline_cursor += card_duration_us

    # Add all segments to the script (use default video track — no track_name needed for single track)
    for seg in segments:
        script.add_segment(seg)

    script.save()

    draft_path = drafts_dir / draft_name
    _print_instructions(draft_path)
    return draft_path


def _apply_transition(seg: VideoSegment, entry: dict[str, Any], index: int, timeline: list[dict[str, Any]]) -> None:
    """Apply transition to a segment if the entry or previous entry specifies one."""
    transition_data: dict[str, Any] | None = entry.get("transition")
    if not transition_data:
        return
    transition_type_str: str = transition_data.get("type", "none")
    if transition_type_str == "none":
        return
    mapped = TRANSITION_MAP.get(transition_type_str)
    if mapped is None:
        print(f"WARNING: unknown transition type '{transition_type_str}' — skipping", file=sys.stderr)
        return
    duration_sec: float = transition_data.get("durationSec", 0.5)
    seg.add_transition(mapped, duration=int(duration_sec * SEC))


def _print_instructions(draft_path: Path) -> None:
    """Print instructions for opening the draft in CapCut."""
    print(f"\n✅ CapCut draft created: {draft_path}")
    print()
    print("To open in CapCut desktop:")
    print("  1. Open CapCut desktop application")
    print("  2. Click 'Import project' or look for the draft in your projects list")
    print(f"  3. The draft '{draft_path.name}' should appear automatically")
    print("  4. If not visible, restart CapCut to refresh the drafts list")
    print()


# ── Entrypoint ────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    export_capcut(args)


if __name__ == "__main__":
    main()
