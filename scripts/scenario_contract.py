"""Scenario contract normalization and validation helpers.

This module defines the canonical scenario shape used across docs, frontend,
backend, and AI generation. It also provides migration support for legacy
payloads that still send flat section timing fields.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_STYLE = {
    "titleCardBackground": "linear-gradient(135deg, #c8102e, #1e1b4b)",
    "captionPosition": "bottom",
    "transition": "fade",
    "transitionDuration": 0.5,
}

DEFAULT_OPTIONS = {
    "removeSilence": True,
    "silenceThreshold": 3.0,
    "autoCaption": True,
    "correctCaptions": True,
}


class ScenarioContractError(ValueError):
    """Raised when a scenario payload cannot be normalized safely."""


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScenarioContractError(f"{field_name} must be an object.")
    return value


def _coerce_number(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ScenarioContractError(f"{field_name} must be a number.") from exc


def _normalize_time_range(section: dict[str, Any], index: int) -> dict[str, float]:
    time_range = section.get("timeRange")
    if time_range is None:
        if "startSec" not in section or "endSec" not in section:
            raise ScenarioContractError(
                f"sections[{index}] must include timeRange or legacy startSec/endSec."
            )
        start_sec = _coerce_number(section.get("startSec"), f"sections[{index}].startSec")
        end_sec = _coerce_number(section.get("endSec"), f"sections[{index}].endSec")
    else:
        time_range = _require_mapping(time_range, f"sections[{index}].timeRange")
        start_sec = _coerce_number(
            time_range.get("startSec"), f"sections[{index}].timeRange.startSec"
        )
        end_sec = _coerce_number(
            time_range.get("endSec"), f"sections[{index}].timeRange.endSec"
        )

    if end_sec < start_sec:
        raise ScenarioContractError(
            f"sections[{index}] has endSec earlier than startSec."
        )

    return {
        "startSec": start_sec,
        "endSec": end_sec,
    }


def _normalize_emphasis(items: Any, section_index: int) -> list[dict[str, Any]]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise ScenarioContractError(f"sections[{section_index}].emphasis must be a list.")

    normalized: list[dict[str, Any]] = []
    for item_index, item in enumerate(items):
        emphasis = _require_mapping(
            item, f"sections[{section_index}].emphasis[{item_index}]"
        )
        time_sec = _coerce_number(
            emphasis.get("timeSec"),
            f"sections[{section_index}].emphasis[{item_index}].timeSec",
        )
        emphasis_type = emphasis.get("type")
        if emphasis_type not in {"caption", "highlight"}:
            raise ScenarioContractError(
                f"sections[{section_index}].emphasis[{item_index}].type must be caption or highlight."
            )

        normalized_item: dict[str, Any] = {
            "timeSec": time_sec,
            "type": emphasis_type,
        }
        if emphasis_type == "caption":
            text = str(emphasis.get("text", "")).strip()
            if not text:
                raise ScenarioContractError(
                    f"sections[{section_index}].emphasis[{item_index}].text is required for caption."
                )
            normalized_item["text"] = text
        else:
            region = _require_mapping(
                emphasis.get("region"),
                f"sections[{section_index}].emphasis[{item_index}].region",
            )
            normalized_item["region"] = {
                "x": _coerce_number(
                    region.get("x"),
                    f"sections[{section_index}].emphasis[{item_index}].region.x",
                ),
                "y": _coerce_number(
                    region.get("y"),
                    f"sections[{section_index}].emphasis[{item_index}].region.y",
                ),
                "width": _coerce_number(
                    region.get("width"),
                    f"sections[{section_index}].emphasis[{item_index}].region.width",
                ),
                "height": _coerce_number(
                    region.get("height"),
                    f"sections[{section_index}].emphasis[{item_index}].region.height",
                ),
            }

        normalized.append(normalized_item)

    return normalized


def normalize_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert a scenario payload to the canonical schema.

    New writes should always emit the canonical shape:
    - top-level `language`
    - nested `sections[].timeRange`
    - `options.correctCaptions`

    Legacy flat section timing fields are accepted during migration and
    normalized on output.
    """

    scenario = _require_mapping(deepcopy(payload), "scenario")

    title = str(scenario.get("title", scenario.get("name", ""))).strip()
    if not title:
        raise ScenarioContractError("title is required.")

    language = str(scenario.get("language", "auto")).strip() or "auto"

    raw_sections = scenario.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ScenarioContractError("sections must be a non-empty list.")

    normalized_sections: list[dict[str, Any]] = []
    for index, raw_section in enumerate(raw_sections):
        section = _require_mapping(raw_section, f"sections[{index}]")
        section_title = str(section.get("title", "")).strip()
        section_description = str(section.get("description", "")).strip()
        if not section_title:
            raise ScenarioContractError(f"sections[{index}].title is required.")
        if not section_description:
            raise ScenarioContractError(f"sections[{index}].description is required.")

        normalized_section: dict[str, Any] = {
            "title": section_title,
            "description": section_description,
            "timeRange": _normalize_time_range(section, index),
        }
        emphasis = _normalize_emphasis(section.get("emphasis"), index)
        if emphasis:
            normalized_section["emphasis"] = emphasis
        normalized_sections.append(normalized_section)

    style = deepcopy(DEFAULT_STYLE)
    raw_style = scenario.get("style")
    if raw_style is not None:
        style.update(_require_mapping(raw_style, "style"))

    options = deepcopy(DEFAULT_OPTIONS)
    raw_options = scenario.get("options")
    if raw_options is not None:
        options.update(_require_mapping(raw_options, "options"))

    normalized: dict[str, Any] = {
        "title": title,
        "language": language,
        "sections": normalized_sections,
        "style": style,
        "options": options,
    }

    for field in ("subtitle", "author"):
        value = scenario.get(field)
        if isinstance(value, str) and value.strip():
            normalized[field] = value.strip()

    return normalized
