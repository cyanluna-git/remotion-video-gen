"""Optional vision-review providers for post-render QA."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class VisionReviewError(RuntimeError):
    """Raised when a vision review provider fails."""


@dataclass(frozen=True)
class VisionReviewRequest:
    """Inputs required for a second-pass vision QA review."""

    frame_samples: list[dict[str, Any]]
    heuristic_review: dict[str, Any]
    edit_context: dict[str, Any] | None


@dataclass(frozen=True)
class VisionReviewConfig:
    """Provider configuration for vision QA."""

    name: str
    model: str
    detail: str = "low"


class BaseVisionReviewProvider:
    """Abstract provider interface."""

    def __init__(self, config: VisionReviewConfig) -> None:
        self.config = config

    def review(self, request: VisionReviewRequest) -> dict[str, Any]:
        raise NotImplementedError


class MockVisionReviewProvider(BaseVisionReviewProvider):
    """Deterministic provider for tests and dry-runs."""

    def review(self, request: VisionReviewRequest) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        for sample in request.frame_samples:
            if not sample.get("extracted"):
                continue
            yavg = sample.get("yavg")
            if yavg is not None and float(yavg) < 18:
                findings.append(
                    {
                        "severity": "warn",
                        "category": "blank-frame",
                        "message": "Frame appears unusually dark for a representative render sample.",
                        "timeSec": sample.get("timeSec"),
                        "framePath": sample.get("path"),
                    }
                )

        if not findings and request.heuristic_review.get("summary", {}).get("status") == "warn":
            findings.append(
                {
                    "severity": "warn",
                    "category": "consistency",
                    "message": "Heuristic QA reported warnings; verify semantic quality on highlighted frames.",
                }
            )

        return normalize_vision_review(
            {
                "summary": {
                    "status": "warn" if findings else "pass",
                    "warningCount": len([item for item in findings if item["severity"] == "warn"]),
                    "failCount": len([item for item in findings if item["severity"] == "fail"]),
                },
                "findings": findings,
            },
            provider={
                "name": self.config.name,
                "model": self.config.model,
                "detail": self.config.detail,
            },
            frame_samples=request.frame_samples,
        )


class OpenAIVisionReviewProvider(BaseVisionReviewProvider):
    """OpenAI Responses API provider for image-based QA."""

    def review(self, request: VisionReviewRequest) -> dict[str, Any]:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise VisionReviewError("OPENAI_API_KEY is required for the openai vision QA provider.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise VisionReviewError(
                "The openai package is not installed. Run `pip install -r requirements.txt`."
            ) from exc

        client = OpenAI(api_key=api_key)
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": build_vision_prompt(request),
            }
        ]

        for sample in request.frame_samples[:4]:
            frame_path = Path(str(sample.get("path", "")))
            if not sample.get("extracted") or not frame_path.exists():
                continue
            content.append(
                {
                    "type": "input_text",
                    "text": f"Frame sample at {sample.get('timeSec')}s from {frame_path.name}",
                }
            )
            content.append(
                {
                    "type": "input_image",
                    "image_url": encode_image_data_url(frame_path),
                    "detail": self.config.detail,
                }
            )

        response = client.responses.create(
            model=self.config.model,
            input=[{"role": "user", "content": content}],
        )
        raw_text = getattr(response, "output_text", "") or extract_response_text(response)
        if not raw_text.strip():
            raise VisionReviewError("Vision QA response did not contain text output.")

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise VisionReviewError("Vision QA response was not valid JSON.") from exc

        return normalize_vision_review(
            payload,
            provider={
                "name": self.config.name,
                "model": self.config.model,
                "detail": self.config.detail,
            },
            frame_samples=request.frame_samples,
        )


def build_vision_review_provider(
    provider_name: str,
    *,
    model: str,
    detail: str,
) -> BaseVisionReviewProvider:
    """Build a provider instance for the requested vision QA backend."""
    config = VisionReviewConfig(
        name=provider_name.strip().lower(),
        model=model.strip(),
        detail=detail.strip().lower() or "low",
    )
    if config.name == "mock":
        return MockVisionReviewProvider(config)
    if config.name == "openai":
        return OpenAIVisionReviewProvider(config)
    raise VisionReviewError(f"Unsupported vision QA provider: {provider_name}")


def normalize_vision_review(
    payload: dict[str, Any],
    *,
    provider: dict[str, Any],
    frame_samples: list[dict[str, Any]],
) -> dict[str, Any]:
    """Normalize vision review output to a consistent serializable shape."""
    if not isinstance(payload, dict):
        raise VisionReviewError("Vision review payload must be a JSON object.")

    raw_findings = payload.get("findings")
    findings: list[dict[str, Any]] = []
    warning_count = 0
    fail_count = 0
    if isinstance(raw_findings, list):
        for finding in raw_findings:
            if not isinstance(finding, dict):
                continue
            severity = str(finding.get("severity") or "warn")
            if severity not in {"warn", "fail"}:
                severity = "warn"
            if severity == "warn":
                warning_count += 1
            elif severity == "fail":
                fail_count += 1
            findings.append(
                {
                    "severity": severity,
                    "category": str(finding.get("category") or "general"),
                    "message": str(finding.get("message") or "").strip(),
                    "timeSec": finding.get("timeSec"),
                    "framePath": finding.get("framePath"),
                }
            )

    raw_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    status = str(raw_summary.get("status") or ("fail" if fail_count else "warn" if warning_count else "pass"))
    return {
        "version": "1.0",
        "method": "vision",
        "provider": provider,
        "summary": {
            "status": status,
            "warningCount": int(raw_summary.get("warningCount", warning_count)),
            "failCount": int(raw_summary.get("failCount", fail_count)),
        },
        "findings": findings,
        "frameSamples": frame_samples,
        "notes": str(payload.get("notes") or "").strip(),
    }


def build_vision_prompt(request: VisionReviewRequest) -> str:
    """Construct a compact JSON-only vision QA prompt."""
    heuristic_summary = request.heuristic_review.get("summary", {})
    return "\n".join(
        [
            "You are reviewing rendered video QA frames for a Remotion pipeline.",
            "Return ONLY JSON with keys: summary, findings, notes.",
            'summary.status must be one of "pass", "warn", or "fail".',
            'Each finding must include: severity ("warn" or "fail"), category, message, optional timeSec, optional framePath.',
            "Review for black frames, unreadable captions, awkward transitions, cropped UI, and mismatches between the selected thumbnail and the representative content.",
            "",
            "## Heuristic Summary",
            json.dumps(heuristic_summary, ensure_ascii=False),
            "",
            "## Frame Sample Metadata",
            json.dumps(request.frame_samples, ensure_ascii=False),
            "",
            "## Edit Context",
            json.dumps(request.edit_context or {}, ensure_ascii=False),
        ]
    )


def encode_image_data_url(path: Path) -> str:
    """Encode an image file as a data URL for OpenAI image input."""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64,{encoded}"


def extract_response_text(response: Any) -> str:
    """Best-effort extraction for SDK response text."""
    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return ""
    texts: list[str] = []
    for item in output:
        contents = getattr(item, "content", None)
        if not isinstance(contents, list):
            continue
        for content in contents:
            text = getattr(content, "text", None)
            if isinstance(text, str):
                texts.append(text)
    return "\n".join(texts).strip()
