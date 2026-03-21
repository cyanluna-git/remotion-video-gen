"""Generate representative thumbnails and heuristic QA artifacts for rendered videos."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from multimodal_contracts import normalize_qa_artifact
    from vision_review import VisionReviewError, VisionReviewRequest, build_vision_review_provider
except ModuleNotFoundError:
    from scripts.multimodal_contracts import normalize_qa_artifact
    from scripts.vision_review import (
        VisionReviewError,
        VisionReviewRequest,
        build_vision_review_provider,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate post-render QA JSON and a representative thumbnail.",
    )
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--thumbnail-output", type=Path, required=True)
    parser.add_argument("--edit-json", type=Path, default=None)
    parser.add_argument(
        "--vision-provider",
        default=os.environ.get("VISION_QA_PROVIDER", ""),
        help="Optional vision QA provider (e.g. openai, mock)",
    )
    parser.add_argument(
        "--vision-model",
        default=os.environ.get("VISION_QA_MODEL", "gpt-4.1-mini"),
        help="Vision QA model name (default: gpt-4.1-mini)",
    )
    parser.add_argument(
        "--vision-detail",
        default=os.environ.get("VISION_QA_DETAIL", "low"),
        help="Vision QA image detail level (default: low)",
    )
    return parser.parse_args(argv)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def get_video_duration(video_path: Path) -> float:
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
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def sample_timestamps(duration_sec: float) -> list[float]:
    if duration_sec <= 0:
        return [0.0]
    if duration_sec < 3:
        return [round(duration_sec / 2, 3)]

    upper_bound = max(duration_sec - 0.25, 0.0)
    raw = [duration_sec * ratio for ratio in (0.18, 0.38, 0.58, 0.78)]
    timestamps = []
    for value in raw:
        clamped = round(min(max(value, 0.25), upper_bound), 3)
        if clamped not in timestamps:
            timestamps.append(clamped)
    return timestamps or [0.0]


def extract_frame(video_path: Path, time_sec: float, output_path: Path) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{time_sec:.3f}",
        "-i",
        str(video_path),
        "-vframes",
        "1",
        "-q:v",
        "4",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and output_path.exists()


def probe_frame_luma(video_path: Path, time_sec: float) -> Optional[float]:
    cmd = [
        "ffmpeg",
        "-ss",
        f"{time_sec:.3f}",
        "-i",
        str(video_path),
        "-vf",
        "signalstats",
        "-vframes",
        "1",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    text = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"YAVG:([0-9.]+)", text)
    if not match:
        return None
    return float(match.group(1))


def select_representative_thumbnail(
    video_path: Path,
    thumbnail_output: Path,
    duration_sec: float,
) -> dict[str, Any]:
    candidates_dir = thumbnail_output.parent / "qa-frames"
    candidates: list[dict[str, Any]] = []

    for index, time_sec in enumerate(sample_timestamps(duration_sec), start=1):
        candidate_path = candidates_dir / f"sample-{index}.jpg"
        if not extract_frame(video_path, time_sec, candidate_path):
            candidates.append(
                {
                    "timeSec": time_sec,
                    "path": str(candidate_path),
                    "selected": False,
                    "extracted": False,
                }
            )
            continue

        file_size = candidate_path.stat().st_size
        yavg = probe_frame_luma(video_path, time_sec)
        score = file_size + ((yavg or 0.0) * 1000)
        candidates.append(
            {
                "timeSec": time_sec,
                "path": str(candidate_path),
                "fileSize": file_size,
                "yavg": yavg,
                "score": score,
                "selected": False,
                "extracted": True,
            }
        )

    extracted = [candidate for candidate in candidates if candidate.get("extracted")]
    fallback_used = False
    selected: dict[str, Any] | None = None

    viable = [
        candidate
        for candidate in extracted
        if candidate.get("yavg") is None or candidate.get("yavg", 0) >= 20
    ]
    pool = viable or extracted
    if pool:
        selected = max(pool, key=lambda candidate: candidate.get("score", 0))
    else:
        fallback_used = True
        if extract_frame(video_path, 0.0, thumbnail_output):
            selected = {
                "timeSec": 0.0,
                "path": str(thumbnail_output),
                "selected": True,
                "extracted": True,
                "fallback": True,
            }

    if selected and Path(selected["path"]).exists():
        thumbnail_output.parent.mkdir(parents=True, exist_ok=True)
        source_path = Path(selected["path"])
        if source_path.resolve() != thumbnail_output.resolve():
            thumbnail_output.write_bytes(source_path.read_bytes())
        for candidate in candidates:
            if candidate.get("path") == str(source_path):
                candidate["selected"] = True
                break
    else:
        raise RuntimeError("Failed to generate representative thumbnail.")

    return {
        "path": str(thumbnail_output),
        "selectedTimeSec": selected["timeSec"],
        "fallbackUsed": fallback_used or bool(selected.get("fallback")),
        "candidates": candidates,
    }


def load_edit_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, dict) and isinstance(payload.get("script"), dict):
        return payload["script"]
    return payload if isinstance(payload, dict) else None


def analyze_edit_contract(edit: dict[str, Any] | None) -> dict[str, Any]:
    if not edit:
        return {
            "subtitleOverlapRisk": {"status": "not_available", "issues": []},
            "transitionSmoothness": {"status": "not_available", "issues": []},
            "timingReadability": {"status": "not_available", "issues": []},
        }

    timeline = edit.get("timeline", [])
    overlap_issues: list[dict[str, Any]] = []
    transition_issues: list[dict[str, Any]] = []
    readability_issues: list[dict[str, Any]] = []

    for entry_index, entry in enumerate(timeline):
        if not isinstance(entry, dict):
            continue

        transition = entry.get("transition")
        if isinstance(transition, dict):
            duration = float(transition.get("durationSec", 0))
            if duration < 0.2 or duration > 1.25:
                transition_issues.append(
                    {
                        "entryIndex": entry_index,
                        "type": transition.get("type"),
                        "durationSec": duration,
                    }
                )

        if entry.get("type") != "clip":
            continue

        overlays = entry.get("overlays", [])
        captions = [
            overlay
            for overlay in overlays
            if isinstance(overlay, dict) and overlay.get("type") == "caption"
        ]
        captions.sort(key=lambda overlay: float(overlay.get("startSec", 0)))

        previous_end = None
        for overlay in captions:
            start_sec = float(overlay.get("startSec", 0))
            duration_sec = max(float(overlay.get("durationSec", 0)), 0.0)
            end_sec = start_sec + duration_sec
            text = str(overlay.get("text", "")).strip()

            if previous_end is not None and start_sec < previous_end:
                overlap_issues.append(
                    {
                        "entryIndex": entry_index,
                        "startSec": start_sec,
                        "endSec": end_sec,
                        "text": text,
                    }
                )

            cps = (len(text.replace(" ", "")) / duration_sec) if duration_sec > 0 else 999
            if duration_sec < 1.1 or cps > 18:
                readability_issues.append(
                    {
                        "entryIndex": entry_index,
                        "text": text,
                        "durationSec": round(duration_sec, 3),
                        "charsPerSec": round(cps, 2),
                    }
                )

            previous_end = max(previous_end or 0.0, end_sec)

    return {
        "subtitleOverlapRisk": {
            "status": "warn" if overlap_issues else "pass",
            "issues": overlap_issues,
        },
        "transitionSmoothness": {
            "status": "warn" if transition_issues else "pass",
            "issues": transition_issues,
        },
        "timingReadability": {
            "status": "warn" if readability_issues else "pass",
            "issues": readability_issues,
        },
    }


def evaluate_blank_frames(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    issues = [
        {
            "timeSec": candidate.get("timeSec"),
            "yavg": candidate.get("yavg"),
        }
        for candidate in candidates
        if candidate.get("extracted") and candidate.get("yavg") is not None and candidate.get("yavg", 0) < 18
    ]
    status = "warn" if issues else "pass"
    if candidates and len(issues) > (len(candidates) / 2):
        status = "fail"
    return {"status": status, "issues": issues}


def summarize_checks(checks: dict[str, Any]) -> dict[str, Any]:
    warning_count = 0
    fail_count = 0
    for check in checks.values():
        status = check.get("status")
        if status == "warn":
            warning_count += len(check.get("issues", [])) or 1
        elif status == "fail":
            fail_count += len(check.get("issues", [])) or 1

    summary_status = "fail" if fail_count else "warn" if warning_count else "pass"
    return {
        "status": summary_status,
        "warningCount": warning_count,
        "failCount": fail_count,
    }


def summarize_edit_context(edit: dict[str, Any] | None) -> dict[str, Any]:
    """Return compact edit metadata for the vision reviewer."""
    if not edit:
        return {}

    timeline = edit.get("timeline", [])
    clip_count = sum(1 for entry in timeline if isinstance(entry, dict) and entry.get("type") == "clip")
    caption_count = 0
    for entry in timeline:
        if not isinstance(entry, dict):
            continue
        for overlay in entry.get("overlays", []):
            if isinstance(overlay, dict) and overlay.get("type") == "caption":
                caption_count += 1
    return {
        "timelineEntryCount": len(timeline) if isinstance(timeline, list) else 0,
        "clipCount": clip_count,
        "captionOverlayCount": caption_count,
        "hasVoiceover": bool(edit.get("audio", {}).get("voiceover")) if isinstance(edit.get("audio"), dict) else False,
    }


def build_heuristic_review(video_path: Path, edit_json: Path | None, thumbnail_output: Path) -> dict[str, Any]:
    duration_sec = get_video_duration(video_path)
    thumbnail = select_representative_thumbnail(video_path, thumbnail_output, duration_sec)
    edit = load_edit_json(edit_json)
    checks = analyze_edit_contract(edit)
    checks["blankFrames"] = evaluate_blank_frames(thumbnail["candidates"])
    summary = summarize_checks(checks)

    return {
        "version": "1.0",
        "generatedAt": utcnow_iso(),
        "method": "heuristic",
        "videoDurationSec": round(duration_sec, 3),
        "thumbnail": thumbnail,
        "checks": checks,
        "summary": summary,
        "autoRerender": False,
    }


def maybe_run_vision_review(
    *,
    heuristic_review: dict[str, Any],
    edit: dict[str, Any] | None,
    provider_name: str,
    model: str,
    detail: str,
) -> dict[str, Any] | None:
    """Run an optional second-pass vision review over sampled frames."""
    normalized_provider = provider_name.strip().lower()
    if not normalized_provider or normalized_provider == "none":
        return None

    frame_samples = heuristic_review.get("thumbnail", {}).get("candidates", [])
    if not isinstance(frame_samples, list) or not frame_samples:
        return None

    provider = build_vision_review_provider(
        normalized_provider,
        model=model,
        detail=detail,
    )
    return provider.review(
        VisionReviewRequest(
            frame_samples=frame_samples,
            heuristic_review=heuristic_review,
            edit_context=summarize_edit_context(edit),
        )
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if not args.video.exists():
        print(f"ERROR: Video not found: {args.video}", file=sys.stderr)
        sys.exit(1)

    try:
        heuristic_review = build_heuristic_review(args.video, args.edit_json, args.thumbnail_output)
    except Exception as exc:
        print(f"ERROR: Failed to generate post-render review: {exc}", file=sys.stderr)
        sys.exit(1)

    edit = load_edit_json(args.edit_json)
    vision_review = None
    try:
        vision_review = maybe_run_vision_review(
            heuristic_review=heuristic_review,
            edit=edit,
            provider_name=args.vision_provider,
            model=args.vision_model,
            detail=args.vision_detail,
        )
    except VisionReviewError as exc:
        print(f"WARNING: Vision QA skipped: {exc}", file=sys.stderr)

    combined_review = normalize_qa_artifact(heuristic_review, vision_review)
    heuristic_path = args.output_json.with_name("qa.heuristic.json")
    vision_path = args.output_json.with_name("qa.vision.json")

    heuristic_path.parent.mkdir(parents=True, exist_ok=True)
    heuristic_path.write_text(
        json.dumps(heuristic_review, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if vision_review is not None:
        vision_path.write_text(
            json.dumps(vision_review, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    elif vision_path.exists():
        vision_path.unlink()

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(combined_review, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Saved QA review to: {args.output_json}")
    print(f"Saved representative thumbnail to: {args.thumbnail_output}")


if __name__ == "__main__":
    main()
