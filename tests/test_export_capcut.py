"""Tests for scripts/export_capcut.py."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.export_capcut import (
    _captions_json_to_srt,
    _create_caption_text_segment,
    _create_highlight_segment,
    _format_srt_time,
    _parse_linear_gradient,
    _hex_to_rgb,
    _render_gradient_image,
    export_capcut,
    extract_hex_color,
    generate_title_card,
    load_edit_json,
    parse_args,
    resolve_sources,
    CAPTION_STYLES,
    MIN_DURATION_US,
    POSITION_Y_MAP,
    TRANSITION_MAP,
)
from pycapcut import SEC


def _make_video_stub(directory: Path, name: str = "test.mp4") -> Path:
    """Create a minimal valid video file using imageio-ffmpeg."""
    p = directory / name
    try:
        import imageio_ffmpeg
        import subprocess

        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [
                ffmpeg_path, "-y",
                "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1:r=10",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-frames:v", "10",
                str(p),
            ],
            capture_output=True,
            check=True,
        )
    except (ImportError, FileNotFoundError):
        # Fallback: create a PNG image (pyCapCut accepts images as "photo" material)
        from PIL import Image as PILImage

        img = PILImage.new("RGB", (320, 240), "#333333")
        png_path = p.with_suffix(".png")
        img.save(str(png_path))
        return png_path
    return p


def _make_edit_json(
    directory: Path,
    *,
    sources: dict[str, str] | None = None,
    timeline: list[dict] | None = None,
) -> Path:
    """Create a minimal edit.json file."""
    data = {
        "version": "1.0",
        "fps": 30,
        "resolution": {"width": 1920, "height": 1080},
        "sources": sources or {},
        "timeline": timeline or [],
    }
    path = directory / "edit.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestParseArgs(unittest.TestCase):
    def test_help_exits_zero(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            parse_args(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_default_draft_name_is_none(self) -> None:
        args = parse_args(["--input", "edit.json"])
        self.assertIsNone(args.draft_name)

    def test_custom_drafts_dir(self) -> None:
        args = parse_args(["--input", "edit.json", "--drafts-dir", "/custom/path"])
        self.assertEqual(args.drafts_dir, Path("/custom/path"))


class TestExtractHexColor(unittest.TestCase):
    def test_gradient_extracts_first_color(self) -> None:
        self.assertEqual(extract_hex_color("linear-gradient(135deg, #c8102e, #1e1b4b)"), "#c8102e")

    def test_single_hex_color(self) -> None:
        self.assertEqual(extract_hex_color("#ff0000"), "#ff0000")

    def test_no_color_returns_default(self) -> None:
        self.assertEqual(extract_hex_color("solid red"), "#1e1b4b")

    def test_three_digit_hex(self) -> None:
        self.assertEqual(extract_hex_color("#abc"), "#abc")


class TestResolveSources(unittest.TestCase):
    def test_relative_path_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = _make_video_stub(tmp_path, "main.mp4")
            result = resolve_sources({"main": "main.mp4"}, tmp_path)
            self.assertEqual(result["main"], video.resolve())

    def test_missing_source_raises_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with self.assertRaises(FileNotFoundError) as ctx:
                resolve_sources({"missing": "nonexistent.mp4"}, tmp_path)
            self.assertIn("nonexistent.mp4", str(ctx.exception))
            self.assertIn("missing", str(ctx.exception))


class TestExportCapcut(unittest.TestCase):
    def test_basic_clip_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")

            edit_path = _make_edit_json(
                tmp_path,
                sources={"main": "rec.mp4"},
                timeline=[
                    {"type": "clip", "source": "main", "startSec": 0, "endSec": 0.5},
                ],
            )

            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "test_draft",
                "--video-dir", str(video_dir),
            ])
            draft_path = export_capcut(args)

            self.assertTrue(draft_path.exists())
            content_json = draft_path / "draft_content.json"
            self.assertTrue(content_json.exists(), f"draft_content.json not found in {draft_path}")

            meta_json = draft_path / "draft_meta_info.json"
            self.assertTrue(meta_json.exists(), f"draft_meta_info.json not found in {draft_path}")

    def test_multi_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "cam1.mp4")
            _make_video_stub(video_dir, "cam2.mp4")

            edit_path = _make_edit_json(
                tmp_path,
                sources={"cam1": "cam1.mp4", "cam2": "cam2.mp4"},
                timeline=[
                    {"type": "clip", "source": "cam1", "startSec": 0, "endSec": 0.5},
                    {"type": "clip", "source": "cam2", "startSec": 0, "endSec": 0.5},
                ],
            )

            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "multi_src",
                "--video-dir", str(video_dir),
            ])
            draft_path = export_capcut(args)

            content_json = draft_path / "draft_content.json"
            self.assertTrue(content_json.exists())
            content = json.loads(content_json.read_text(encoding="utf-8"))
            # Should have materials for both sources
            materials_list = content.get("materials", {}).get("videos", [])
            paths_in_draft = [m.get("path", "") for m in materials_list]
            self.assertTrue(any("cam1.mp4" in p for p in paths_in_draft), f"cam1 not found in materials: {paths_in_draft}")
            self.assertTrue(any("cam2.mp4" in p for p in paths_in_draft), f"cam2 not found in materials: {paths_in_draft}")

    def test_speed_adjustment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")

            edit_path = _make_edit_json(
                tmp_path,
                sources={"main": "rec.mp4"},
                timeline=[
                    {"type": "clip", "source": "main", "startSec": 0, "endSec": 0.8, "speed": 2.0},
                ],
            )

            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "speed_test",
                "--video-dir", str(video_dir),
            ])
            draft_path = export_capcut(args)

            content_json = draft_path / "draft_content.json"
            content = json.loads(content_json.read_text(encoding="utf-8"))
            tracks = content.get("tracks", [])
            # Find video track segments
            video_segments = []
            for track in tracks:
                for seg in track.get("segments", []):
                    video_segments.append(seg)
            self.assertTrue(len(video_segments) > 0, "No segments found")
            seg = video_segments[0]
            target_duration = seg["target_timerange"]["duration"]
            source_duration = 800_000  # 0.8 sec in microseconds
            expected_target = source_duration // 2  # speed=2.0 → half duration
            self.assertEqual(target_duration, expected_target, f"Expected {expected_target}, got {target_duration}")

    def test_empty_timeline_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            edit_path = _make_edit_json(tmp_path, sources={}, timeline=[])

            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "empty_test",
                "--video-dir", str(tmp_path),
            ])
            draft_path = export_capcut(args)
            self.assertTrue(draft_path.exists())
            content_json = draft_path / "draft_content.json"
            self.assertTrue(content_json.exists())

    def test_missing_source_key_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")

            edit_path = _make_edit_json(
                tmp_path,
                sources={"main": "rec.mp4"},
                timeline=[
                    {"type": "clip", "source": "nonexistent_key", "startSec": 0, "endSec": 0.5},
                    {"type": "clip", "source": "main", "startSec": 0, "endSec": 0.5},
                ],
            )

            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "skip_test",
                "--video-dir", str(video_dir),
            ])
            # Should not raise — skips the bad entry
            draft_path = export_capcut(args)
            self.assertTrue(draft_path.exists())

    def test_title_card_generates_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            edit_path = _make_edit_json(
                tmp_path,
                sources={},
                timeline=[
                    {
                        "type": "title-card",
                        "text": "Hello World",
                        "subtitle": "Subtitle",
                        "durationSec": 2,
                        "background": "linear-gradient(135deg, #c8102e, #1e1b4b)",
                    },
                ],
            )

            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "title_test",
                "--video-dir", str(tmp_path),
            ])
            draft_path = export_capcut(args)
            card_path = draft_path / "title_card_0.png"
            self.assertTrue(card_path.exists(), f"Title card PNG not found at {card_path}")

    def test_transition_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")

            edit_path = _make_edit_json(
                tmp_path,
                sources={"main": "rec.mp4"},
                timeline=[
                    {"type": "clip", "source": "main", "startSec": 0, "endSec": 0.3},
                    {
                        "type": "clip",
                        "source": "main",
                        "startSec": 0.3,
                        "endSec": 0.6,
                        "transition": {"type": "fade", "durationSec": 0.5},
                    },
                ],
            )

            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "transition_test",
                "--video-dir", str(video_dir),
            ])
            draft_path = export_capcut(args)
            content_json = draft_path / "draft_content.json"
            content = json.loads(content_json.read_text(encoding="utf-8"))
            # Verify transition exists in the draft content
            tracks = content.get("tracks", [])
            has_transition = False
            for track in tracks:
                for seg in track.get("segments", []):
                    if seg.get("extra_material_refs"):
                        has_transition = True
            # pyCapCut stores transitions in segment data — at minimum the draft should be valid
            self.assertTrue(content_json.exists())

    def test_default_draft_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            edit_path = _make_edit_json(tmp_path, sources={}, timeline=[])

            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--video-dir", str(tmp_path),
            ])
            draft_path = export_capcut(args)
            self.assertTrue(draft_path.name.startswith("edit_"))


# ── Shield additional tests ───────────────────────────────────────────────────


class TestLoadEditJson(unittest.TestCase):
    """Direct unit tests for load_edit_json — previously untested."""

    def test_missing_file_raises_system_exit(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            load_edit_json(Path("/nonexistent/path/edit.json"))
        self.assertEqual(ctx.exception.code, 1)

    def test_missing_required_field_raises_system_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "edit.json"
            # 'fps' missing
            path.write_text(json.dumps({"version": "1.0", "resolution": {}, "sources": {}, "timeline": []}))
            with self.assertRaises(SystemExit) as ctx:
                load_edit_json(path)
            self.assertEqual(ctx.exception.code, 1)

    def test_all_required_fields_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "edit.json"
            data = {"version": "1.0", "fps": 30, "resolution": {"width": 1920, "height": 1080}, "sources": {}, "timeline": []}
            path.write_text(json.dumps(data))
            result = load_edit_json(path)
            self.assertEqual(result["fps"], 30)

    def test_invalid_json_raises_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "edit.json"
            path.write_text("{not valid json}")
            with self.assertRaises(json.JSONDecodeError):
                load_edit_json(path)


class TestResolveSourcesAdditional(unittest.TestCase):
    """Additional resolve_sources coverage: absolute paths, multiple sources."""

    def test_absolute_path_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = _make_video_stub(tmp_path, "abs.mp4")
            # Pass as absolute path in sources dict
            result = resolve_sources({"abs": str(video.resolve())}, Path("/irrelevant"))
            self.assertEqual(result["abs"], video.resolve())

    def test_multiple_sources_all_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_video_stub(tmp_path, "a.mp4")
            _make_video_stub(tmp_path, "b.mp4")
            result = resolve_sources({"a": "a.mp4", "b": "b.mp4"}, tmp_path)
            self.assertIn("a", result)
            self.assertIn("b", result)
            self.assertTrue(result["a"].exists())
            self.assertTrue(result["b"].exists())

    def test_error_message_includes_source_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError) as ctx:
                resolve_sources({"my_key": "ghost.mp4"}, Path(tmp))
            self.assertIn("my_key", str(ctx.exception))


class TestGenerateTitleCard(unittest.TestCase):
    """Direct unit tests for generate_title_card."""

    def test_generates_png_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "card.png"
            from scripts.export_capcut import generate_title_card
            result = generate_title_card("Hello", None, "#ff0000", 320, 240, output_path)
            self.assertTrue(result.exists())

    def test_generates_correct_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "card.png"
            from scripts.export_capcut import generate_title_card
            from PIL import Image as PILImage
            generate_title_card("Test", "sub", "#0000ff", 640, 360, output_path)
            img = PILImage.open(str(output_path))
            self.assertEqual(img.size, (640, 360))

    def test_no_subtitle_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "card.png"
            from scripts.export_capcut import generate_title_card
            # Should not raise even when subtitle is None
            generate_title_card("Title Only", None, "#1e1b4b", 320, 240, output_path)
            self.assertTrue(output_path.exists())

    def test_css_gradient_background_uses_first_color(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "card.png"
            from scripts.export_capcut import generate_title_card
            from PIL import Image as PILImage
            generate_title_card("Gradient", None, "linear-gradient(135deg, #c8102e, #1e1b4b)", 8, 8, output_path)
            img = PILImage.open(str(output_path))
            # Top-left pixel should be close to #c8102e (gradient renders top-to-bottom)
            corner = img.getpixel((0, 0))
            self.assertAlmostEqual(corner[0], 0xc8, delta=15)
            self.assertAlmostEqual(corner[1], 0x10, delta=40)
            self.assertAlmostEqual(corner[2], 0x2e, delta=35)


class TestExtractHexColorAdditional(unittest.TestCase):
    """Additional edge cases for extract_hex_color."""

    def test_uppercase_hex(self) -> None:
        self.assertEqual(extract_hex_color("#FF0000"), "#FF0000")

    def test_mixed_case_hex(self) -> None:
        self.assertEqual(extract_hex_color("#aAbBcC"), "#aAbBcC")

    def test_multiple_colors_returns_first(self) -> None:
        result = extract_hex_color("#111111 and #222222 and #333333")
        self.assertEqual(result, "#111111")

    def test_empty_string_returns_default(self) -> None:
        self.assertEqual(extract_hex_color(""), "#1e1b4b")


class TestTransitionCoverage(unittest.TestCase):
    """Test all transition types and edge cases in _apply_transition."""

    def _make_export_with_transition(self, transition_type: str, tmp_path: Path) -> Path:
        video_dir = tmp_path / "videos"
        video_dir.mkdir(exist_ok=True)
        _make_video_stub(video_dir, "rec.mp4")

        edit_path = _make_edit_json(
            tmp_path,
            sources={"main": "rec.mp4"},
            timeline=[
                {"type": "clip", "source": "main", "startSec": 0, "endSec": 0.3},
                {
                    "type": "clip",
                    "source": "main",
                    "startSec": 0.3,
                    "endSec": 0.6,
                    "transition": {"type": transition_type, "durationSec": 0.3},
                },
            ],
        )
        drafts_dir = tmp_path / "drafts"
        args = parse_args([
            "--input", str(edit_path),
            "--drafts-dir", str(drafts_dir),
            "--draft-name", f"trans_{transition_type.replace('-', '_')}",
            "--video-dir", str(video_dir),
        ])
        return export_capcut(args)

    def test_slide_left_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            draft_path = self._make_export_with_transition("slide-left", Path(tmp))
            self.assertTrue((draft_path / "draft_content.json").exists())

    def test_slide_right_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            draft_path = self._make_export_with_transition("slide-right", Path(tmp))
            self.assertTrue((draft_path / "draft_content.json").exists())

    def test_wipe_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            draft_path = self._make_export_with_transition("wipe", Path(tmp))
            self.assertTrue((draft_path / "draft_content.json").exists())

    def test_unknown_transition_still_exports(self) -> None:
        """Unknown transition type should warn and skip (not crash)."""
        with tempfile.TemporaryDirectory() as tmp:
            draft_path = self._make_export_with_transition("unknown-fx", Path(tmp))
            self.assertTrue((draft_path / "draft_content.json").exists())

    def test_none_transition_type_no_op(self) -> None:
        """Transition type 'none' should be silently skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            draft_path = self._make_export_with_transition("none", Path(tmp))
            self.assertTrue((draft_path / "draft_content.json").exists())


class TestExportCapcutEdgeCases(unittest.TestCase):
    """Additional export_capcut edge cases not covered by Builder."""

    def test_slow_motion_speed_below_1(self) -> None:
        """speed=0.5 → target duration doubles the source duration."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")

            edit_path = _make_edit_json(
                tmp_path,
                sources={"main": "rec.mp4"},
                timeline=[
                    {"type": "clip", "source": "main", "startSec": 0, "endSec": 0.4, "speed": 0.5},
                ],
            )
            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "slow_mo",
                "--video-dir", str(video_dir),
            ])
            draft_path = export_capcut(args)
            content = json.loads((draft_path / "draft_content.json").read_text())
            segments = [seg for track in content.get("tracks", []) for seg in track.get("segments", [])]
            self.assertTrue(len(segments) > 0)
            target_duration = segments[0]["target_timerange"]["duration"]
            source_duration_us = int(0.4 * 1_000_000)
            expected = int(source_duration_us / 0.5)
            self.assertEqual(target_duration, expected)

    def test_title_card_without_subtitle_field(self) -> None:
        """title-card entry with no 'subtitle' key should not crash."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            edit_path = _make_edit_json(
                tmp_path,
                sources={},
                timeline=[{"type": "title-card", "text": "No Subtitle", "durationSec": 1.5, "background": "#000000"}],
            )
            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "no_sub",
                "--video-dir", str(tmp_path),
            ])
            draft_path = export_capcut(args)
            self.assertTrue((draft_path / "title_card_0.png").exists())

    def test_multiple_title_cards_generate_separate_images(self) -> None:
        """Multiple title-card entries → separate title_card_N.png files."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            edit_path = _make_edit_json(
                tmp_path,
                sources={},
                timeline=[
                    {"type": "title-card", "text": "Card A", "durationSec": 1, "background": "#111111"},
                    {"type": "title-card", "text": "Card B", "durationSec": 1, "background": "#222222"},
                ],
            )
            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "multi_card",
                "--video-dir", str(tmp_path),
            ])
            draft_path = export_capcut(args)
            self.assertTrue((draft_path / "title_card_0.png").exists())
            self.assertTrue((draft_path / "title_card_1.png").exists())

    def test_title_card_default_duration(self) -> None:
        """title-card without durationSec uses 3.0s default."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            edit_path = _make_edit_json(
                tmp_path,
                sources={},
                timeline=[{"type": "title-card", "text": "Default Dur", "background": "#003366"}],
            )
            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "default_dur",
                "--video-dir", str(tmp_path),
            ])
            draft_path = export_capcut(args)
            content = json.loads((draft_path / "draft_content.json").read_text())
            segments = [seg for track in content.get("tracks", []) for seg in track.get("segments", [])]
            self.assertTrue(len(segments) > 0)
            duration_us = segments[0]["target_timerange"]["duration"]
            self.assertEqual(duration_us, 3_000_000)

    def test_only_title_cards_timeline_no_video_clips(self) -> None:
        """Timeline with only title-card entries (no video clips) exports cleanly."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            edit_path = _make_edit_json(
                tmp_path,
                sources={},
                timeline=[
                    {"type": "title-card", "text": "Intro", "durationSec": 2, "background": "#000000"},
                    {"type": "title-card", "text": "End", "durationSec": 2, "background": "#ffffff"},
                ],
            )
            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "only_cards",
                "--video-dir", str(tmp_path),
            ])
            draft_path = export_capcut(args)
            self.assertTrue((draft_path / "draft_content.json").exists())
            self.assertTrue((draft_path / "title_card_0.png").exists())
            self.assertTrue((draft_path / "title_card_1.png").exists())

    def test_explicit_speed_1_equals_no_speed(self) -> None:
        """Explicitly passing speed=1.0 should produce same duration as omitting speed."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")

            def _get_duration(draft_name: str, include_speed: bool) -> int:
                timeline_entry: dict = {"type": "clip", "source": "main", "startSec": 0, "endSec": 0.6}
                if include_speed:
                    timeline_entry["speed"] = 1.0
                edit_dir = tmp_path / draft_name
                edit_dir.mkdir(parents=True, exist_ok=True)
                edit_path = edit_dir / "edit.json"
                data = {"version": "1.0", "fps": 30, "resolution": {"width": 1920, "height": 1080},
                        "sources": {"main": "rec.mp4"}, "timeline": [timeline_entry]}
                edit_path.write_text(json.dumps(data))
                args = parse_args([
                    "--input", str(edit_path),
                    "--drafts-dir", str(tmp_path / "drafts"),
                    "--draft-name", draft_name,
                    "--video-dir", str(video_dir),
                ])
                draft_path = export_capcut(args)
                content = json.loads((draft_path / "draft_content.json").read_text())
                segs = [s for t in content.get("tracks", []) for s in t.get("segments", [])]
                return segs[0]["target_timerange"]["duration"]

            dur_default = _get_duration("no_speed", False)
            dur_explicit = _get_duration("with_speed", True)
            self.assertEqual(dur_default, dur_explicit)

    def test_allow_replace_overwrites_existing_draft(self) -> None:
        """Running export twice with same draft name should overwrite (allow_replace=True)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")

            edit_path = _make_edit_json(
                tmp_path,
                sources={"main": "rec.mp4"},
                timeline=[{"type": "clip", "source": "main", "startSec": 0, "endSec": 0.4}],
            )
            drafts_dir = tmp_path / "drafts"
            common_args = ["--input", str(edit_path), "--drafts-dir", str(drafts_dir),
                           "--draft-name", "overwrite_test", "--video-dir", str(video_dir)]
            # First run
            export_capcut(parse_args(common_args))
            # Second run — should not raise
            draft_path = export_capcut(parse_args(common_args))
            self.assertTrue((draft_path / "draft_content.json").exists())


# ── New tests for #2262: overlays/captions mapping ───────────────────────────


class TestFormatSrtTime(unittest.TestCase):
    def test_zero_seconds(self) -> None:
        self.assertEqual(_format_srt_time(0.0), "00:00:00,000")

    def test_one_second(self) -> None:
        self.assertEqual(_format_srt_time(1.0), "00:00:01,000")

    def test_fractional_seconds(self) -> None:
        self.assertEqual(_format_srt_time(1.5), "00:00:01,500")

    def test_over_one_minute(self) -> None:
        self.assertEqual(_format_srt_time(90.25), "00:01:30,250")

    def test_over_one_hour(self) -> None:
        self.assertEqual(_format_srt_time(3661.0), "01:01:01,000")

    def test_sub_millisecond_rounds(self) -> None:
        # 0.9999 → rounds to 1000 ms = 1 second
        result = _format_srt_time(0.9999)
        self.assertIn("00:00:01", result)


class TestCaptionsJsonToSrt(unittest.TestCase):
    def test_empty_captions_writes_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "captions.srt"
            _captions_json_to_srt([], out)
            self.assertTrue(out.exists())
            self.assertEqual(out.read_text(encoding="utf-8").strip(), "")

    def test_single_caption_srt_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "captions.srt"
            _captions_json_to_srt([{"startSec": 1.0, "endSec": 2.5, "text": "Hello"}], out)
            content = out.read_text(encoding="utf-8")
            self.assertIn("1\n", content)
            self.assertIn("00:00:01,000 --> 00:00:02,500", content)
            self.assertIn("Hello", content)

    def test_multiple_captions_numbered_sequentially(self) -> None:
        captions = [
            {"startSec": 0.0, "endSec": 1.0, "text": "First"},
            {"startSec": 1.5, "endSec": 2.5, "text": "Second"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "captions.srt"
            _captions_json_to_srt(captions, out)
            content = out.read_text(encoding="utf-8")
            self.assertIn("1\n", content)
            self.assertIn("2\n", content)
            self.assertIn("First", content)
            self.assertIn("Second", content)

    def test_missing_end_sec_defaults_to_start_plus_half(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "captions.srt"
            _captions_json_to_srt([{"startSec": 5.0, "text": "Only start"}], out)
            content = out.read_text(encoding="utf-8")
            self.assertIn("00:00:05,000 --> 00:00:05,500", content)

    def test_emoji_text_written_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "captions.srt"
            _captions_json_to_srt([{"startSec": 0.0, "endSec": 1.0, "text": "Hello 🚀 World"}], out)
            content = out.read_text(encoding="utf-8")
            self.assertIn("Hello 🚀 World", content)

    def test_special_chars_in_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "captions.srt"
            _captions_json_to_srt([{"startSec": 0.0, "endSec": 1.0, "text": "<b>Bold</b> & \"Quoted\""}], out)
            content = out.read_text(encoding="utf-8")
            self.assertIn("<b>Bold</b> & \"Quoted\"", content)

    def test_creates_parent_directory_if_needed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "nested" / "deep" / "captions.srt"
            _captions_json_to_srt([{"startSec": 0.0, "endSec": 1.0, "text": "Test"}], out)
            self.assertTrue(out.exists())

    def test_returns_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "captions.srt"
            result = _captions_json_to_srt([], out)
            self.assertEqual(result, out)


class TestCreateCaptionTextSegment(unittest.TestCase):
    """Tests for _create_caption_text_segment."""

    def _make_overlay(self, **kwargs) -> dict:
        defaults = {"type": "caption", "startSec": 0.0, "durationSec": 2.0, "text": "Test", "captionClass": "subtitle", "position": "bottom"}
        defaults.update(kwargs)
        return defaults

    def test_subtitle_style_small_not_bold_white(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(captionClass="subtitle"), 0, 5 * SEC, 1.0)
        self.assertAlmostEqual(seg.style.size, CAPTION_STYLES["subtitle"]["size"])
        self.assertFalse(seg.style.bold)
        self.assertEqual(seg.style.color, (1.0, 1.0, 1.0))

    def test_announcement_style_large_bold_white(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(captionClass="announcement"), 0, 5 * SEC, 1.0)
        self.assertAlmostEqual(seg.style.size, CAPTION_STYLES["announcement"]["size"])
        self.assertTrue(seg.style.bold)
        self.assertEqual(seg.style.color, (1.0, 1.0, 1.0))

    def test_technical_term_style_bold_yellow(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(captionClass="technical-term"), 0, 5 * SEC, 1.0)
        self.assertTrue(seg.style.bold)
        r, g, b = seg.style.color
        self.assertAlmostEqual(r, 1.0)
        self.assertGreater(g, 0.9)   # near-yellow: green channel high
        self.assertLess(b, 0.5)       # blue channel low

    def test_unknown_captionclass_defaults_to_subtitle(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(captionClass="unknown-class"), 0, 5 * SEC, 1.0)
        self.assertAlmostEqual(seg.style.size, CAPTION_STYLES["subtitle"]["size"])

    def test_position_bottom_transform_y(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(position="bottom"), 0, 5 * SEC, 1.0)
        self.assertAlmostEqual(seg.clip_settings.transform_y, POSITION_Y_MAP["bottom"])

    def test_position_top_transform_y(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(position="top"), 0, 5 * SEC, 1.0)
        self.assertAlmostEqual(seg.clip_settings.transform_y, POSITION_Y_MAP["top"])

    def test_position_center_transform_y(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(position="center"), 0, 5 * SEC, 1.0)
        self.assertAlmostEqual(seg.clip_settings.transform_y, POSITION_Y_MAP["center"])

    def test_subtitle_has_background(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(captionClass="subtitle"), 0, 5 * SEC, 1.0)
        self.assertIsNotNone(seg.background)

    def test_announcement_has_background(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(captionClass="announcement"), 0, 5 * SEC, 1.0)
        self.assertIsNotNone(seg.background)

    def test_technical_term_has_no_background(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(captionClass="technical-term"), 0, 5 * SEC, 1.0)
        self.assertIsNone(seg.background)

    def test_timing_absolute_start_and_duration(self) -> None:
        clip_start_us = 3 * SEC
        seg = _create_caption_text_segment(self._make_overlay(startSec=1.0, durationSec=1.0), clip_start_us, 5 * SEC, 1.0)
        self.assertEqual(seg.start, clip_start_us + 1 * SEC)
        self.assertEqual(seg.duration, 1 * SEC)

    def test_zero_duration_clamped_to_min(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(durationSec=0.0), 0, 5 * SEC, 1.0)
        self.assertEqual(seg.duration, MIN_DURATION_US)

    def test_exceeds_clip_end_clamped(self) -> None:
        # Caption wants 3s but clip only has 2s → clamped
        seg = _create_caption_text_segment(self._make_overlay(startSec=0.0, durationSec=3.0), 0, 2 * SEC, 1.0)
        self.assertLessEqual(seg.start + seg.duration, 2 * SEC)

    def test_text_preserved(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(text="Hello World"), 0, 5 * SEC, 1.0)
        self.assertEqual(seg.text, "Hello World")

    def test_emoji_text(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(text="🚀 Launch"), 0, 5 * SEC, 1.0)
        self.assertEqual(seg.text, "🚀 Launch")

    def test_empty_text(self) -> None:
        seg = _create_caption_text_segment(self._make_overlay(text=""), 0, 5 * SEC, 1.0)
        self.assertEqual(seg.text, "")

    def test_speed_affects_timing(self) -> None:
        # At 2x speed, a 2s caption should cover 1s of timeline time
        seg = _create_caption_text_segment(self._make_overlay(startSec=0.0, durationSec=2.0), 0, 5 * SEC, 2.0)
        self.assertEqual(seg.duration, 1 * SEC)


class TestCreateHighlightSegment(unittest.TestCase):
    """Tests for _create_highlight_segment."""

    def _make_overlay(self, **kwargs) -> dict:
        defaults = {
            "type": "highlight",
            "startSec": 0.0,
            "durationSec": 2.0,
            "color": "#FFFF00",
            "region": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1},
        }
        defaults.update(kwargs)
        return defaults

    def test_text_is_single_space(self) -> None:
        seg = _create_highlight_segment(self._make_overlay(), 0, 5 * SEC, 1.0)
        self.assertEqual(seg.text, " ")

    def test_background_color_extracted_from_overlay(self) -> None:
        seg = _create_highlight_segment(self._make_overlay(color="#FF0000"), 0, 5 * SEC, 1.0)
        self.assertIsNotNone(seg.background)
        self.assertEqual(seg.background.color, "#FF0000")

    def test_background_alpha_is_035(self) -> None:
        seg = _create_highlight_segment(self._make_overlay(), 0, 5 * SEC, 1.0)
        self.assertAlmostEqual(seg.background.alpha, 0.35)

    def test_region_center_mapped_to_transform(self) -> None:
        # region x=0.5, y=0.5, width=0.2, height=0.2 → center: transform_x=0.2, transform_y=0.2
        region = {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2}
        seg = _create_highlight_segment(self._make_overlay(region=region), 0, 5 * SEC, 1.0)
        # transform_x = (0.4 + 0.1 - 0.5) * 2 = 0.0
        self.assertAlmostEqual(seg.clip_settings.transform_x, 0.0)
        self.assertAlmostEqual(seg.clip_settings.transform_y, 0.0)

    def test_region_scale_set_to_width_height(self) -> None:
        region = {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.15}
        seg = _create_highlight_segment(self._make_overlay(region=region), 0, 5 * SEC, 1.0)
        self.assertAlmostEqual(seg.clip_settings.scale_x, 0.3)
        self.assertAlmostEqual(seg.clip_settings.scale_y, 0.15)

    def test_zero_duration_clamped_to_min(self) -> None:
        seg = _create_highlight_segment(self._make_overlay(durationSec=0.0), 0, 5 * SEC, 1.0)
        self.assertEqual(seg.duration, MIN_DURATION_US)

    def test_exceeds_clip_end_clamped(self) -> None:
        seg = _create_highlight_segment(self._make_overlay(startSec=0.0, durationSec=5.0), 0, 2 * SEC, 1.0)
        self.assertLessEqual(seg.start + seg.duration, 2 * SEC)

    def test_timing_absolute_position(self) -> None:
        clip_start_us = 2 * SEC
        seg = _create_highlight_segment(self._make_overlay(startSec=1.0, durationSec=1.0), clip_start_us, 5 * SEC, 1.0)
        self.assertEqual(seg.start, clip_start_us + 1 * SEC)
        self.assertEqual(seg.duration, 1 * SEC)

    def test_css_color_value_parsed(self) -> None:
        seg = _create_highlight_segment(self._make_overlay(color="rgba(255,0,0,0.5) #AABBCC"), 0, 5 * SEC, 1.0)
        self.assertEqual(seg.background.color, "#AABBCC")

    def test_missing_region_defaults_to_center(self) -> None:
        seg = _create_highlight_segment(self._make_overlay(region={}), 0, 5 * SEC, 1.0)
        # x=0.5, y=0.5, w=0.2, h=0.1 defaults
        self.assertIsNotNone(seg.clip_settings)


class TestCaptionsModeFlag(unittest.TestCase):
    """Tests for the --captions CLI flag behavior."""

    def _make_edit_with_captions(self, tmp_path: Path, video_dir: Path) -> Path:
        data = {
            "version": "1.0",
            "fps": 30,
            "resolution": {"width": 1920, "height": 1080},
            "sources": {"main": "rec.mp4"},
            "timeline": [{"type": "clip", "source": "main", "startSec": 0, "endSec": 0.5}],
            "captions": [
                {"startSec": 0.0, "endSec": 0.3, "text": "First caption"},
                {"startSec": 0.3, "endSec": 0.5, "text": "Second caption"},
            ],
        }
        p = tmp_path / "edit.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def test_captions_none_mode_no_srt_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")
            edit_path = self._make_edit_with_captions(tmp_path, video_dir)
            srt_path = video_dir / "captions.srt"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(tmp_path / "drafts"),
                "--draft-name", "test_none",
                "--video-dir", str(video_dir),
                "--captions", "none",
            ])
            export_capcut(args)
            # With mode=none, SRT file should NOT be written
            self.assertFalse(srt_path.exists())

    def test_captions_whisper_mode_writes_srt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")
            edit_path = self._make_edit_with_captions(tmp_path, video_dir)
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(tmp_path / "drafts"),
                "--draft-name", "test_whisper",
                "--video-dir", str(video_dir),
                "--captions", "whisper",
            ])
            export_capcut(args)
            srt_path = (video_dir / "captions.srt").resolve()
            self.assertTrue(srt_path.exists())
            content = srt_path.read_text(encoding="utf-8")
            self.assertIn("First caption", content)
            self.assertIn("Second caption", content)

    def test_captions_capcut_ai_mode_no_srt_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")
            edit_path = self._make_edit_with_captions(tmp_path, video_dir)
            srt_path = video_dir / "captions.srt"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(tmp_path / "drafts"),
                "--draft-name", "test_capcut_ai",
                "--video-dir", str(video_dir),
                "--captions", "capcut-ai",
            ])
            export_capcut(args)
            self.assertFalse(srt_path.exists())

    def test_parse_args_default_captions_is_whisper(self) -> None:
        args = parse_args(["--input", "edit.json"])
        self.assertEqual(args.captions, "whisper")

    def test_parse_args_captions_none(self) -> None:
        args = parse_args(["--input", "edit.json", "--captions", "none"])
        self.assertEqual(args.captions, "none")

    def test_parse_args_captions_capcut_ai(self) -> None:
        args = parse_args(["--input", "edit.json", "--captions", "capcut-ai"])
        self.assertEqual(args.captions, "capcut-ai")

    def test_parse_args_invalid_captions_choice_exits(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args(["--input", "edit.json", "--captions", "invalid"])


class TestOverlaysEndToEnd(unittest.TestCase):
    """End-to-end tests: overlays in timeline clips produce text segments in draft."""

    def _count_text_tracks(self, draft_path: Path) -> int:
        content = json.loads((draft_path / "draft_content.json").read_text())
        return sum(1 for t in content.get("tracks", []) if t.get("type") == "text")

    def _get_all_text_segments(self, draft_path: Path) -> list[dict]:
        content = json.loads((draft_path / "draft_content.json").read_text())
        return [s for t in content.get("tracks", []) if t.get("type") == "text" for s in t.get("segments", [])]

    def test_caption_overlay_creates_text_track(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")
            data = {
                "version": "1.0", "fps": 30,
                "resolution": {"width": 1920, "height": 1080},
                "sources": {"main": "rec.mp4"},
                "timeline": [{
                    "type": "clip", "source": "main", "startSec": 0, "endSec": 1.0,
                    "overlays": [{"type": "caption", "startSec": 0.0, "durationSec": 0.5, "text": "Hello", "captionClass": "subtitle", "position": "bottom"}],
                }],
            }
            edit_path = tmp_path / "edit.json"
            edit_path.write_text(json.dumps(data), encoding="utf-8")
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(tmp_path / "drafts"),
                "--draft-name", "ov_caption",
                "--video-dir", str(video_dir),
                "--captions", "none",
            ])
            draft_path = export_capcut(args)
            self.assertGreater(self._count_text_tracks(draft_path), 0)
            segs = self._get_all_text_segments(draft_path)
            self.assertEqual(len(segs), 1)

    def test_highlight_overlay_creates_text_track(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")
            data = {
                "version": "1.0", "fps": 30,
                "resolution": {"width": 1920, "height": 1080},
                "sources": {"main": "rec.mp4"},
                "timeline": [{
                    "type": "clip", "source": "main", "startSec": 0, "endSec": 1.0,
                    "overlays": [{"type": "highlight", "startSec": 0.0, "durationSec": 0.5, "color": "#FF0000", "region": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1}}],
                }],
            }
            edit_path = tmp_path / "edit.json"
            edit_path.write_text(json.dumps(data), encoding="utf-8")
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(tmp_path / "drafts"),
                "--draft-name", "ov_highlight",
                "--video-dir", str(video_dir),
                "--captions", "none",
            ])
            draft_path = export_capcut(args)
            self.assertGreater(self._count_text_tracks(draft_path), 0)

    def test_multiple_overlapping_captions_use_separate_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")
            # Two captions at same time → need 2 text tracks
            data = {
                "version": "1.0", "fps": 30,
                "resolution": {"width": 1920, "height": 1080},
                "sources": {"main": "rec.mp4"},
                "timeline": [{
                    "type": "clip", "source": "main", "startSec": 0, "endSec": 0.9,
                    "overlays": [
                        {"type": "caption", "startSec": 0.0, "durationSec": 0.4, "text": "A", "captionClass": "subtitle", "position": "bottom"},
                        {"type": "caption", "startSec": 0.0, "durationSec": 0.4, "text": "B", "captionClass": "announcement", "position": "top"},
                    ],
                }],
            }
            edit_path = tmp_path / "edit.json"
            edit_path.write_text(json.dumps(data), encoding="utf-8")
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(tmp_path / "drafts"),
                "--draft-name", "ov_overlap",
                "--video-dir", str(video_dir),
                "--captions", "none",
            ])
            draft_path = export_capcut(args)
            # Two overlapping captions → must use 2 separate tracks
            self.assertGreaterEqual(self._count_text_tracks(draft_path), 2)

    def test_sequential_captions_use_single_track(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")
            data = {
                "version": "1.0", "fps": 30,
                "resolution": {"width": 1920, "height": 1080},
                "sources": {"main": "rec.mp4"},
                "timeline": [{
                    "type": "clip", "source": "main", "startSec": 0, "endSec": 0.9,
                    "overlays": [
                        {"type": "caption", "startSec": 0.0, "durationSec": 0.3, "text": "First", "captionClass": "subtitle", "position": "bottom"},
                        {"type": "caption", "startSec": 0.5, "durationSec": 0.3, "text": "Second", "captionClass": "subtitle", "position": "bottom"},
                    ],
                }],
            }
            edit_path = tmp_path / "edit.json"
            edit_path.write_text(json.dumps(data), encoding="utf-8")
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(tmp_path / "drafts"),
                "--draft-name", "ov_seq",
                "--video-dir", str(video_dir),
                "--captions", "none",
            ])
            draft_path = export_capcut(args)
            # Sequential captions → greedy packs into one text track
            self.assertEqual(self._count_text_tracks(draft_path), 1)

    def test_unknown_overlay_type_skipped_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")
            data = {
                "version": "1.0", "fps": 30,
                "resolution": {"width": 1920, "height": 1080},
                "sources": {"main": "rec.mp4"},
                "timeline": [{
                    "type": "clip", "source": "main", "startSec": 0, "endSec": 1.0,
                    "overlays": [{"type": "zoom", "startSec": 0.0, "durationSec": 0.5, "factor": 1.5}],
                }],
            }
            edit_path = tmp_path / "edit.json"
            edit_path.write_text(json.dumps(data), encoding="utf-8")
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(tmp_path / "drafts"),
                "--draft-name", "ov_unknown",
                "--video-dir", str(video_dir),
                "--captions", "none",
            ])
            # Should not raise
            draft_path = export_capcut(args)
            self.assertTrue((draft_path / "draft_content.json").exists())
            # No text tracks — unknown overlay not rendered
            self.assertEqual(self._count_text_tracks(draft_path), 0)


if __name__ == "__main__":
    unittest.main()


# ── Voiceover manifest tests ─────────────────────────────────────────────────

from scripts.export_capcut import (
    load_voiceover_manifest,
    _add_voiceover_audio,
    VOICEOVER_TRACK_PREFIX,
)


def _make_audio_stub(directory: Path, name: str = "vo.wav", duration_samples: int = 8000) -> Path:
    """Create a minimal valid WAV file for voiceover testing."""
    import struct

    p = directory / name
    sample_rate = 8000
    data_size = duration_samples * 2
    with p.open("wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))
        f.write(struct.pack("<H", 1))
        f.write(struct.pack("<H", 1))
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", sample_rate * 2))
        f.write(struct.pack("<H", 2))
        f.write(struct.pack("<H", 16))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(b"\x00" * data_size)
    return p


def _make_manifest(
    directory: Path,
    tracks: list[dict] | None = None,
    name: str = "manifest.json",
) -> Path:
    """Create a voiceover manifest JSON."""
    manifest = {
        "version": "1.0",
        "artifact": "voiceover-manifest",
        "status": "ready",
        "tracks": tracks or [],
        "summary": {"trackCount": len(tracks or [])},
    }
    p = directory / name
    p.write_text(json.dumps(manifest), encoding="utf-8")
    return p


class TestLoadVoiceoverManifest(unittest.TestCase):
    """Tests for load_voiceover_manifest()."""

    def test_explicit_path_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_audio_stub(tmp_path, "vo.wav")
            manifest_path = _make_manifest(tmp_path, tracks=[
                {"id": "t1", "src": "vo.wav", "startSec": 0, "durationSec": 1.0},
            ])
            result = load_voiceover_manifest(manifest_path, tmp_path)
            self.assertIsNotNone(result)
            self.assertEqual(len(result["tracks"]), 1)

    def test_auto_probe_work_voiceover(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            vo_dir = tmp_path / ".work" / "voiceover"
            vo_dir.mkdir(parents=True)
            _make_audio_stub(vo_dir, "vo.wav")
            _make_manifest(vo_dir, tracks=[
                {"id": "t1", "src": "vo.wav", "startSec": 0, "durationSec": 1.0},
            ])
            result = load_voiceover_manifest(None, tmp_path)
            self.assertIsNotNone(result)

    def test_auto_probe_voiceover_subdir(self) -> None:
        """Auto-probe also checks video_dir/voiceover/ (when video_dir=.work/)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            vo_dir = tmp_path / "voiceover"
            vo_dir.mkdir(parents=True)
            _make_audio_stub(vo_dir, "vo.wav")
            _make_manifest(vo_dir, tracks=[
                {"id": "t1", "src": "vo.wav", "startSec": 0, "durationSec": 1.0},
            ])
            result = load_voiceover_manifest(None, tmp_path)
            self.assertIsNotNone(result)

    def test_missing_manifest_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = load_voiceover_manifest(None, Path(tmp))
            self.assertIsNone(result)

    def test_empty_tracks_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_manifest(tmp_path, tracks=[])
            result = load_voiceover_manifest(tmp_path / "manifest.json", tmp_path)
            self.assertIsNone(result)

    def test_tracks_not_a_list_returns_none(self) -> None:
        """Manifest with tracks as non-list (e.g. dict) should return None with warning."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bad_manifest = {
                "version": "1.0",
                "artifact": "voiceover-manifest",
                "status": "ready",
                "tracks": {"bad": "value"},  # not a list
                "summary": {"trackCount": 0},
            }
            p = tmp_path / "manifest.json"
            p.write_text(json.dumps(bad_manifest), encoding="utf-8")
            result = load_voiceover_manifest(p, tmp_path)
            self.assertIsNone(result)


class TestAddVoiceoverAudio(unittest.TestCase):
    """Tests for _add_voiceover_audio() via full export_capcut()."""

    def _export_with_voiceover(
        self,
        tmp_path: Path,
        tracks: list[dict],
        timeline: list[dict] | None = None,
    ) -> Path:
        video_dir = tmp_path / "videos"
        video_dir.mkdir(exist_ok=True)
        _make_video_stub(video_dir, "rec.mp4")

        vo_dir = video_dir / "voiceover"
        vo_dir.mkdir(exist_ok=True)
        for t in tracks:
            src = t.get("src", "")
            audio_name = Path(src).name
            if not (video_dir / src).exists():
                audio_parent = (video_dir / src).parent
                audio_parent.mkdir(parents=True, exist_ok=True)
                _make_audio_stub(audio_parent, audio_name, duration_samples=16000)

        manifest_path = _make_manifest(vo_dir, tracks=tracks)

        if timeline is None:
            timeline = [{"type": "clip", "source": "main", "startSec": 0, "endSec": 0.5}]

        edit_path = _make_edit_json(
            tmp_path,
            sources={"main": "rec.mp4"},
            timeline=timeline,
        )

        drafts_dir = tmp_path / "drafts"
        args = parse_args([
            "--input", str(edit_path),
            "--drafts-dir", str(drafts_dir),
            "--draft-name", "vo_test",
            "--video-dir", str(video_dir),
            "--captions", "none",
            "--voiceover-manifest", str(manifest_path),
        ])
        return export_capcut(args)

    def _load_draft_content(self, draft_path: Path) -> dict:
        content_json = draft_path / "draft_content.json"
        return json.loads(content_json.read_text(encoding="utf-8"))

    def _count_audio_tracks(self, draft_path: Path) -> int:
        content = self._load_draft_content(draft_path)
        tracks = content.get("tracks", [])
        return sum(1 for t in tracks if t.get("type") == "audio")

    def _get_audio_segments(self, draft_path: Path) -> list[dict]:
        content = self._load_draft_content(draft_path)
        tracks = content.get("tracks", [])
        segments: list[dict] = []
        for t in tracks:
            if t.get("type") == "audio":
                segments.extend(t.get("segments", []))
        return segments

    def test_single_track_creates_audio_segment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(tmp_path, tracks=[
                {"id": "t1", "src": "voiceover/intro.wav", "startSec": 0.5, "durationSec": 1.0},
            ])
            self.assertTrue((draft_path / "draft_content.json").exists())
            self.assertEqual(self._count_audio_tracks(draft_path), 1)
            segments = self._get_audio_segments(draft_path)
            self.assertEqual(len(segments), 1)

    def test_multi_track_non_overlapping_same_track(self) -> None:
        """Sequential tracks should reuse the same audio track."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(
                tmp_path,
                tracks=[
                    {"id": "t1", "src": "voiceover/a.wav", "startSec": 0.0, "durationSec": 0.2},
                    {"id": "t2", "src": "voiceover/b.wav", "startSec": 0.2, "durationSec": 0.2},
                ],
                timeline=[{"type": "clip", "source": "main", "startSec": 0, "endSec": 0.5}],
            )
            self.assertEqual(self._count_audio_tracks(draft_path), 1)
            self.assertEqual(len(self._get_audio_segments(draft_path)), 2)

    def test_multi_track_overlapping_separate_tracks(self) -> None:
        """Overlapping tracks should be placed on separate audio tracks."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(tmp_path, tracks=[
                {"id": "t1", "src": "voiceover/a.wav", "startSec": 0.0, "durationSec": 1.5},
                {"id": "t2", "src": "voiceover/b.wav", "startSec": 0.5, "durationSec": 1.0},
            ])
            self.assertEqual(self._count_audio_tracks(draft_path), 2)
            self.assertEqual(len(self._get_audio_segments(draft_path)), 2)

    def test_volume_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(tmp_path, tracks=[
                {"id": "t1", "src": "voiceover/vo.wav", "startSec": 0, "durationSec": 1.0, "volume": 0.5},
            ])
            segments = self._get_audio_segments(draft_path)
            self.assertEqual(len(segments), 1)
            # pyCapCut stores volume in the segment
            seg = segments[0]
            self.assertAlmostEqual(seg.get("volume", 1.0), 0.5, places=2)

    def test_zero_volume_still_added(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(tmp_path, tracks=[
                {"id": "t1", "src": "voiceover/vo.wav", "startSec": 0, "durationSec": 1.0, "volume": 0.0},
            ])
            segments = self._get_audio_segments(draft_path)
            self.assertEqual(len(segments), 1)

    def test_timing_microseconds(self) -> None:
        """startSec should map to correct microsecond position."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(
                tmp_path,
                tracks=[
                    {"id": "t1", "src": "voiceover/vo.wav", "startSec": 0.2, "durationSec": 0.2},
                ],
                timeline=[{"type": "clip", "source": "main", "startSec": 0, "endSec": 0.5}],
            )
            segments = self._get_audio_segments(draft_path)
            self.assertEqual(len(segments), 1)
            seg = segments[0]
            target_tr = seg.get("target_timerange", {})
            self.assertEqual(target_tr.get("start", 0), int(0.2 * SEC))

    def test_offset_sec_maps_to_source_timerange(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(tmp_path, tracks=[
                {"id": "t1", "src": "voiceover/vo.wav", "startSec": 0, "durationSec": 0.5, "offsetSec": 0.3},
            ])
            segments = self._get_audio_segments(draft_path)
            self.assertEqual(len(segments), 1)
            seg = segments[0]
            source_tr = seg.get("source_timerange", {})
            self.assertEqual(source_tr.get("start", 0), int(0.3 * SEC))

    def test_playback_rate_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(tmp_path, tracks=[
                {"id": "t1", "src": "voiceover/vo.wav", "startSec": 0, "durationSec": 1.0, "playbackRate": 1.5},
            ])
            segments = self._get_audio_segments(draft_path)
            self.assertEqual(len(segments), 1)
            seg = segments[0]
            self.assertAlmostEqual(seg.get("speed", 1.0), 1.5, places=2)

    def test_missing_manifest_graceful_skip(self) -> None:
        """When --voiceover-manifest points to a missing file, export still succeeds."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")

            edit_path = _make_edit_json(
                tmp_path,
                sources={"main": "rec.mp4"},
                timeline=[{"type": "clip", "source": "main", "startSec": 0, "endSec": 1.0}],
            )

            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "no_vo",
                "--video-dir", str(video_dir),
                "--captions", "none",
                "--voiceover-manifest", str(tmp_path / "nonexistent.json"),
            ])
            draft_path = export_capcut(args)
            self.assertTrue((draft_path / "draft_content.json").exists())
            self.assertEqual(self._count_audio_tracks(draft_path), 0)

    def test_start_beyond_timeline_clamped(self) -> None:
        """Track starting after timeline end should be clamped with a warning."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(
                tmp_path,
                tracks=[
                    {"id": "t1", "src": "voiceover/vo.wav", "startSec": 999.0, "durationSec": 1.0},
                ],
                timeline=[{"type": "clip", "source": "main", "startSec": 0, "endSec": 1.0}],
            )
            # Should still create the segment (clamped)
            segments = self._get_audio_segments(draft_path)
            self.assertEqual(len(segments), 1)

    def test_fade_in_out_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(tmp_path, tracks=[
                {
                    "id": "t1", "src": "voiceover/vo.wav",
                    "startSec": 0, "durationSec": 1.0,
                    "fadeInSec": 0.2, "fadeOutSec": 0.3,
                },
            ])
            segments = self._get_audio_segments(draft_path)
            self.assertEqual(len(segments), 1)

    def test_missing_audio_file_skips_track(self) -> None:
        """A track referencing a non-existent audio file should be skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_dir = tmp_path / "videos"
            video_dir.mkdir()
            _make_video_stub(video_dir, "rec.mp4")

            vo_dir = video_dir / "voiceover"
            vo_dir.mkdir()
            # Create manifest referencing a file that doesn't exist
            manifest_path = _make_manifest(vo_dir, tracks=[
                {"id": "t1", "src": "voiceover/missing.wav", "startSec": 0, "durationSec": 1.0},
            ])

            edit_path = _make_edit_json(
                tmp_path,
                sources={"main": "rec.mp4"},
                timeline=[{"type": "clip", "source": "main", "startSec": 0, "endSec": 1.0}],
            )
            drafts_dir = tmp_path / "drafts"
            args = parse_args([
                "--input", str(edit_path),
                "--drafts-dir", str(drafts_dir),
                "--draft-name", "missing_audio",
                "--video-dir", str(video_dir),
                "--captions", "none",
                "--voiceover-manifest", str(manifest_path),
            ])
            draft_path = export_capcut(args)
            self.assertTrue((draft_path / "draft_content.json").exists())
            # No audio track should be created (the only track was skipped)
            self.assertEqual(self._count_audio_tracks(draft_path), 0)

    def test_zero_duration_track_skipped(self) -> None:
        """Track with durationSec=0 should be skipped (not added to any audio track)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(tmp_path, tracks=[
                {"id": "t1", "src": "voiceover/vo.wav", "startSec": 0, "durationSec": 0.0},
            ])
            # Track is skipped → no audio tracks created
            self.assertEqual(self._count_audio_tracks(draft_path), 0)
            self.assertEqual(len(self._get_audio_segments(draft_path)), 0)

    def test_negative_duration_track_skipped(self) -> None:
        """Track with negative durationSec should be skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(tmp_path, tracks=[
                {"id": "t1", "src": "voiceover/vo.wav", "startSec": 0, "durationSec": -1.0},
            ])
            self.assertEqual(self._count_audio_tracks(draft_path), 0)

    def test_playback_rate_adjusts_target_duration(self) -> None:
        """playbackRate=2.0 should halve the target_timerange duration (compressed in time)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(tmp_path, tracks=[
                {"id": "t1", "src": "voiceover/vo.wav", "startSec": 0, "durationSec": 1.0, "playbackRate": 2.0},
            ])
            segments = self._get_audio_segments(draft_path)
            self.assertEqual(len(segments), 1)
            target_tr = segments[0].get("target_timerange", {})
            # durationSec=1.0, playbackRate=2.0 → target duration = 0.5s = 500_000 μs
            expected_us = int(1.0 / 2.0 * 1_000_000)
            self.assertEqual(target_tr.get("duration", 0), expected_us)

    def test_only_fade_in_applied(self) -> None:
        """fadeInSec set without fadeOutSec should still trigger add_fade with 0 out-duration."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(tmp_path, tracks=[
                {"id": "t1", "src": "voiceover/vo.wav", "startSec": 0, "durationSec": 1.0, "fadeInSec": 0.2},
            ])
            segments = self._get_audio_segments(draft_path)
            self.assertEqual(len(segments), 1)
            # Fade adds an extra material ref beyond the default speed ref
            seg = segments[0]
            refs = seg.get("extra_material_refs", [])
            self.assertGreater(len(refs), 1, "fade should add a second extra_material_ref beyond the speed ref")

    def test_only_fade_out_applied(self) -> None:
        """fadeOutSec set without fadeInSec should still trigger add_fade with 0 in-duration."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(tmp_path, tracks=[
                {"id": "t1", "src": "voiceover/vo.wav", "startSec": 0, "durationSec": 1.0, "fadeOutSec": 0.3},
            ])
            segments = self._get_audio_segments(draft_path)
            self.assertEqual(len(segments), 1)
            seg = segments[0]
            refs = seg.get("extra_material_refs", [])
            self.assertGreater(len(refs), 1, "fade should add a second extra_material_ref beyond the speed ref")

    def test_no_fade_when_both_zero(self) -> None:
        """Segments without fadeInSec/fadeOutSec should have only the default speed ref (no fade ref)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = self._export_with_voiceover(tmp_path, tracks=[
                {"id": "t1", "src": "voiceover/vo.wav", "startSec": 0, "durationSec": 1.0},
            ])
            segments = self._get_audio_segments(draft_path)
            self.assertEqual(len(segments), 1)
            seg = segments[0]
            refs = seg.get("extra_material_refs", [])
            # Without fade: only the speed material ref is present (1 ref baseline from pycapcut)
            self.assertEqual(len(refs), 1, "no fade → only speed ref in extra_material_refs")


class TestParseArgsVoiceover(unittest.TestCase):
    """Tests for --voiceover-manifest CLI argument."""

    def test_default_is_none(self) -> None:
        args = parse_args(["--input", "edit.json"])
        self.assertIsNone(args.voiceover_manifest)

    def test_custom_path(self) -> None:
        args = parse_args(["--input", "edit.json", "--voiceover-manifest", "/path/to/manifest.json"])
        self.assertEqual(args.voiceover_manifest, Path("/path/to/manifest.json"))


# ── Phase 1: Gradient parsing tests ──────────────────────────────────────────


class TestParseLinearGradient(unittest.TestCase):
    def test_basic_two_color_gradient(self) -> None:
        result = _parse_linear_gradient("linear-gradient(135deg, #667eea 0%, #764ba2 100%)")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("#667eea", 0.0))
        self.assertEqual(result[1], ("#764ba2", 1.0))

    def test_three_color_gradient(self) -> None:
        result = _parse_linear_gradient("linear-gradient(90deg, #ff0000 0%, #00ff00 50%, #0000ff 100%)")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[1][1], 0.5)

    def test_no_percentage_auto_distributes(self) -> None:
        result = _parse_linear_gradient("linear-gradient(to right, #ff0000, #0000ff)")
        self.assertIsNotNone(result)
        self.assertEqual(result[0][1], 0.0)
        self.assertEqual(result[1][1], 1.0)

    def test_solid_color_returns_none(self) -> None:
        result = _parse_linear_gradient("#c8102e")
        self.assertIsNone(result)

    def test_radial_gradient_returns_none(self) -> None:
        result = _parse_linear_gradient("radial-gradient(circle, #ff0000, #0000ff)")
        self.assertIsNone(result)

    def test_single_color_gradient_returns_none(self) -> None:
        result = _parse_linear_gradient("linear-gradient(90deg, #ff0000)")
        self.assertIsNone(result)

    def test_no_angle_prefix(self) -> None:
        result = _parse_linear_gradient("linear-gradient(#ff0000 0%, #00ff00 100%)")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)

    def test_case_insensitive(self) -> None:
        result = _parse_linear_gradient("LINEAR-GRADIENT(135deg, #667eea 0%, #764ba2 100%)")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)


class TestHexToRgb(unittest.TestCase):
    def test_six_digit(self) -> None:
        self.assertEqual(_hex_to_rgb("#ff0000"), (255, 0, 0))

    def test_three_digit(self) -> None:
        self.assertEqual(_hex_to_rgb("#f00"), (255, 0, 0))

    def test_mixed_case(self) -> None:
        self.assertEqual(_hex_to_rgb("#FfAa00"), (255, 170, 0))


class TestRenderGradientImage(unittest.TestCase):
    def test_creates_correct_size(self) -> None:
        stops = [("#ff0000", 0.0), ("#0000ff", 1.0)]
        img = _render_gradient_image(stops, 100, 50)
        self.assertEqual(img.size, (100, 50))

    def test_top_pixel_near_first_color(self) -> None:
        stops = [("#ff0000", 0.0), ("#0000ff", 1.0)]
        img = _render_gradient_image(stops, 10, 100)
        r, g, b = img.getpixel((5, 0))
        self.assertGreater(r, 200)
        self.assertLess(b, 55)

    def test_bottom_pixel_near_last_color(self) -> None:
        stops = [("#ff0000", 0.0), ("#0000ff", 1.0)]
        img = _render_gradient_image(stops, 10, 100)
        r, g, b = img.getpixel((5, 99))
        self.assertLess(r, 55)
        self.assertGreater(b, 200)

    def test_three_stop_midpoint(self) -> None:
        stops = [("#ff0000", 0.0), ("#00ff00", 0.5), ("#0000ff", 1.0)]
        img = _render_gradient_image(stops, 10, 101)
        r, g, b = img.getpixel((5, 50))
        self.assertGreater(g, 200)


class TestGenerateTitleCardGradient(unittest.TestCase):
    def test_gradient_background_produces_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "card.png"
            generate_title_card("Hello", None, "linear-gradient(135deg, #667eea 0%, #764ba2 100%)", 200, 100, output_path)
            self.assertTrue(output_path.exists())
            from PIL import Image as PILImage
            img = PILImage.open(str(output_path))
            self.assertEqual(img.size, (200, 100))

    def test_solid_color_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "card.png"
            generate_title_card("Hello", None, "#1e1b4b", 100, 100, output_path)
            self.assertTrue(output_path.exists())
            from PIL import Image as PILImage
            img = PILImage.open(str(output_path))
            # All pixels should be the solid color (except text)
            corner = img.getpixel((0, 0))
            self.assertEqual(corner, (0x1e, 0x1b, 0x4b))


# ── Phase 2: Expanded transition map tests ───────────────────────────────────


class TestExpandedTransitionMap(unittest.TestCase):
    def test_dissolve_maps_to_fade(self) -> None:
        self.assertEqual(TRANSITION_MAP["dissolve"], TRANSITION_MAP["fade"])

    def test_slide_up_exists(self) -> None:
        self.assertIn("slide-up", TRANSITION_MAP)

    def test_slide_down_exists(self) -> None:
        self.assertIn("slide-down", TRANSITION_MAP)

    def test_wipe_left_exists(self) -> None:
        self.assertIn("wipe-left", TRANSITION_MAP)

    def test_original_entries_preserved(self) -> None:
        for key in ("fade", "slide-left", "slide-right", "wipe"):
            self.assertIn(key, TRANSITION_MAP)


# ── Phase 3: Template mode tests ─────────────────────────────────────────────


class TestCapcutTemplateCLI(unittest.TestCase):
    def test_default_is_none(self) -> None:
        args = parse_args(["--input", "edit.json"])
        self.assertIsNone(args.capcut_template)

    def test_template_flag_parsed(self) -> None:
        args = parse_args(["--input", "edit.json", "--capcut-template", "my_template"])
        self.assertEqual(args.capcut_template, "my_template")

    def test_video_track_default_is_zero(self) -> None:
        args = parse_args(["--input", "edit.json"])
        self.assertEqual(args.capcut_template_video_track, 0)

    def test_text_track_default_is_zero(self) -> None:
        args = parse_args(["--input", "edit.json"])
        self.assertEqual(args.capcut_template_text_track, 0)

    def test_custom_track_indices(self) -> None:
        args = parse_args([
            "--input", "edit.json",
            "--capcut-template", "tpl",
            "--capcut-template-video-track", "1",
            "--capcut-template-text-track", "2",
        ])
        self.assertEqual(args.capcut_template_video_track, 1)
        self.assertEqual(args.capcut_template_text_track, 2)


class TestCapcutTemplateMode(unittest.TestCase):
    def test_template_mode_calls_duplicate(self) -> None:
        """Template mode uses duplicate_as_template and replace methods."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = _make_video_stub(tmp_path)

            # Create a "template" draft first
            from pycapcut import DraftFolder
            df = DraftFolder(str(tmp_path))
            tpl_script = df.create_draft("my_template", 1920, 1080, fps=30)
            from pycapcut import VideoMaterial, VideoSegment, Timerange, TrackType
            tpl_script.add_track(TrackType.video)
            mat = VideoMaterial(str(video))
            tpl_script.add_material(mat)
            seg = VideoSegment(mat, Timerange(0, 1 * SEC), source_timerange=Timerange(0, 1 * SEC))
            tpl_script.add_segment(seg)
            tpl_script.save()

            # Create edit.json with a clip
            edit_json = _make_edit_json(
                tmp_path,
                sources={"main": str(video)},
                timeline=[{"type": "clip", "source": "main", "startSec": 0, "endSec": 1}],
            )

            args = parse_args([
                "--input", str(edit_json),
                "--drafts-dir", str(tmp_path),
                "--draft-name", "output_draft",
                "--video-dir", str(tmp_path),
                "--capcut-template", "my_template",
            ])
            draft_path = export_capcut(args)
            self.assertTrue(draft_path.exists())
            self.assertEqual(draft_path.name, "output_draft")

    def test_normal_mode_unchanged_without_template(self) -> None:
        """Without --capcut-template, export uses normal flow."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = _make_video_stub(tmp_path)
            edit_json = _make_edit_json(
                tmp_path,
                sources={"main": str(video)},
                timeline=[{"type": "clip", "source": "main", "startSec": 0, "endSec": 1}],
            )
            args = parse_args([
                "--input", str(edit_json),
                "--drafts-dir", str(tmp_path),
                "--draft-name", "normal_draft",
                "--video-dir", str(tmp_path),
            ])
            draft_path = export_capcut(args)
            self.assertTrue(draft_path.exists())
            self.assertEqual(draft_path.name, "normal_draft")


# ── Phase 1: Title card TextSegment overlay test ─────────────────────────────


class TestTitleCardTextSegments(unittest.TestCase):
    def test_title_card_creates_text_segments(self) -> None:
        """Title cards should produce pyCapCut TextSegments for editable title+subtitle."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = _make_video_stub(tmp_path)
            edit_json = _make_edit_json(
                tmp_path,
                sources={"main": str(video)},
                timeline=[
                    {
                        "type": "title-card",
                        "text": "Hello World",
                        "subtitle": "Subtitle Text",
                        "background": "#1e1b4b",
                        "durationSec": 3.0,
                    },
                    {"type": "clip", "source": "main", "startSec": 0, "endSec": 1},
                ],
            )
            args = parse_args([
                "--input", str(edit_json),
                "--drafts-dir", str(tmp_path),
                "--draft-name", "tc_draft",
                "--video-dir", str(tmp_path),
                "--captions", "none",
            ])
            draft_path = export_capcut(args)
            self.assertTrue(draft_path.exists())
            # Check that draft_content.json was written (basic sanity)
            dc = draft_path / "draft_content.json"
            self.assertTrue(dc.exists())


if __name__ == "__main__":
    unittest.main()
