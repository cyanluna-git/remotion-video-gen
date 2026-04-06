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
    AudioMaterial,
    AudioSegment,
    ClipSettings,
    DraftFolder,
    SEC,
    TextBackground,
    TextSegment,
    TextStyle,
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

# ── Caption / overlay constants ───────────────────────────────────────────────

MIN_DURATION_US: int = 500_000  # 0.5 s clamp

POSITION_Y_MAP: dict[str, float] = {
    "top": -0.7,
    "center": 0.0,
    "bottom": 0.7,
}

# captionClass → TextStyle presets (size is pyCapCut float units, not pt)
CAPTION_STYLES: dict[str, dict[str, Any]] = {
    "subtitle": {"size": 8.0, "bold": False, "color": (1.0, 1.0, 1.0)},
    "announcement": {"size": 12.0, "bold": True, "color": (1.0, 1.0, 1.0)},
    "technical-term": {"size": 8.0, "bold": True, "color": (1.0, 0.95, 0.4)},
}

DEFAULT_CAPTION_BG_HEX = "#000000"
DEFAULT_CAPTION_BG_ALPHA = 0.6

TEXT_TRACK_NAME = "overlays"
CAPTIONS_TRACK_NAME = "captions"

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
    parser.add_argument(
        "--captions",
        type=str,
        choices=["whisper", "capcut-ai", "none"],
        default="whisper",
        help="Caption mode: whisper (SRT import), capcut-ai (use CapCut AI), none (no captions)",
    )
    parser.add_argument(
        "--voiceover-manifest",
        type=Path,
        default=None,
        help="Path to voiceover manifest JSON. Auto-probes .work/voiceover/manifest.json when omitted.",
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


def _captions_json_to_srt(captions: list[dict[str, Any]], output_path: Path) -> Path:
    """Convert [{startSec, endSec, text}] to SRT format and write to output_path."""
    lines: list[str] = []
    for idx, cap in enumerate(captions, start=1):
        start_sec: float = cap.get("startSec", 0.0)
        end_sec: float = cap.get("endSec", start_sec + 0.5)
        text: str = cap.get("text", "")
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(start_sec)} --> {_format_srt_time(end_sec)}")
        lines.append(text)
        lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm."""
    total_ms = int(round(seconds * 1000))
    hours = total_ms // 3_600_000
    minutes = (total_ms % 3_600_000) // 60_000
    secs = (total_ms % 60_000) // 1_000
    millis = total_ms % 1_000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _create_caption_text_segment(
    overlay: dict[str, Any],
    clip_timeline_start_us: int,
    clip_duration_us: int,
    speed: float,
) -> TextSegment:
    """Create a TextSegment from a caption overlay."""
    start_offset_sec: float = overlay.get("startSec", 0.0)
    duration_sec: float = overlay.get("durationSec", 2.0)

    # Absolute start on timeline (accounting for speed)
    abs_start_us = clip_timeline_start_us + int(start_offset_sec / speed * SEC)
    raw_duration_us = int(duration_sec / speed * SEC)

    # Clamp: min duration
    duration_us = max(raw_duration_us, MIN_DURATION_US)
    # Clamp: don't exceed clip end
    clip_end_us = clip_timeline_start_us + clip_duration_us
    if abs_start_us + duration_us > clip_end_us:
        duration_us = max(clip_end_us - abs_start_us, MIN_DURATION_US)

    text: str = overlay.get("text", "")
    caption_class: str = overlay.get("captionClass", "subtitle")
    position: str = overlay.get("position", "bottom")

    # Style
    style_params = CAPTION_STYLES.get(caption_class, CAPTION_STYLES["subtitle"])
    text_style = TextStyle(**style_params)

    # Position
    transform_y = POSITION_Y_MAP.get(position, POSITION_Y_MAP["bottom"])
    clip_settings = ClipSettings(transform_y=transform_y)

    # Background for subtitle/announcement
    background: TextBackground | None = None
    if caption_class in ("subtitle", "announcement"):
        background = TextBackground(color=DEFAULT_CAPTION_BG_HEX, alpha=DEFAULT_CAPTION_BG_ALPHA)

    return TextSegment(
        text,
        Timerange(abs_start_us, duration_us),
        style=text_style,
        clip_settings=clip_settings,
        background=background,
    )


def _create_highlight_segment(
    overlay: dict[str, Any],
    clip_timeline_start_us: int,
    clip_duration_us: int,
    speed: float,
) -> TextSegment:
    """Create a TextSegment (space with colored background) from a highlight overlay."""
    start_offset_sec: float = overlay.get("startSec", 0.0)
    duration_sec: float = overlay.get("durationSec", 2.0)

    abs_start_us = clip_timeline_start_us + int(start_offset_sec / speed * SEC)
    raw_duration_us = int(duration_sec / speed * SEC)
    duration_us = max(raw_duration_us, MIN_DURATION_US)
    clip_end_us = clip_timeline_start_us + clip_duration_us
    if abs_start_us + duration_us > clip_end_us:
        duration_us = max(clip_end_us - abs_start_us, MIN_DURATION_US)

    region: dict[str, float] = overlay.get("region", {})
    color_str: str = overlay.get("color", "#FFFF00")
    color_hex = extract_hex_color(color_str)

    # Map region to ClipSettings: x,y center -> transform_x/y (0=center, ±1=edge)
    rx = region.get("x", 0.5)
    ry = region.get("y", 0.5)
    rw = region.get("width", 0.2)
    rh = region.get("height", 0.1)
    transform_x = (rx + rw / 2 - 0.5) * 2.0
    transform_y = (ry + rh / 2 - 0.5) * 2.0

    clip_settings = ClipSettings(
        transform_x=transform_x,
        transform_y=transform_y,
        scale_x=rw,
        scale_y=rh,
    )
    background = TextBackground(color=color_hex, alpha=0.35)

    return TextSegment(
        " ",
        Timerange(abs_start_us, duration_us),
        clip_settings=clip_settings,
        background=background,
    )


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


# ── Voiceover helpers ─────────────────────────────────────────────────────────

VOICEOVER_TRACK_PREFIX = "voiceover"


def load_voiceover_manifest(path: Path | None, video_dir: Path) -> dict[str, Any] | None:
    """Load voiceover manifest JSON, auto-probing if *path* is None.

    Returns the parsed manifest dict or None (with a warning) when the file
    is missing or the manifest contains no tracks.
    """
    if path is None:
        path = (video_dir / ".work" / "voiceover" / "manifest.json").resolve()
        if not path.exists():
            # Also try video_dir parent (common layout: video_dir=.work/)
            alt = (video_dir / "voiceover" / "manifest.json").resolve()
            if alt.exists():
                path = alt
    else:
        path = path.resolve()

    if not path.exists():
        print(f"WARNING: voiceover manifest not found at {path} — skipping audio mapping", file=sys.stderr)
        return None

    with path.open("r", encoding="utf-8") as f:
        manifest: dict[str, Any] = json.load(f)

    tracks = manifest.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        print("WARNING: voiceover manifest has no tracks — skipping audio mapping", file=sys.stderr)
        return None

    return manifest


def _add_voiceover_audio(
    script: Any,
    manifest: dict[str, Any],
    video_dir: Path,
    timeline_end_us: int,
) -> None:
    """Map each voiceover manifest track to a pyCapCut AudioSegment on dedicated audio tracks."""
    tracks: list[dict[str, Any]] = manifest.get("tracks", [])
    if not tracks:
        return

    # Greedy track allocation: (track_name, end_us)
    audio_tracks: list[tuple[str, int]] = []

    for idx, track in enumerate(tracks):
        src_rel: str = track.get("src", "")
        src_path = Path(src_rel)
        if not src_path.is_absolute():
            src_path = (video_dir / src_path).resolve()
        else:
            src_path = src_path.resolve()

        if not src_path.exists():
            print(f"WARNING: voiceover source not found: {src_path} — skipping track '{track.get('id')}'", file=sys.stderr)
            continue

        start_sec: float = track.get("startSec", 0.0)
        duration_sec: float = track.get("durationSec", 0.0)
        offset_sec: float = track.get("offsetSec", 0.0)
        playback_rate: float = track.get("playbackRate", 1.0)
        volume: float = track.get("volume", 1.0)
        fade_in_sec: float = track.get("fadeInSec", 0.0)
        fade_out_sec: float = track.get("fadeOutSec", 0.0)

        if duration_sec <= 0:
            print(f"WARNING: voiceover track '{track.get('id')}' has durationSec <= 0 — skipping", file=sys.stderr)
            continue

        # Timeline position in microseconds
        target_start_us = int(start_sec * SEC)
        target_duration_us = int(duration_sec / playback_rate * SEC) if playback_rate != 1.0 else int(duration_sec * SEC)

        # Warn + clamp if start exceeds timeline end
        if target_start_us >= timeline_end_us > 0:
            print(
                f"WARNING: voiceover track '{track.get('id')}' starts at {start_sec}s "
                f"which is beyond timeline end ({timeline_end_us / SEC:.3f}s) — clamping",
                file=sys.stderr,
            )
            target_start_us = max(0, timeline_end_us - target_duration_us)

        # Source timerange (offsetSec into the audio file)
        source_start_us = int(offset_sec * SEC)
        source_duration_us = int(duration_sec * SEC)
        source_tr = Timerange(source_start_us, source_duration_us)

        target_tr = Timerange(target_start_us, target_duration_us)

        # Create material + segment
        mat = AudioMaterial(str(src_path))
        script.add_material(mat)

        speed_param: float | None = playback_rate if playback_rate != 1.0 else None
        seg = AudioSegment(
            mat,
            target_tr,
            source_timerange=source_tr,
            speed=speed_param,
            volume=volume,
        )

        # Fade in/out
        if fade_in_sec > 0 or fade_out_sec > 0:
            seg.add_fade(int(fade_in_sec * SEC), int(fade_out_sec * SEC))

        # Place on a non-overlapping audio track (greedy)
        seg_start = target_start_us
        seg_end = target_start_us + target_duration_us
        placed = False
        for t_idx, (t_name, t_end) in enumerate(audio_tracks):
            if seg_start >= t_end:
                script.add_segment(seg, t_name)
                audio_tracks[t_idx] = (t_name, seg_end)
                placed = True
                break
        if not placed:
            track_name = f"{VOICEOVER_TRACK_PREFIX}_{len(audio_tracks)}"
            script.add_track(TrackType.audio, track_name)
            script.add_segment(seg, track_name)
            audio_tracks.append((track_name, seg_end))

    print(f"  Mapped {len(tracks)} voiceover track(s) to {len(audio_tracks)} audio track(s)", file=sys.stderr)


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
    text_segments: list[TextSegment] = []
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

            # Process overlays for this clip
            for overlay in entry.get("overlays", []):
                overlay_type: str = overlay.get("type", "")
                try:
                    if overlay_type == "caption":
                        text_segments.append(
                            _create_caption_text_segment(overlay, timeline_cursor, target_duration, speed)
                        )
                    elif overlay_type == "highlight":
                        text_segments.append(
                            _create_highlight_segment(overlay, timeline_cursor, target_duration, speed)
                        )
                except Exception as exc:
                    print(f"WARNING: failed to create overlay at clip {i}: {exc}", file=sys.stderr)

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

    # Add all video segments
    for seg in segments:
        script.add_segment(seg)

    # Add text overlay segments, distributing across tracks to avoid overlaps
    if text_segments:
        _add_text_segments_to_tracks(script, text_segments)

    # Handle global captions (--captions flag)
    captions_mode: str = getattr(args, "captions", "whisper")
    if captions_mode == "whisper":
        global_captions: list[dict[str, Any]] = edit_data.get("captions", [])
        if global_captions:
            srt_path = (args.video_dir / "captions.srt").resolve()
            _captions_json_to_srt(global_captions, srt_path)
            script.add_track(TrackType.text, CAPTIONS_TRACK_NAME)
            caption_style = TextStyle(size=8.0, bold=False, color=(1.0, 1.0, 1.0))
            caption_clip = ClipSettings(transform_y=0.7)
            script.import_srt(str(srt_path), CAPTIONS_TRACK_NAME, text_style=caption_style, clip_settings=caption_clip)
            print(f"  Imported {len(global_captions)} captions from edit.json via SRT", file=sys.stderr)
        else:
            print("  No global captions in edit.json — skipping SRT import", file=sys.stderr)
    elif captions_mode == "capcut-ai":
        print(
            "\n💡 Captions mode: capcut-ai\n"
            "   Open the draft in CapCut and use Auto captions (Text → Auto captions)\n"
            "   to generate AI-powered captions.",
            file=sys.stderr,
        )
    # captions_mode == "none": do nothing

    # ── Voiceover audio mapping ───────────────────────────────────────────
    vo_manifest_path: Path | None = getattr(args, "voiceover_manifest", None)
    vo_manifest = load_voiceover_manifest(vo_manifest_path, args.video_dir)
    if vo_manifest is not None:
        _add_voiceover_audio(script, vo_manifest, args.video_dir, timeline_cursor)

    script.save()

    draft_path = drafts_dir / draft_name
    _print_instructions(draft_path)
    return draft_path


def _add_text_segments_to_tracks(script: Any, text_segments: list[TextSegment]) -> None:
    """Distribute text segments across tracks to avoid overlap errors.

    Uses a greedy approach: each track maintains an end-time watermark.
    A segment goes to the first track where it doesn't overlap.
    """
    tracks: list[tuple[str, int]] = []  # (track_name, end_us)

    for tseg in text_segments:
        seg_start = tseg.start
        seg_end = seg_start + tseg.duration
        placed = False
        for idx, (track_name, track_end) in enumerate(tracks):
            if seg_start >= track_end:
                script.add_segment(tseg, track_name)
                tracks[idx] = (track_name, seg_end)
                placed = True
                break
        if not placed:
            track_name = f"{TEXT_TRACK_NAME}_{len(tracks)}"
            script.add_track(TrackType.text, track_name)
            script.add_segment(tseg, track_name)
            tracks.append((track_name, seg_end))


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
