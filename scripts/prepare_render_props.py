"""Wrap edit props for Remotion and rewrite local audio assets to public paths."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare render props and copy local audio assets into Remotion public/.",
    )
    parser.add_argument("--edit-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-dir", type=Path, required=True)
    return parser.parse_args(argv)


def load_edit(edit_source: Path) -> dict[str, Any]:
    with edit_source.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if "script" in payload and isinstance(payload.get("script"), dict):
        return payload["script"]
    return payload


def rewrite_audio_assets(
    script: dict[str, Any],
    *,
    edit_source: Path,
    public_dir: Path,
) -> dict[str, Any]:
    audio = script.get("audio")
    if not isinstance(audio, dict):
        return script

    asset_scope = edit_source.parent.name or "default"
    voiceover = audio.get("voiceover")
    if isinstance(voiceover, dict) and isinstance(voiceover.get("tracks"), list):
        for track in voiceover["tracks"]:
            if isinstance(track, dict):
                track["src"] = rewrite_single_audio_src(
                    track.get("src"),
                    edit_source=edit_source,
                    public_dir=public_dir,
                    asset_scope=asset_scope,
                )
    elif isinstance(voiceover, dict) and voiceover.get("src"):
        voiceover["src"] = rewrite_single_audio_src(
            voiceover.get("src"),
            edit_source=edit_source,
            public_dir=public_dir,
            asset_scope=asset_scope,
        )

    background_music = audio.get("backgroundMusic")
    if isinstance(background_music, dict) and background_music.get("src"):
        background_music["src"] = rewrite_single_audio_src(
            background_music.get("src"),
            edit_source=edit_source,
            public_dir=public_dir,
            asset_scope=asset_scope,
        )

    return script


def rewrite_single_audio_src(
    raw_src: Any,
    *,
    edit_source: Path,
    public_dir: Path,
    asset_scope: str,
) -> Any:
    if not isinstance(raw_src, str) or not raw_src:
        return raw_src
    if raw_src.startswith("http://") or raw_src.startswith("https://"):
        return raw_src

    candidate = Path(raw_src)
    if not candidate.is_absolute():
        candidate = (edit_source.parent / raw_src).resolve()

    if not candidate.exists() or not candidate.is_file():
        return raw_src

    dest_dir = public_dir / "voiceover" / asset_scope
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / candidate.name
    if candidate.resolve() != dest_path.resolve():
        shutil.copy2(candidate, dest_path)

    return f"voiceover/{asset_scope}/{candidate.name}"


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    script = load_edit(args.edit_source)
    script = rewrite_audio_assets(
        script,
        edit_source=args.edit_source.resolve(),
        public_dir=args.public_dir.resolve(),
    )

    wrapped = {"script": script}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(wrapped, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
