import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MAIN = PROJECT_ROOT / "web" / "backend" / "main.py"


def load_backend_module():
    spec = importlib.util.spec_from_file_location("backend_main_test", BACKEND_MAIN)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class BackendApiE2ETest(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = load_backend_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.jobs_dir = Path(self.temp_dir.name) / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.backend.JOBS_DIR = self.jobs_dir

        self._original_run_pipeline = self.backend.run_pipeline
        self.backend.run_pipeline = AsyncMock(return_value=None)
        self.client = TestClient(self.backend.app)

    def tearDown(self) -> None:
        self.backend.run_pipeline = self._original_run_pipeline
        self.temp_dir.cleanup()

    def test_manual_submission_normalizes_legacy_payload(self) -> None:
        response = self.client.post(
            "/api/jobs",
            files={"video": ("demo.mp4", b"fake-video", "video/mp4")},
            data={
                "scenario": json.dumps(
                    {
                        "title": "Legacy Manual",
                        "sections": [
                            {
                                "title": "Intro",
                                "description": "Manual flow",
                                "startSec": 1,
                                "endSec": 6,
                            }
                        ],
                    }
                )
            },
        )

        self.assertEqual(response.status_code, 201)
        job_id = response.json()["id"]

        scenario_path = self.jobs_dir / job_id / "scenario.json"
        self.assertTrue(scenario_path.exists())
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        self.assertEqual(
            scenario["sections"][0]["timeRange"],
            {"startSec": 1.0, "endSec": 6.0},
        )

        summary_response = self.client.get("/api/jobs")
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.json()[0]["inputMode"], "manual")
        self.backend.run_pipeline.assert_awaited_once()

    def test_zero_input_submission_accepts_video_only(self) -> None:
        response = self.client.post(
            "/api/jobs",
            files={"video": ("screen-capture.mp4", b"fake-video", "video/mp4")},
            data={"autoScenario": "true", "language": "ko"},
        )

        self.assertEqual(response.status_code, 201)
        job_id = response.json()["id"]
        meta = self.backend.load_meta(self.jobs_dir / job_id / "meta.json")

        self.assertEqual(meta["inputMode"], "auto")
        self.assertEqual(meta["languageHint"], "ko")
        self.assertEqual(meta["title"], "screen capture")
        self.assertFalse((self.jobs_dir / job_id / "scenario.json").exists())
        self.backend.run_pipeline.assert_awaited_once()

    def test_artifact_retrieval_surfaces_edit_thumbnail_video_and_qa(self) -> None:
        response = self.client.post(
            "/api/jobs",
            files={"video": ("demo.mp4", b"fake-video", "video/mp4")},
            data={
                "scenario": json.dumps(
                    {
                        "title": "Artifact Job",
                        "sections": [
                            {
                                "title": "Only",
                                "description": "Artifact path",
                                "timeRange": {"startSec": 0, "endSec": 5},
                            }
                        ],
                    }
                )
            },
        )
        job_id = response.json()["id"]
        job_dir = self.jobs_dir / job_id
        output_dir = job_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        (output_dir / "final.mp4").write_bytes(b"video")
        (output_dir / "thumbnail.jpg").write_bytes(b"thumb")
        (job_dir / "edit.json").write_text(
            json.dumps({"version": "1.0", "fps": 30, "resolution": {"width": 1, "height": 1}, "sources": {}, "timeline": []}),
            encoding="utf-8",
        )
        (output_dir / "qa.json").write_text(
            json.dumps({"summary": {"status": "warn", "warningCount": 2, "failCount": 0}}),
            encoding="utf-8",
        )

        meta = self.backend.load_meta(job_dir / "meta.json")
        meta["status"] = "done"
        self.backend.save_meta(job_dir / "meta.json", meta)

        detail = self.client.get(f"/api/jobs/{job_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertTrue(payload["hasVideo"])
        self.assertTrue(payload["hasThumbnail"])
        self.assertTrue(payload["hasEdit"])
        self.assertTrue(payload["hasQa"])
        self.assertEqual(payload["qaStatus"], "warn")
        self.assertEqual(payload["qaWarningCount"], 2)

        self.assertEqual(self.client.get(f"/api/jobs/{job_id}/video").status_code, 200)
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}/thumbnail").status_code, 200)
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}/edit").status_code, 200)
        self.backend.run_pipeline.assert_awaited_once()

    def test_artifact_retrieval_surfaces_tts_manifest_summary(self) -> None:
        response = self.client.post(
            "/api/jobs",
            files={"video": ("demo.mp4", b"fake-video", "video/mp4")},
            data={
                "scenario": json.dumps(
                    {
                        "title": "TTS Job",
                        "sections": [
                            {
                                "title": "Intro",
                                "description": "Narrate intro",
                                "timeRange": {"startSec": 0, "endSec": 5},
                            }
                        ],
                    }
                )
            },
        )
        job_id = response.json()["id"]
        job_dir = self.jobs_dir / job_id
        voiceover_dir = job_dir / "voiceover"
        voiceover_dir.mkdir(parents=True, exist_ok=True)
        (voiceover_dir / "section-01-intro.wav").write_bytes(b"RIFFdemo")
        (voiceover_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "artifact": "voiceover-manifest",
                    "provider": {"name": "mock", "model": "demo-v1", "voice": "alloy"},
                    "tracks": [
                        {
                            "id": "section-01-intro",
                            "src": "voiceover/section-01-intro.wav",
                            "startSec": 0,
                            "durationSec": 1.5,
                            "text": "Intro. Narrate intro",
                        }
                    ],
                    "summary": {"status": "ready", "trackCount": 1},
                }
            ),
            encoding="utf-8",
        )

        detail = self.client.get(f"/api/jobs/{job_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertTrue(payload["hasVoiceoverArtifacts"])
        self.assertEqual(payload["ttsStatus"], "ready")
        self.assertEqual(payload["ttsTrackCount"], 1)
        self.assertEqual(payload["ttsProvider"], "mock")
        self.assertEqual(payload["ttsModel"], "demo-v1")
        self.assertEqual(payload["ttsVoice"], "alloy")

    def test_artifact_retrieval_surfaces_qa_review_methods(self) -> None:
        response = self.client.post(
            "/api/jobs",
            files={"video": ("demo.mp4", b"fake-video", "video/mp4")},
            data={
                "scenario": json.dumps(
                    {
                        "title": "QA Job",
                        "sections": [
                            {
                                "title": "Intro",
                                "description": "Review QA",
                                "timeRange": {"startSec": 0, "endSec": 5},
                            }
                        ],
                    }
                )
            },
        )
        job_id = response.json()["id"]
        job_dir = self.jobs_dir / job_id
        output_dir = job_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "qa.json").write_text(
            json.dumps(
                {
                    "summary": {"status": "warn", "warningCount": 1, "failCount": 0},
                    "reviews": {
                        "heuristic": {"summary": {"status": "pass", "warningCount": 0, "failCount": 0}},
                        "vision": {"summary": {"status": "warn", "warningCount": 1, "failCount": 0}},
                    },
                }
            ),
            encoding="utf-8",
        )

        detail = self.client.get(f"/api/jobs/{job_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertTrue(payload["hasQa"])
        self.assertTrue(payload["hasVisionQa"])
        self.assertEqual(payload["qaReviewMethods"], ["heuristic", "vision"])

    def test_artifact_retrieval_surfaces_clip_ranking_summary(self) -> None:
        response = self.client.post(
            "/api/jobs",
            files={"video": ("demo.mp4", b"fake-video", "video/mp4")},
            data={
                "scenario": json.dumps(
                    {
                        "title": "Ranking Job",
                        "sections": [
                            {
                                "title": "Intro",
                                "description": "Review ranking",
                                "timeRange": {"startSec": 0, "endSec": 5},
                            }
                        ],
                    }
                )
            },
        )
        job_id = response.json()["id"]
        analysis_dir = self.jobs_dir / job_id / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "clip-ranking.json").write_text(
            json.dumps(
                {
                    "summary": {
                        "status": "ready",
                        "candidateCount": 2,
                        "topCandidateIds": ["scene-01", "scene-02"],
                    },
                    "candidates": [
                        {
                            "id": "scene-01",
                            "rank": 1,
                            "startSec": 0,
                            "endSec": 4,
                            "score": 0.8,
                            "sourceSignals": ["scenes"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        detail = self.client.get(f"/api/jobs/{job_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertTrue(payload["hasClipRanking"])
        self.assertEqual(payload["clipRankingCandidateCount"], 2)
        self.assertEqual(payload["clipRankingTopCandidateIds"], ["scene-01", "scene-02"])
        self.assertIn("clipRanking", payload)

        summary = self.client.get("/api/jobs").json()[0]
        self.assertTrue(summary["hasClipRanking"])
        self.assertEqual(summary["clipRankingCandidateCount"], 2)

    def test_multimodal_detail_surfaces_combined_artifacts(self) -> None:
        response = self.client.post(
            "/api/jobs",
            files={"video": ("demo.mp4", b"fake-video", "video/mp4")},
            data={
                "scenario": json.dumps(
                    {
                        "title": "Multimodal Job",
                        "sections": [
                            {
                                "title": "Intro",
                                "description": "Review all artifacts",
                                "timeRange": {"startSec": 0, "endSec": 5},
                            }
                        ],
                    }
                )
            },
        )
        job_id = response.json()["id"]
        job_dir = self.jobs_dir / job_id
        output_dir = job_dir / "output"
        voiceover_dir = job_dir / "voiceover"
        analysis_dir = job_dir / "analysis"
        output_dir.mkdir(parents=True, exist_ok=True)
        voiceover_dir.mkdir(parents=True, exist_ok=True)
        analysis_dir.mkdir(parents=True, exist_ok=True)

        (voiceover_dir / "track.wav").write_bytes(b"RIFFdemo")
        (voiceover_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "provider": {"name": "mock", "model": "demo-v1", "voice": "alloy"},
                    "tracks": [{"src": "voiceover/track.wav", "startSec": 0, "durationSec": 1.2}],
                    "summary": {"status": "ready", "trackCount": 1},
                }
            ),
            encoding="utf-8",
        )
        (analysis_dir / "clip-ranking.json").write_text(
            json.dumps(
                {
                    "summary": {"candidateCount": 2, "topCandidateIds": ["scene-01", "scene-02"]},
                    "candidates": [{"id": "scene-01", "rank": 1, "startSec": 0, "endSec": 4, "score": 0.8, "sourceSignals": ["scenes"]}],
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "qa.json").write_text(
            json.dumps(
                {
                    "summary": {"status": "warn", "warningCount": 1, "failCount": 0},
                    "reviews": {
                        "heuristic": {"summary": {"status": "pass", "warningCount": 0, "failCount": 0}},
                        "vision": {"summary": {"status": "warn", "warningCount": 1, "failCount": 0}},
                    },
                }
            ),
            encoding="utf-8",
        )

        detail = self.client.get(f"/api/jobs/{job_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertEqual(payload["ttsStatus"], "ready")
        self.assertEqual(payload["clipRankingCandidateCount"], 2)
        self.assertTrue(payload["hasVisionQa"])
        self.assertEqual(payload["qaReviewMethods"], ["heuristic", "vision"])
        self.assertIn("voiceoverManifest", payload)
        self.assertIn("clipRanking", payload)

    def test_optional_stage_failures_do_not_break_baseline_detail(self) -> None:
        response = self.client.post(
            "/api/jobs",
            files={"video": ("demo.mp4", b"fake-video", "video/mp4")},
            data={
                "scenario": json.dumps(
                    {
                        "title": "Failure Tolerant Job",
                        "sections": [
                            {
                                "title": "Only",
                                "description": "Baseline still works",
                                "timeRange": {"startSec": 0, "endSec": 5},
                            }
                        ],
                    }
                )
            },
        )
        job_id = response.json()["id"]
        job_dir = self.jobs_dir / job_id
        voiceover_dir = job_dir / "voiceover"
        voiceover_dir.mkdir(parents=True, exist_ok=True)
        (voiceover_dir / "error.json").write_text(
            json.dumps({"status": "failed", "message": "Missing provider credentials"}),
            encoding="utf-8",
        )

        detail = self.client.get(f"/api/jobs/{job_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertEqual(payload["ttsStatus"], "failed")
        self.assertEqual(payload["ttsError"], "Missing provider credentials")
        self.assertFalse(payload["hasClipRanking"])
        self.assertFalse(payload.get("hasVisionQa", False))


class PipelineFlowE2ETest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.backend = load_backend_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.jobs_dir = Path(self.temp_dir.name) / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.backend.JOBS_DIR = self.jobs_dir

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_auto_pipeline_success_records_done_status_and_qa(self) -> None:
        job_id = "auto-job"
        job_dir = self.jobs_dir / job_id
        output_dir = job_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "input.mp4").write_bytes(b"video")

        self.backend.save_meta(
            job_dir / "meta.json",
            {
                "id": job_id,
                "title": "Auto Job",
                "inputMode": "auto",
                "titleHint": "Auto Job",
                "languageHint": "ko",
                "status": "queued",
                "currentStep": 0,
                "createdAt": self.backend.utcnow_iso(),
                "startedAt": None,
                "completedAt": None,
                "fileSize": 0,
                "duration": None,
                "log": "",
            },
        )
        (output_dir / "final.mp4").write_bytes(b"video")
        (job_dir / "edit.json").write_text(
            json.dumps({"version": "1.0", "fps": 30, "resolution": {"width": 1, "height": 1}, "sources": {}, "timeline": []}),
            encoding="utf-8",
        )

        captured = {}

        class FakeStdout:
            def __init__(self, lines):
                self._lines = iter(lines)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._lines)
                except StopIteration as exc:
                    raise StopAsyncIteration from exc

        class FakeProcess:
            def __init__(self, returncode, lines):
                self.returncode = returncode
                self.stdout = FakeStdout(lines)

            async def wait(self):
                return self.returncode

        async def fake_subprocess_exec(*cmd, **kwargs):
            captured["cmd"] = cmd
            return FakeProcess(
                0,
                [
                    b"Step 1: Preprocessing\n",
                    b"Step 3: AI Edit Script Generation\n",
                    b"Step 5: Audio Post-Processing\n",
                ],
            )

        original_exec = self.backend.asyncio.create_subprocess_exec
        original_run = self.backend.subprocess.run

        def fake_run(cmd, capture_output=False, text=False):
            if "post_render_review.py" in str(cmd):
                qa_path = output_dir / "qa.json"
                thumb_path = output_dir / "thumbnail.jpg"
                qa_path.write_text(
                    json.dumps({"summary": {"status": "pass", "warningCount": 0, "failCount": 0}}),
                    encoding="utf-8",
                )
                thumb_path.write_bytes(b"thumb")

            class Result:
                returncode = 0
                stdout = ""
                stderr = ""

            return Result()

        self.backend.asyncio.create_subprocess_exec = fake_subprocess_exec
        self.backend.subprocess.run = fake_run
        try:
            await self.backend.run_pipeline(job_id, job_dir)
        finally:
            self.backend.asyncio.create_subprocess_exec = original_exec
            self.backend.subprocess.run = original_run

        meta = self.backend.load_meta(job_dir / "meta.json")
        self.assertEqual(meta["status"], "done")
        self.assertTrue(meta["hasQa"])
        self.assertEqual(meta["qaStatus"], "pass")
        self.assertIn("--auto-scenario", captured["cmd"])
        self.assertIn("--scenario-output", captured["cmd"])
        self.assertIn("--edit-output", captured["cmd"])

    async def test_pipeline_failure_marks_status_and_logs(self) -> None:
        job_id = "failed-job"
        job_dir = self.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "input.mp4").write_bytes(b"video")
        (job_dir / "scenario.json").write_text(
            json.dumps(
                {
                    "title": "Failure",
                    "sections": [
                        {
                            "title": "Only",
                            "description": "Failure case",
                            "timeRange": {"startSec": 0, "endSec": 1},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        self.backend.save_meta(
            job_dir / "meta.json",
            {
                "id": job_id,
                "title": "Failure",
                "inputMode": "manual",
                "status": "queued",
                "currentStep": 0,
                "createdAt": self.backend.utcnow_iso(),
                "startedAt": None,
                "completedAt": None,
                "fileSize": 0,
                "duration": None,
                "log": "",
            },
        )

        class FakeStdout:
            def __init__(self, lines):
                self._lines = iter(lines)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._lines)
                except StopIteration as exc:
                    raise StopAsyncIteration from exc

        class FakeProcess:
            def __init__(self):
                self.returncode = 1
                self.stdout = FakeStdout(
                    [
                        b"Step 1: Preprocessing\n",
                        b"Step 3: AI Edit Script Generation\n",
                        b"ERROR: Invalid scenario payload\n",
                    ]
                )

            async def wait(self):
                return self.returncode

        async def fake_subprocess_exec(*cmd, **kwargs):
            return FakeProcess()

        original_exec = self.backend.asyncio.create_subprocess_exec
        self.backend.asyncio.create_subprocess_exec = fake_subprocess_exec
        try:
            await self.backend.run_pipeline(job_id, job_dir)
        finally:
            self.backend.asyncio.create_subprocess_exec = original_exec

        meta = self.backend.load_meta(job_dir / "meta.json")
        self.assertEqual(meta["status"], "failed")
        self.assertEqual(meta["currentStep"], 3)
        self.assertIn("Invalid scenario payload", meta["log"])


if __name__ == "__main__":
    unittest.main()
