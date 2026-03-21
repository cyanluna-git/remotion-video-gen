"""Deterministic clip-ranking helpers built from Step 2 analysis artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from multimodal_contracts import normalize_clip_ranking
except ModuleNotFoundError:
    from scripts.multimodal_contracts import normalize_clip_ranking


@dataclass(frozen=True)
class CandidateWindow:
    """Intermediate candidate clip window."""

    id: str
    start_sec: float
    end_sec: float
    source_signals: list[str]


def build_candidate_windows(
    *,
    transcript_segments: list[dict[str, Any]],
    scenes: list[dict[str, Any]] | None,
    video_duration: float | None,
) -> list[CandidateWindow]:
    """Build explicit candidate windows from scene or transcript structure."""
    if scenes:
        candidates: list[CandidateWindow] = []
        for index, scene in enumerate(scenes, start=1):
            start_sec = float(scene.get("startSec", 0.0))
            end_sec = float(scene.get("endSec", 0.0))
            if end_sec <= start_sec:
                continue
            candidates.append(
                CandidateWindow(
                    id=f"scene-{index:02d}",
                    start_sec=round(start_sec, 3),
                    end_sec=round(end_sec, 3),
                    source_signals=["scenes"],
                )
            )
        if candidates:
            return candidates

    if transcript_segments:
        windows: list[CandidateWindow] = []
        index = 0
        window_id = 1
        while index < len(transcript_segments):
            segment = transcript_segments[index]
            start_sec = float(segment.get("start", 0.0))
            end_sec = float(segment.get("end", start_sec))
            if end_sec <= start_sec:
                index += 1
                continue

            max_end = start_sec + 8.0
            last_end = end_sec
            next_index = index + 1
            while next_index < len(transcript_segments):
                next_segment = transcript_segments[next_index]
                next_start = float(next_segment.get("start", last_end))
                next_end = float(next_segment.get("end", next_start))
                if next_end <= next_start:
                    next_index += 1
                    continue
                if next_start - last_end > 1.5 or next_end > max_end:
                    break
                last_end = next_end
                next_index += 1

            windows.append(
                CandidateWindow(
                    id=f"window-{window_id:02d}",
                    start_sec=round(start_sec, 3),
                    end_sec=round(last_end, 3),
                    source_signals=["transcript"],
                )
            )
            window_id += 1
            index = max(next_index, index + 1)

        if windows:
            return windows

    if video_duration is not None and video_duration > 0:
        windows = []
        start_sec = 0.0
        index = 1
        while start_sec < video_duration - 1e-6:
            end_sec = min(video_duration, start_sec + 8.0)
            if end_sec - start_sec >= 2.0:
                windows.append(
                    CandidateWindow(
                        id=f"window-{index:02d}",
                        start_sec=round(start_sec, 3),
                        end_sec=round(end_sec, 3),
                        source_signals=["video-duration"],
                    )
                )
                index += 1
            start_sec = end_sec
        return windows

    return []


def build_clip_ranking_artifact(
    *,
    transcript_segments: list[dict[str, Any]],
    scenes: list[dict[str, Any]] | None,
    silences: list[dict[str, Any]] | None,
    video_duration: float | None,
    provider_name: str = "heuristic",
    provider_model: str = "deterministic-v1",
    top_n: int = 12,
) -> dict[str, Any]:
    """Build a canonical clip-ranking artifact from deterministic heuristics."""
    candidates = build_candidate_windows(
        transcript_segments=transcript_segments,
        scenes=scenes,
        video_duration=video_duration,
    )
    ranked: list[dict[str, Any]] = []

    for candidate in candidates:
        excerpt = collect_transcript_excerpt(candidate, transcript_segments)
        silence_ratio = compute_silence_ratio(candidate, silences or [])
        duration_sec = max(candidate.end_sec - candidate.start_sec, 0.001)
        words = len(excerpt.split())
        transcript_density = min(words / max(duration_sec * 1.8, 1.0), 1.0)
        duration_preference = max(0.0, 1.0 - abs(duration_sec - 8.0) / 8.0)
        scene_bonus = 1.0 if "scenes" in candidate.source_signals else 0.0
        score = min(
            1.0,
            max(
                0.0,
                0.45 * transcript_density
                + 0.30 * (1.0 - silence_ratio)
                + 0.20 * duration_preference
                + 0.05 * scene_bonus,
            ),
        )

        source_signals = list(candidate.source_signals)
        if excerpt:
            source_signals.append("transcript")
        if silence_ratio > 0:
            source_signals.append("silences")

        ranked.append(
            {
                "id": candidate.id,
                "startSec": candidate.start_sec,
                "endSec": candidate.end_sec,
                "score": round(score, 3),
                "sourceSignals": dedupe(source_signals),
                "transcriptExcerpt": excerpt,
                "rationale": build_rationale(
                    transcript_density=transcript_density,
                    silence_ratio=silence_ratio,
                    duration_sec=duration_sec,
                ),
                "provider": {
                    "name": provider_name,
                    "model": provider_model,
                },
            }
        )

    if top_n > 0:
        ranked = sorted(ranked, key=lambda item: item["score"], reverse=True)[:top_n]

    return normalize_clip_ranking(
        {
            "provider": {"name": provider_name, "model": provider_model},
            "candidates": ranked,
            "summary": {"status": "ready"},
        }
    )


def collect_transcript_excerpt(
    candidate: CandidateWindow,
    transcript_segments: list[dict[str, Any]],
    *,
    max_chars: int = 240,
) -> str:
    """Collect a concise transcript excerpt overlapping a candidate."""
    parts: list[str] = []
    for segment in transcript_segments:
        start_sec = float(segment.get("start", 0.0))
        end_sec = float(segment.get("end", start_sec))
        if end_sec <= candidate.start_sec or start_sec >= candidate.end_sec:
            continue
        text = str(segment.get("text", "")).strip()
        if text:
            parts.append(text)
        if len(" ".join(parts)) >= max_chars:
            break
    excerpt = " ".join(parts).strip()
    return excerpt[: max_chars - 1] + "…" if len(excerpt) > max_chars else excerpt


def compute_silence_ratio(
    candidate: CandidateWindow,
    silences: list[dict[str, Any]],
) -> float:
    """Return overlap ratio between candidate duration and detected silences."""
    duration_sec = max(candidate.end_sec - candidate.start_sec, 0.001)
    overlap_total = 0.0
    for silence in silences:
        start_sec = float(silence.get("startSec", 0.0))
        end_sec = float(silence.get("endSec", start_sec))
        overlap_total += overlap_duration(
            candidate.start_sec,
            candidate.end_sec,
            start_sec,
            end_sec,
        )
    return min(overlap_total / duration_sec, 1.0)


def overlap_duration(
    start_a: float,
    end_a: float,
    start_b: float,
    end_b: float,
) -> float:
    """Calculate overlap duration between two windows."""
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def build_rationale(
    *,
    transcript_density: float,
    silence_ratio: float,
    duration_sec: float,
) -> str:
    """Build a human-readable ranking rationale."""
    parts = [f"duration {duration_sec:.1f}s"]
    if transcript_density >= 0.7:
        parts.append("high speech density")
    elif transcript_density >= 0.35:
        parts.append("moderate speech density")
    else:
        parts.append("low speech density")

    if silence_ratio <= 0.1:
        parts.append("little silence")
    elif silence_ratio <= 0.35:
        parts.append("some silence overlap")
    else:
        parts.append("heavy silence overlap")

    return ", ".join(parts)


def dedupe(values: list[str]) -> list[str]:
    """Preserve order while removing duplicate strings."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
