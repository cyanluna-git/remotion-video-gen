"""Canonical contracts for multimodal pipeline artifacts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "1.0"


class MultimodalContractError(ValueError):
    """Raised when a multimodal artifact does not match the canonical contract."""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def job_artifact_paths(job_dir: Path) -> dict[str, Path]:
    """Return canonical job-scoped artifact paths for multimodal stages."""
    return {
        "voiceover_dir": job_dir / "voiceover",
        "voiceover_manifest": job_dir / "voiceover" / "manifest.json",
        "analysis_dir": job_dir / "analysis",
        "clip_ranking": job_dir / "analysis" / "clip-ranking.json",
        "qa_output": job_dir / "output" / "qa.json",
        "qa_heuristic": job_dir / "output" / "qa.heuristic.json",
        "qa_vision": job_dir / "output" / "qa.vision.json",
    }


def _as_relative_job_path(raw_path: Any) -> str:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise MultimodalContractError("Track src must be a non-empty string.")
    normalized = raw_path.strip().replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("../"):
        raise MultimodalContractError("Track src must be job-relative, not absolute.")
    normalized = normalized.lstrip("./")
    return normalized


def _provider_meta(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise MultimodalContractError("provider must be an object when present.")

    name = str(payload.get("name") or "").strip()
    if not name:
        raise MultimodalContractError("provider.name is required when provider is present.")

    normalized = {"name": name}
    for key in ("model", "voice", "revision", "notes"):
        value = payload.get(key)
        if value is not None:
            normalized[key] = value
    return normalized


def normalize_voiceover_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize a provider-agnostic voiceover manifest."""
    if not isinstance(payload, dict):
        raise MultimodalContractError("Voiceover manifest must be a JSON object.")

    raw_tracks = payload.get("tracks")
    if not isinstance(raw_tracks, list) or not raw_tracks:
        raise MultimodalContractError("Voiceover manifest requires a non-empty tracks array.")

    normalized_tracks: list[dict[str, Any]] = []
    total_duration = 0.0
    for index, track in enumerate(raw_tracks):
        if not isinstance(track, dict):
            raise MultimodalContractError(f"tracks[{index}] must be an object.")

        start_sec = float(track.get("startSec", 0.0))
        duration_sec = float(track.get("durationSec", 0.0))
        if start_sec < 0:
            raise MultimodalContractError(f"tracks[{index}].startSec must be >= 0.")
        if duration_sec <= 0:
            raise MultimodalContractError(f"tracks[{index}].durationSec must be > 0.")

        normalized_track = {
            "id": str(track.get("id") or f"track-{index + 1}"),
            "label": str(track.get("label") or f"Track {index + 1}"),
            "src": _as_relative_job_path(track.get("src")),
            "startSec": round(start_sec, 3),
            "durationSec": round(duration_sec, 3),
            "text": str(track.get("text") or "").strip(),
        }

        offset_sec = track.get("offsetSec")
        if offset_sec is not None:
            normalized_track["offsetSec"] = round(float(offset_sec), 3)

        playback_rate = track.get("playbackRate")
        if playback_rate is not None:
            normalized_track["playbackRate"] = float(playback_rate)

        volume = track.get("volume")
        if volume is not None:
            normalized_track["volume"] = float(volume)

        track_provider = _provider_meta(track.get("provider"))
        if track_provider is not None:
            normalized_track["provider"] = track_provider

        normalized_tracks.append(normalized_track)
        total_duration += duration_sec

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    normalized_summary = {
        "trackCount": len(normalized_tracks),
        "totalDurationSec": round(float(summary.get("totalDurationSec", total_duration)), 3),
        "status": str(summary.get("status") or payload.get("status") or "ready"),
    }

    revision = payload.get("revision")
    normalized_revision = revision if isinstance(revision, dict) else {}

    normalized = {
        "version": str(payload.get("version") or CONTRACT_VERSION),
        "artifact": "voiceover-manifest",
        "generatedAt": str(payload.get("generatedAt") or utcnow_iso()),
        "status": normalized_summary["status"],
        "tracks": normalized_tracks,
        "summary": normalized_summary,
        "revision": normalized_revision,
    }

    provider = _provider_meta(payload.get("provider"))
    if provider is not None:
        normalized["provider"] = provider

    return normalized


def normalize_clip_ranking(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize clip-ranking output derived from analysis and optional models."""
    if not isinstance(payload, dict):
        raise MultimodalContractError("Clip-ranking artifact must be a JSON object.")

    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise MultimodalContractError("Clip-ranking artifact requires a non-empty candidates array.")

    candidates: list[dict[str, Any]] = []
    for index, candidate in enumerate(raw_candidates):
        if not isinstance(candidate, dict):
            raise MultimodalContractError(f"candidates[{index}] must be an object.")

        start_sec = float(candidate.get("startSec", 0.0))
        end_sec = float(candidate.get("endSec", 0.0))
        if end_sec <= start_sec:
            raise MultimodalContractError(
                f"candidates[{index}] must have endSec greater than startSec."
            )

        signals = candidate.get("sourceSignals")
        if not isinstance(signals, list) or not signals:
            raise MultimodalContractError(
                f"candidates[{index}].sourceSignals must be a non-empty array."
            )

        normalized = {
            "id": str(candidate.get("id") or f"candidate-{index + 1}"),
            "startSec": round(start_sec, 3),
            "endSec": round(end_sec, 3),
            "score": float(candidate.get("score", 0.0)),
            "sourceSignals": [str(signal) for signal in signals],
        }

        rationale = str(candidate.get("rationale") or "").strip()
        if rationale:
            normalized["rationale"] = rationale

        transcript_excerpt = str(candidate.get("transcriptExcerpt") or "").strip()
        if transcript_excerpt:
            normalized["transcriptExcerpt"] = transcript_excerpt

        provider = _provider_meta(candidate.get("provider"))
        if provider is not None:
            normalized["provider"] = provider

        candidates.append(normalized)

    candidates.sort(key=lambda item: item["score"], reverse=True)
    for index, candidate in enumerate(candidates, start=1):
        candidate["rank"] = index

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    normalized_summary = {
        "candidateCount": len(candidates),
        "topCandidateIds": [
            str(candidate_id)
            for candidate_id in summary.get("topCandidateIds", [c["id"] for c in candidates[:3]])
        ],
        "status": str(summary.get("status") or payload.get("status") or "ready"),
    }

    normalized = {
        "version": str(payload.get("version") or CONTRACT_VERSION),
        "artifact": "clip-ranking",
        "generatedAt": str(payload.get("generatedAt") or utcnow_iso()),
        "status": normalized_summary["status"],
        "candidates": candidates,
        "summary": normalized_summary,
        "revision": payload.get("revision") if isinstance(payload.get("revision"), dict) else {},
    }

    provider = _provider_meta(payload.get("provider"))
    if provider is not None:
        normalized["provider"] = provider

    return normalized


def normalize_qa_artifact(
    heuristic_review: dict[str, Any],
    vision_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap the current heuristic review in the canonical multimodal QA contract."""
    if not isinstance(heuristic_review, dict):
        raise MultimodalContractError("Heuristic QA review must be an object.")

    summary = heuristic_review.get("summary")
    if not isinstance(summary, dict):
        raise MultimodalContractError("Heuristic QA review requires a summary object.")

    combined = {
        "version": str(heuristic_review.get("version") or CONTRACT_VERSION),
        "artifact": "qa-review",
        "generatedAt": str(heuristic_review.get("generatedAt") or utcnow_iso()),
        "method": str(heuristic_review.get("method") or "heuristic"),
        "videoDurationSec": heuristic_review.get("videoDurationSec"),
        "thumbnail": deepcopy(heuristic_review.get("thumbnail")),
        "checks": deepcopy(heuristic_review.get("checks", {})),
        "summary": deepcopy(summary),
        "autoRerender": bool(heuristic_review.get("autoRerender", False)),
        "reviews": {
            "heuristic": deepcopy(heuristic_review),
        },
    }

    if vision_review is not None:
        if not isinstance(vision_review, dict):
            raise MultimodalContractError("Vision QA review must be an object when present.")
        combined["reviews"]["vision"] = deepcopy(vision_review)

        vision_summary = vision_review.get("summary")
        if isinstance(vision_summary, dict):
            heuristic_status = str(summary.get("status") or "pass")
            vision_status = str(vision_summary.get("status") or "pass")
            status_order = {"pass": 0, "warn": 1, "fail": 2}
            combined["summary"]["status"] = max(
                (heuristic_status, vision_status),
                key=lambda item: status_order.get(item, -1),
            )
            combined["summary"]["warningCount"] = int(summary.get("warningCount", 0)) + int(
                vision_summary.get("warningCount", 0)
            )
            combined["summary"]["failCount"] = int(summary.get("failCount", 0)) + int(
                vision_summary.get("failCount", 0)
            )

    return combined
