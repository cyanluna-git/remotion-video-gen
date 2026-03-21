import unittest

from scripts.scenario_contract import ScenarioContractError
from scripts.scenario_generation import (
    derive_language,
    derive_title,
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


if __name__ == "__main__":
    unittest.main()
