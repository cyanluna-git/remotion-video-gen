"""Whisper large-v3-turbo transcription wrapper.

Transcribes audio from video/audio files using OpenAI Whisper,
outputting word-level timestamps as JSON.

Usage:
    python scripts/transcribe.py input.mp4
    python scripts/transcribe.py input.wav --output .work/transcript.json
    python scripts/transcribe.py input.mp4 --model large-v3-turbo --language ko
"""

from __future__ import annotations

import argparse
import json
import ssl

# Workaround for SSL certificate issues during model download
ssl._create_default_https_context = ssl._create_unverified_context
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Transcribe audio from video/audio files using OpenAI Whisper.",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Input file path (MP4 or WAV)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".work/transcript.json"),
        help="Output JSON path (default: .work/transcript.json)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="large-v3-turbo",
        help="Whisper model name (default: large-v3-turbo)",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="auto",
        help="Language code or 'auto' for auto-detect (default: auto)",
    )
    return parser.parse_args(argv)


def extract_audio_to_wav(input_path: Path, output_wav: Path) -> None:
    """Extract audio from a video file to 16kHz mono WAV using ffmpeg."""
    if not shutil.which("ffmpeg"):
        print("Error: ffmpeg is not installed or not found in PATH.", file=sys.stderr)
        print("Install it via: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)", file=sys.stderr)
        sys.exit(1)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output_wav),
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error: ffmpeg failed to extract audio from {input_path}", file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        sys.exit(1)


def load_whisper_model(model_name: str) -> "whisper.Whisper":
    """Load the Whisper model, handling import and download errors."""
    try:
        import whisper
    except ImportError:
        print("Error: openai-whisper is not installed.", file=sys.stderr)
        print("Install it via: pip install openai-whisper", file=sys.stderr)
        sys.exit(1)

    print(f"Loading Whisper model '{model_name}'...")
    try:
        model = whisper.load_model(model_name)
    except Exception as e:
        print(f"Error: Failed to load Whisper model '{model_name}': {e}", file=sys.stderr)
        sys.exit(1)

    return model


def transcribe_audio(model: "whisper.Whisper", audio_path: Path, language: str) -> dict:
    """Run Whisper transcription with word-level timestamps."""
    lang = None if language == "auto" else language

    print(f"Transcribing '{audio_path}'...")
    start_time = time.time()

    result = model.transcribe(
        str(audio_path),
        language=lang,
        word_timestamps=True,
        task="transcribe",
    )

    elapsed = time.time() - start_time
    print(f"Transcription completed in {elapsed:.1f}s")

    return result


def save_result(result: dict, output_path: Path) -> None:
    """Save the Whisper transcription result as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved transcript to {output_path}")


def print_summary(result: dict, model_name: str) -> None:
    """Print a summary of the transcription result."""
    language = result.get("language", "unknown")
    segments = result.get("segments", [])
    num_segments = len(segments)

    total_duration = 0.0
    if segments:
        total_duration = segments[-1].get("end", 0.0)

    minutes = int(total_duration // 60)
    seconds = total_duration % 60

    print("\n--- Transcription Summary ---")
    print(f"  Model:       {model_name}")
    print(f"  Language:     {language}")
    print(f"  Segments:     {num_segments}")
    print(f"  Duration:     {minutes}m {seconds:.1f}s")
    print("-----------------------------")


def main(argv: Optional[list[str]] = None) -> None:
    """Main entry point for the transcription CLI."""
    args = parse_args(argv)

    input_path: Path = args.input
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    suffix = input_path.suffix.lower()
    temp_wav: Optional[Path] = None

    try:
        if suffix in (".mp4", ".mkv", ".mov", ".avi", ".webm"):
            temp_dir = Path(tempfile.mkdtemp(prefix="whisper_"))
            temp_wav = temp_dir / "audio.wav"
            print(f"Extracting audio from {input_path}...")
            extract_audio_to_wav(input_path, temp_wav)
            audio_path = temp_wav
        elif suffix in (".wav", ".flac", ".mp3", ".ogg", ".m4a"):
            audio_path = input_path
        else:
            print(f"Error: Unsupported file format '{suffix}'.", file=sys.stderr)
            print("Supported: .mp4, .mkv, .mov, .avi, .webm, .wav, .flac, .mp3, .ogg, .m4a", file=sys.stderr)
            sys.exit(1)

        model = load_whisper_model(args.model)
        result = transcribe_audio(model, audio_path, args.language)
        save_result(result, args.output)
        print_summary(result, args.model)

    finally:
        if temp_wav is not None and temp_wav.exists():
            temp_dir = temp_wav.parent
            temp_wav.unlink(missing_ok=True)
            try:
                temp_dir.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    main()
