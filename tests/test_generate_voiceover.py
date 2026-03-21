import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_voiceover import generate_voiceover_manifest, parse_args


class GenerateVoiceoverTest(unittest.TestCase):
    def test_mock_provider_generates_manifest_and_audio_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scenario_path = root / "scenario.json"
            scenario_path.write_text(
                json.dumps(
                    {
                        "title": "Mock TTS",
                        "language": "en",
                        "sections": [
                            {
                                "title": "Intro",
                                "description": "Explain the intro screen.",
                                "timeRange": {"startSec": 0, "endSec": 5},
                            },
                            {
                                "title": "Demo",
                                "description": "Show the primary workflow.",
                                "timeRange": {"startSec": 5, "endSec": 12},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            manifest_path = root / "voiceover" / "manifest.json"
            args = parse_args(
                [
                    "--scenario",
                    str(scenario_path),
                    "--output",
                    str(manifest_path),
                    "--provider",
                    "mock",
                ]
            )

            manifest = generate_voiceover_manifest(args)

            self.assertEqual(manifest["artifact"], "voiceover-manifest")
            self.assertEqual(manifest["provider"]["name"], "mock")
            self.assertEqual(manifest["summary"]["trackCount"], 2)
            self.assertEqual(manifest["summary"]["status"], "ready")
            self.assertTrue((root / "voiceover" / "section-01-intro.wav").exists())
            self.assertTrue((root / "voiceover" / "section-02-demo.wav").exists())
            self.assertEqual(
                manifest["tracks"][0]["src"],
                "voiceover/section-01-intro.wav",
            )
            self.assertGreater(manifest["tracks"][0]["durationSec"], 0)
            self.assertEqual(manifest["tracks"][0]["startSec"], 0.0)
            self.assertEqual(manifest["tracks"][1]["startSec"], 5.0)


if __name__ == "__main__":
    unittest.main()
