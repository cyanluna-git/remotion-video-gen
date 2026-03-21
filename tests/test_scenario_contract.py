import unittest

from scripts.scenario_contract import ScenarioContractError, normalize_scenario


class ScenarioContractTest(unittest.TestCase):
    def test_normalizes_legacy_flat_section_shape(self) -> None:
        normalized = normalize_scenario(
            {
                "title": "Legacy Scenario",
                "sections": [
                    {
                        "title": "Intro",
                        "description": "Show the intro.",
                        "startSec": 1,
                        "endSec": 12,
                    }
                ],
            }
        )

        self.assertEqual(normalized["language"], "auto")
        self.assertEqual(
            normalized["sections"][0]["timeRange"],
            {"startSec": 1.0, "endSec": 12.0},
        )
        self.assertNotIn("startSec", normalized["sections"][0])
        self.assertNotIn("endSec", normalized["sections"][0])
        self.assertTrue(normalized["options"]["correctCaptions"])

    def test_preserves_canonical_shape_and_defaults(self) -> None:
        normalized = normalize_scenario(
            {
                "title": "Canonical Scenario",
                "language": "ko",
                "sections": [
                    {
                        "title": "Intro",
                        "description": "Show the intro.",
                        "timeRange": {"startSec": 0, "endSec": 8},
                    }
                ],
                "options": {"autoCaption": False},
            }
        )

        self.assertEqual(normalized["language"], "ko")
        self.assertEqual(
            normalized["sections"][0]["timeRange"],
            {"startSec": 0.0, "endSec": 8.0},
        )
        self.assertFalse(normalized["options"]["autoCaption"])
        self.assertTrue(normalized["options"]["correctCaptions"])

    def test_rejects_invalid_ranges(self) -> None:
        with self.assertRaises(ScenarioContractError):
            normalize_scenario(
                {
                    "title": "Broken Scenario",
                    "sections": [
                        {
                            "title": "Intro",
                            "description": "Show the intro.",
                            "timeRange": {"startSec": 12, "endSec": 1},
                        }
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
