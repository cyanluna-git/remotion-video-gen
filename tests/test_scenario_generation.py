import unittest

from scripts.scenario_contract import ScenarioContractError
from scripts.scenario_generation import (
    build_scenario_prompt,
    derive_language,
    derive_title,
    summarize_clip_ranking,
    validate_generated_scenario,
)


class ScenarioGenerationTest(unittest.TestCase):
    def test_derives_title_from_source_name(self) -> None:
        self.assertEqual(
            derive_title(None, "edge_frontend-demo.mp4"),
            "edge frontend demo",
        )

    def test_prefers_explicit_title_hint(self) -> None:
        self.assertEqual(
            derive_title("Custom Title", "edge_frontend-demo.mp4"),
            "Custom Title",
        )

    def test_derives_language_from_transcript_metadata(self) -> None:
        transcript = {"language": "ko", "segments": []}
        self.assertEqual(derive_language(None, transcript), "ko")

    def test_defaults_language_to_auto_without_signal(self) -> None:
        self.assertEqual(derive_language(None, None), "auto")

    def test_rejects_overlapping_generated_sections(self) -> None:
        with self.assertRaises(ScenarioContractError):
            validate_generated_scenario(
                {
                    "title": "Auto Scenario",
                    "language": "en",
                    "sections": [
                        {
                            "title": "Intro",
                            "description": "First part",
                            "timeRange": {"startSec": 0, "endSec": 10},
                        },
                        {
                            "title": "Overlap",
                            "description": "Second part",
                            "timeRange": {"startSec": 9, "endSec": 12},
                        },
                    ],
                }
            )

    def test_rejects_sections_beyond_duration(self) -> None:
        with self.assertRaises(ScenarioContractError):
            validate_generated_scenario(
                {
                    "title": "Auto Scenario",
                    "language": "en",
                    "sections": [
                        {
                            "title": "Only",
                            "description": "All footage",
                            "timeRange": {"startSec": 0, "endSec": 12},
                        }
                    ],
                },
                video_duration=10.0,
            )

    def test_accepts_canonical_generated_scenario(self) -> None:
        scenario = validate_generated_scenario(
            {
                "title": "Auto Scenario",
                "sections": [
                    {
                        "title": "Only",
                        "description": "All footage",
                        "timeRange": {"startSec": 0, "endSec": 10},
                    }
                ],
            },
            video_duration=10.0,
        )
        self.assertEqual(scenario["language"], "auto")
        self.assertTrue(scenario["options"]["correctCaptions"])

    def test_summarizes_clip_ranking_for_prompt_context(self) -> None:
        summary = summarize_clip_ranking(
            {
                "candidates": [
                    {
                        "id": "scene-01",
                        "rank": 1,
                        "startSec": 0,
                        "endSec": 6,
                        "score": 0.91,
                        "sourceSignals": ["scenes", "transcript"],
                        "transcriptExcerpt": "Open the dashboard and explain the top metrics.",
                        "rationale": "duration 6.0s, high speech density, little silence",
                    }
                ]
            }
        )

        self.assertEqual(summary[0]["id"], "scene-01")
        self.assertEqual(summary[0]["rank"], 1)
        self.assertIn("transcriptExcerpt", summary[0])

    def test_scenario_prompt_includes_clip_ranking_hints(self) -> None:
        prompt = build_scenario_prompt(
            title_hint="Demo",
            language_hint="en",
            transcript_segments=[],
            scenes=None,
            silences=None,
            clip_ranking={
                "candidates": [
                    {
                        "id": "scene-01",
                        "rank": 1,
                        "startSec": 0,
                        "endSec": 6,
                        "score": 0.91,
                        "sourceSignals": ["scenes", "transcript"],
                    }
                ]
            },
            video_duration=12.0,
        )

        self.assertIn("Clip Ranking Hints", prompt)
        self.assertIn("scene-01", prompt)


if __name__ == "__main__":
    unittest.main()
