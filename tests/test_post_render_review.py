import unittest

from scripts.post_render_review import (
    analyze_edit_contract,
    evaluate_blank_frames,
    sample_timestamps,
    summarize_checks,
)


class PostRenderReviewTest(unittest.TestCase):
    def test_sample_timestamps_for_short_video(self) -> None:
        self.assertEqual(sample_timestamps(2.0), [1.0])

    def test_detects_caption_overlap_and_readability(self) -> None:
        checks = analyze_edit_contract(
            {
                "timeline": [
                    {
                        "type": "clip",
                        "transition": {"type": "fade", "durationSec": 0.1},
                        "overlays": [
                            {
                                "type": "caption",
                                "text": "Short",
                                "startSec": 0,
                                "durationSec": 2,
                            },
                            {
                                "type": "caption",
                                "text": "Dense technical announcement copy",
                                "startSec": 1,
                                "durationSec": 0.8,
                            },
                        ],
                    }
                ]
            }
        )

        self.assertEqual(checks["subtitleOverlapRisk"]["status"], "warn")
        self.assertEqual(checks["transitionSmoothness"]["status"], "warn")
        self.assertEqual(checks["timingReadability"]["status"], "warn")

    def test_blank_frame_evaluation_warns_on_dark_samples(self) -> None:
        result = evaluate_blank_frames(
            [
                {"timeSec": 1.0, "extracted": True, "yavg": 10.0},
                {"timeSec": 2.0, "extracted": True, "yavg": 40.0},
            ]
        )
        self.assertEqual(result["status"], "warn")
        self.assertEqual(len(result["issues"]), 1)

    def test_summary_counts_warn_and_fail(self) -> None:
        summary = summarize_checks(
            {
                "blankFrames": {"status": "fail", "issues": [{"timeSec": 1.0}]},
                "timingReadability": {"status": "warn", "issues": [{"entryIndex": 0}]},
            }
        )
        self.assertEqual(summary["status"], "fail")
        self.assertEqual(summary["warningCount"], 1)
        self.assertEqual(summary["failCount"], 1)


if __name__ == "__main__":
    unittest.main()
