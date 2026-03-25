"""Rebuild edit.json timeline with jump-cuts based on narration timing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild timeline with jump-cuts aligned to voiceover narration.",
    )
    parser.add_argument("--manifest", type=Path, required=True, help="Voiceover manifest JSON")
    parser.add_argument("--scenario", type=Path, required=True, help="Scenario JSON (section boundaries)")
    parser.add_argument("--base-edit", type=Path, default=None, help="Base edit.json to inherit structure from")
    parser.add_argument("--captions", type=Path, default=None, help="Captions JSON for overlay placement")
    parser.add_argument("--output", type=Path, required=True, help="Output edit.json path")
    parser.add_argument("--pad-before", type=float, default=0.5, help="Seconds before narration start (default: 0.5)")
    parser.add_argument("--pad-after", type=float, default=1.0, help="Seconds after narration end (default: 1.0)")
    parser.add_argument("--merge-gap", type=float, default=1.5, help="Merge clips if gap < this (default: 1.5)")
    parser.add_argument("--original-volume", type=float, default=0.0, help="Original audio volume (default: 0)")
    parser.add_argument("--title-card-duration", type=float, default=2.0, help="Title card duration (default: 2.0)")
    parser.add_argument("--video-duration", type=float, default=None, help="Source video duration for clamping")
    return parser.parse_args(argv)


def load_json(path: Path, label: str) -> Any:
    if not path.exists():
        print(f"ERROR: {label} not found: {path}", file=sys.stderr)
        raise SystemExit(1)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_section_index(start_sec: float, sections: list[dict[str, Any]]) -> int:
    result = 0
    for i, sec in enumerate(sections):
        if start_sec >= float(sec["timeRange"]["startSec"]):
            result = i
    return result


def build_clip_ranges(
    tracks: list[dict[str, Any]],
    *,
    pad_before: float,
    pad_after: float,
    video_duration: float | None,
) -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []
    for track in sorted(tracks, key=lambda t: t["startSec"]):
        clip_start = max(0.0, track["startSec"] - pad_before)
        clip_end = track["startSec"] + track["durationSec"] + pad_after
        if video_duration is not None:
            clip_end = min(clip_end, video_duration)
        ranges.append({
            "clipStart": round(clip_start, 3),
            "clipEnd": round(clip_end, 3),
            "tracks": [track],
        })
    return ranges


def merge_nearby_clips(
    ranges: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    *,
    merge_gap: float,
) -> list[dict[str, Any]]:
    if not ranges:
        return []

    merged: list[dict[str, Any]] = [ranges[0]]
    for curr in ranges[1:]:
        prev = merged[-1]
        gap = curr["clipStart"] - prev["clipEnd"]
        prev_section = find_section_index(prev["tracks"][0]["startSec"], sections)
        curr_section = find_section_index(curr["tracks"][0]["startSec"], sections)

        if gap < merge_gap and prev_section == curr_section:
            prev["clipEnd"] = max(prev["clipEnd"], curr["clipEnd"])
            prev["tracks"].extend(curr["tracks"])
        else:
            merged.append(curr)

    return merged


def build_timeline(
    clip_groups: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    captions: list[dict[str, Any]] | None,
    *,
    title_card_duration: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    timeline: list[dict[str, Any]] = []
    remapped_tracks: list[dict[str, Any]] = []
    cursor = 0.0
    prev_section_idx = -1

    title_bg = "linear-gradient(135deg, #c8102e, #1e1b4b)"
    if sections:
        style = sections[0].get("style", {}) if isinstance(sections[0], dict) else {}
        # style is at scenario level, not section level — handle in caller
    # We'll accept title_bg as default; caller can override via scenario style

    for group in clip_groups:
        first_track = group["tracks"][0]
        section_idx = find_section_index(first_track["startSec"], sections)

        if section_idx > prev_section_idx:
            timeline.append({
                "type": "title-card",
                "text": sections[section_idx]["title"],
                "durationSec": title_card_duration,
                "background": title_bg,
            })
            cursor += title_card_duration
            prev_section_idx = section_idx

        clip_start = group["clipStart"]
        clip_end = group["clipEnd"]

        overlays = _find_captions_for_clip(captions, clip_start, clip_end) if captions else []

        entry: dict[str, Any] = {
            "type": "clip",
            "source": "main",
            "startSec": clip_start,
            "endSec": clip_end,
            "transition": {"type": "fade", "durationSec": 0.3},
        }
        if overlays:
            entry["overlays"] = overlays

        timeline.append(entry)

        for track in group["tracks"]:
            new_start = cursor + (track["startSec"] - clip_start)
            remapped_tracks.append({
                **track,
                "startSec": round(new_start, 3),
            })

        cursor += clip_end - clip_start

    return timeline, remapped_tracks


def _find_captions_for_clip(
    captions: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
) -> list[dict[str, Any]]:
    overlays: list[dict[str, Any]] = []
    for cap in captions:
        cap_start = float(cap.get("startSec", cap.get("start", 0)))
        cap_dur = float(cap.get("durationSec", cap.get("duration", 2.0)))
        if cap_start >= clip_start and cap_start < clip_end:
            overlays.append({
                "type": "caption",
                "text": cap.get("text", ""),
                "startSec": round(cap_start - clip_start, 3),
                "durationSec": round(cap_dur, 3),
                "position": "bottom",
            })
    return overlays


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    manifest = load_json(args.manifest, "Voiceover manifest")
    scenario = load_json(args.scenario, "Scenario")
    sections = scenario.get("sections", [])
    tracks = manifest.get("tracks", [])

    if not tracks:
        print("ERROR: No voiceover tracks in manifest", file=sys.stderr)
        raise SystemExit(1)

    captions = None
    if args.captions and args.captions.exists():
        captions = load_json(args.captions, "Captions")

    # Build base edit structure
    if args.base_edit and args.base_edit.exists():
        base = load_json(args.base_edit, "Base edit")
    else:
        base = {
            "version": "1.0",
            "fps": 30,
            "resolution": {"width": 1920, "height": 1080},
            "sources": {"main": "recordings/normalized.mp4"},
        }

    # Get title card style from scenario
    title_bg = scenario.get("style", {}).get(
        "titleCardBackground", "linear-gradient(135deg, #c8102e, #1e1b4b)"
    )

    # Step 1: Build clip ranges from voiceover tracks
    clip_ranges = build_clip_ranges(
        tracks,
        pad_before=args.pad_before,
        pad_after=args.pad_after,
        video_duration=args.video_duration,
    )

    # Step 2: Merge nearby clips within same section
    merged = merge_nearby_clips(clip_ranges, sections, merge_gap=args.merge_gap)

    # Step 3: Build timeline with title cards + remap voiceover positions
    timeline, remapped_tracks = build_timeline(
        merged, sections, captions, title_card_duration=args.title_card_duration,
    )

    # Inject title card background
    for entry in timeline:
        if entry.get("type") == "title-card":
            entry["background"] = title_bg

    # Step 4: Assemble final edit.json
    edit = {
        "version": base.get("version", "1.0"),
        "fps": base.get("fps", 30),
        "resolution": base.get("resolution", {"width": 1920, "height": 1080}),
        "sources": base.get("sources", {"main": "recordings/normalized.mp4"}),
        "timeline": timeline,
        "audio": {
            "originalAudio": {"volume": args.original_volume},
            "voiceover": {"tracks": remapped_tracks},
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(edit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Summary
    clips = [e for e in timeline if e["type"] == "clip"]
    titles = [e for e in timeline if e["type"] == "title-card"]
    total_clip_dur = sum(e["endSec"] - e["startSec"] for e in clips)
    total_title_dur = sum(e["durationSec"] for e in titles)
    total = total_clip_dur + total_title_dur

    print(f"\n{'=' * 50}")
    print("Timeline Rebuild Summary")
    print(f"{'=' * 50}")
    print(f"  Clips        : {len(clips)}")
    print(f"  Title cards   : {len(titles)}")
    print(f"  Voiceover     : {len(remapped_tracks)} tracks")
    print(f"  Duration      : {int(total // 60)}m {total % 60:.1f}s")
    print(f"  Original vol  : {args.original_volume}")
    print(f"{'=' * 50}")
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
