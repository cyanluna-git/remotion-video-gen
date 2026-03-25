"""Provider-agnostic TTS backends for voiceover generation."""

from __future__ import annotations

import math
import os
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class TtsProviderError(RuntimeError):
    """Raised when a TTS provider cannot synthesize audio."""


@dataclass(frozen=True)
class TtsRequest:
    """Single narration synthesis request."""

    text: str
    output_path: Path
    language: str = "auto"
    label: str = ""


@dataclass(frozen=True)
class TtsProviderConfig:
    """Normalized provider configuration."""

    name: str
    model: str
    voice: str
    audio_format: str = "wav"
    instructions: str = ""


class BaseTtsProvider:
    """Abstract TTS provider."""

    def __init__(self, config: TtsProviderConfig) -> None:
        self.config = config

    @property
    def file_extension(self) -> str:
        return self.config.audio_format.lower()

    def synthesize(self, request: TtsRequest) -> dict[str, Any]:
        raise NotImplementedError


class MockTtsProvider(BaseTtsProvider):
    """Deterministic local provider used for tests and dry-runs."""

    SAMPLE_RATE = 24_000

    def synthesize(self, request: TtsRequest) -> dict[str, Any]:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        duration_sec = estimate_mock_duration(request.text)
        frame_count = max(int(self.SAMPLE_RATE * duration_sec), 1)
        amplitude = 11_000

        with wave.open(str(request.output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.SAMPLE_RATE)

            for index in range(frame_count):
                envelope = min(index / (self.SAMPLE_RATE * 0.1), 1.0)
                sample = int(
                    amplitude
                    * envelope
                    * math.sin(2.0 * math.pi * 440.0 * index / self.SAMPLE_RATE)
                )
                wav_file.writeframesraw(struct.pack("<h", sample))

        return {
            "durationSec": round(duration_sec, 3),
            "provider": {
                "name": self.config.name,
                "model": self.config.model,
                "voice": self.config.voice,
            },
        }


class OpenAITtsProvider(BaseTtsProvider):
    """OpenAI audio speech provider."""

    def synthesize(self, request: TtsRequest) -> dict[str, Any]:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise TtsProviderError("OPENAI_API_KEY is required for the openai TTS provider.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise TtsProviderError(
                "The openai package is not installed. Run `pip install -r requirements.txt`."
            ) from exc

        client = OpenAI(api_key=api_key)
        request.output_path.parent.mkdir(parents=True, exist_ok=True)

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "voice": self.config.voice,
            "input": request.text,
            "response_format": self.config.audio_format,
        }
        if self.config.instructions:
            kwargs["instructions"] = self.config.instructions

        try:
            with client.audio.speech.with_streaming_response.create(**kwargs) as response:
                response.stream_to_file(str(request.output_path))
        except AttributeError:
            response = client.audio.speech.create(**kwargs)
            write_audio_response(response, request.output_path)

        duration_sec = probe_audio_duration(request.output_path)
        return {
            "durationSec": round(duration_sec, 3) if duration_sec is not None else None,
            "provider": {
                "name": self.config.name,
                "model": self.config.model,
                "voice": self.config.voice,
            },
        }


class EdgeTtsProvider(BaseTtsProvider):
    """Free Microsoft Edge TTS provider via edge-tts package."""

    def synthesize(self, request: TtsRequest) -> dict[str, Any]:
        try:
            import edge_tts
        except ImportError as exc:
            raise TtsProviderError(
                "The edge-tts package is not installed. Run `pip install edge-tts`."
            ) from exc

        import asyncio

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        voice = self.config.voice

        async def _synthesize() -> None:
            communicate = edge_tts.Communicate(request.text, voice)
            await communicate.save(str(request.output_path))

        asyncio.run(_synthesize())

        duration_sec = probe_audio_duration(request.output_path)
        return {
            "durationSec": round(duration_sec, 3) if duration_sec is not None else None,
            "provider": {
                "name": self.config.name,
                "model": self.config.model,
                "voice": self.config.voice,
            },
        }


def build_tts_provider(
    provider_name: str,
    *,
    model: str,
    voice: str,
    audio_format: str,
    instructions: str = "",
) -> BaseTtsProvider:
    """Construct a provider instance from normalized config."""
    config = TtsProviderConfig(
        name=provider_name.strip().lower(),
        model=model.strip(),
        voice=voice.strip(),
        audio_format=audio_format.strip().lower(),
        instructions=instructions.strip(),
    )
    if config.name == "mock":
        if config.audio_format != "wav":
            raise TtsProviderError("mock provider only supports wav output.")
        return MockTtsProvider(config)
    if config.name == "openai":
        return OpenAITtsProvider(config)
    if config.name == "edge":
        return EdgeTtsProvider(config)
    raise TtsProviderError(f"Unsupported TTS provider: {provider_name}")


def estimate_mock_duration(text: str) -> float:
    """Estimate a deterministic mock narration length from text."""
    word_count = max(len(text.split()), 1)
    char_count = len(text.strip())
    return max(1.0, min(12.0, 0.3 * word_count + 0.018 * char_count))


def probe_audio_duration(audio_path: Path) -> float | None:
    """Get audio duration in seconds via ffprobe when available."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def write_audio_response(response: Any, output_path: Path) -> None:
    """Persist OpenAI SDK responses across a few response shapes."""
    if hasattr(response, "stream_to_file"):
        response.stream_to_file(str(output_path))
        return

    if hasattr(response, "read"):
        data = response.read()
    elif isinstance(response, (bytes, bytearray)):
        data = bytes(response)
    elif hasattr(response, "content") and isinstance(response.content, (bytes, bytearray)):
        data = bytes(response.content)
    else:
        raise TtsProviderError("Unsupported OpenAI TTS response object.")

    output_path.write_bytes(data)
