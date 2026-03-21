import unittest

from scripts.clip_ranking import build_candidate_windows, build_clip_ranking_artifact
from scripts.generate_edit import build_prompt


class ClipRankingTest(unittest.TestCase):
    def test_builds_scene_candidates_when_scenes_exist(self) -> None:
        candidates = build_candidate_windows(
            transcript_segments=[],
            scenes=[
                {"startSec": 0, "endSec": 4},
                {"startSec": 4, "endSec": 10},
            ],
            video_duration=10.0,
        )

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].id, "scene-01")
        self.assertEqual(candidates[1].source_signals, ["scenes"])

    def test_generates_ranked_artifact_from_analysis_inputs(self) -> None:
        artifact = build_clip_ranking_artifact(
            transcript_segments=[
                {"start": 0, "end": 2, "text": "Open settings and explain the environment."},
                {"start": 2.2, "end": 5, "text": "Show the upload flow and the preview panel."},
            ],
            scenes=[
                {"startSec": 0, "endSec": 5},
                {"startSec": 5, "endSec": 12},
            ],
            silences=[{"startSec": 5.5, "endSec": 7.5, "durationSec": 2.0}],
            video_duration=12.0,
        )

        self.assertEqual(artifact["artifact"], "clip-ranking")
        self.assertEqual(artifact["provider"]["name"], "heuristic")
        self.assertGreaterEqual(artifact["summary"]["candidateCount"], 2)
        self.assertEqual(artifact["candidates"][0]["rank"], 1)
        self.assertIn("sourceSignals", artifact["candidates"][0])

    def test_edit_prompt_includes_clip_ranking_hints(self) -> None:
        prompt = build_prompt(
            scenario={
                "title": "Demo",
                "language": "en",
                "sections": [
                    {
                        "title": "Intro",
                        "description": "Explain the intro",
                        "timeRange": {"startSec": 0, "endSec": 8},
                    }
                ],
                "style": {},
                "options": {},
            },
            transcript_segments=[],
            scenes=None,
            silences=None,
            clip_ranking={
                "candidates": [
                    {
                        "id": "scene-01",
                        "rank": 1,
                        "startSec": 0,
                        "endSec": 5,
                        "score": 0.9,
                        "sourceSignals": ["scenes", "transcript"],
                    }
                ]
            },
            voiceover_manifest=None,
            video_duration=8.0,
        )

        self.assertIn("Clip Ranking Hints", prompt)
        self.assertIn("scene-01", prompt)


if __name__ == "__main__":
    unittest.main()
