import unittest
from pathlib import Path

from scripts.multimodal_contracts import (
    MultimodalContractError,
    job_artifact_paths,
    normalize_clip_ranking,
    normalize_qa_artifact,
    normalize_voiceover_manifest,
)


class MultimodalContractsTest(unittest.TestCase):
    def test_job_artifact_paths_are_job_scoped(self) -> None:
        paths = job_artifact_paths(Path("/tmp/jobs/job-123"))

        self.assertEqual(paths["voiceover_manifest"], Path("/tmp/jobs/job-123/voiceover/manifest.json"))
        self.assertEqual(paths["clip_ranking"], Path("/tmp/jobs/job-123/analysis/clip-ranking.json"))
        self.assertEqual(paths["qa_output"], Path("/tmp/jobs/job-123/output/qa.json"))
        self.assertEqual(paths["qa_heuristic"], Path("/tmp/jobs/job-123/output/qa.heuristic.json"))
        self.assertEqual(paths["qa_vision"], Path("/tmp/jobs/job-123/output/qa.vision.json"))

    def test_normalize_voiceover_manifest_applies_defaults(self) -> None:
        manifest = normalize_voiceover_manifest(
            {
                "provider": {"name": "mock-tts", "model": "demo-v1"},
                "tracks": [
                    {
                        "src": "voiceover/intro.wav",
                        "startSec": 0,
                        "durationSec": 3.25,
                        "text": "Intro narration",
                    }
                ],
            }
        )

        self.assertEqual(manifest["artifact"], "voiceover-manifest")
        self.assertEqual(manifest["provider"]["name"], "mock-tts")
        self.assertEqual(manifest["tracks"][0]["id"], "track-1")
        self.assertEqual(manifest["tracks"][0]["src"], "voiceover/intro.wav")
        self.assertEqual(manifest["summary"]["trackCount"], 1)
        self.assertEqual(manifest["summary"]["status"], "ready")

    def test_rejects_absolute_voiceover_paths(self) -> None:
        with self.assertRaises(MultimodalContractError):
            normalize_voiceover_manifest(
                {
                    "tracks": [
                        {
                            "src": "/tmp/intro.wav",
                            "startSec": 0,
                            "durationSec": 1,
                        }
                    ]
                }
            )

    def test_normalize_clip_ranking_sorts_and_ranks_candidates(self) -> None:
        ranking = normalize_clip_ranking(
            {
                "candidates": [
                    {
                        "id": "second",
                        "startSec": 4,
                        "endSec": 8,
                        "score": 0.5,
                        "sourceSignals": ["transcript"],
                    },
                    {
                        "id": "first",
                        "startSec": 0,
                        "endSec": 4,
                        "score": 0.9,
                        "sourceSignals": ["transcript", "scenes"],
                    },
                ]
            }
        )

        self.assertEqual(ranking["artifact"], "clip-ranking")
        self.assertEqual(ranking["candidates"][0]["id"], "first")
        self.assertEqual(ranking["candidates"][0]["rank"], 1)
        self.assertEqual(ranking["candidates"][1]["rank"], 2)
        self.assertEqual(ranking["summary"]["topCandidateIds"], ["first", "second"])

    def test_normalize_qa_artifact_wraps_heuristic_and_merges_vision(self) -> None:
        qa = normalize_qa_artifact(
            {
                "version": "1.0",
                "generatedAt": "2026-03-21T00:00:00.000000Z",
                "method": "heuristic",
                "thumbnail": {"path": "output/thumbnail.jpg"},
                "checks": {},
                "summary": {"status": "warn", "warningCount": 1, "failCount": 0},
                "autoRerender": False,
            },
            {
                "summary": {"status": "fail", "warningCount": 2, "failCount": 1},
                "findings": [],
            },
        )

        self.assertEqual(qa["artifact"], "qa-review")
        self.assertIn("heuristic", qa["reviews"])
        self.assertIn("vision", qa["reviews"])
        self.assertEqual(qa["summary"]["status"], "fail")
        self.assertEqual(qa["summary"]["warningCount"], 3)
        self.assertEqual(qa["summary"]["failCount"], 1)


if __name__ == "__main__":
    unittest.main()
