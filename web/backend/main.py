"""FastAPI backend that wraps pipeline.sh for video generation jobs."""

import asyncio
import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
JOBS_DIR = PROJECT_ROOT / "jobs"
PIPELINE_SH = PROJECT_ROOT / "pipeline.sh"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from scenario_contract import ScenarioContractError, normalize_scenario
from scenario_generation import derive_title

JOBS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Remotion Video Gen API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3010", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_meta(meta_path: Path) -> dict:
    """Load meta.json from disk."""
    with meta_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_meta(meta_path: Path, meta: dict) -> None:
    """Atomically write meta.json."""
    tmp = meta_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    tmp.replace(meta_path)


def utcnow_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def voiceover_summary(edit: dict | None) -> tuple[bool, int]:
    """Return whether edit JSON references voiceover and the track count."""
    if not isinstance(edit, dict):
        return False, 0

    audio = edit.get("audio")
    if not isinstance(audio, dict):
        return False, 0

    voiceover = audio.get("voiceover")
    if not isinstance(voiceover, dict):
        return False, 0

    if isinstance(voiceover.get("tracks"), list):
        return True, len(voiceover["tracks"])
    if isinstance(voiceover.get("src"), str) and voiceover["src"].strip():
        return True, 1
    return False, 0


def job_summary(job_dir: Path) -> Optional[dict]:
    """Build a lightweight summary dict from a job directory."""
    meta_path = job_dir / "meta.json"
    if not meta_path.exists():
        return None
    try:
        meta = load_meta(meta_path)
    except (json.JSONDecodeError, OSError):
        return None
    return {
        "id": meta.get("id", job_dir.name),
        "title": meta.get("title", ""),
        "status": meta.get("status", "unknown"),
        "inputMode": meta.get("inputMode", "manual"),
        "createdAt": meta.get("createdAt"),
        "completedAt": meta.get("completedAt"),
        "duration": meta.get("duration"),
        "fileSize": meta.get("fileSize", 0),
    }


# ---------------------------------------------------------------------------
# Background pipeline runner
# ---------------------------------------------------------------------------


async def run_pipeline(job_id: str, job_dir: Path, edit_only: bool = False) -> None:
    """Run pipeline.sh in background, updating meta.json with progress."""
    meta_path = job_dir / "meta.json"

    meta = load_meta(meta_path)
    meta["status"] = "running"
    meta["startedAt"] = utcnow_iso()
    save_meta(meta_path, meta)

    input_video = job_dir / "input.mp4"
    scenario = job_dir / "scenario.json"
    edit_path = job_dir / "edit.json"
    scenario_prompt = job_dir / "scenario.prompt.txt"
    scenario_error = job_dir / "scenario.error.txt"
    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "final.mp4"

    cmd = [str(PIPELINE_SH), str(input_video)]

    if meta.get("inputMode") == "auto":
        cmd.extend(
            [
                "--auto-scenario",
                "--scenario-output",
                str(scenario),
                "--prompt-output",
                str(scenario_prompt),
                "--scenario-error-output",
                str(scenario_error),
            ]
        )
        title_hint = str(meta.get("titleHint") or "").strip()
        language_hint = str(meta.get("languageHint") or "").strip()
        if title_hint:
            cmd.extend(["--title", title_hint])
        if language_hint:
            cmd.extend(["--language", language_hint])
    else:
        cmd.append(str(scenario))

    cmd.extend(
        [
            "--edit-output",
            str(edit_path),
            "--output",
            str(output),
        ]
    )

    if edit_only:
        cmd.append("--edit-only")

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(PROJECT_ROOT),
    )

    log_lines: list[str] = []
    current_step = 0

    assert process.stdout is not None
    async for line in process.stdout:
        text = line.decode(errors="replace").strip()
        log_lines.append(text)

        if "Step 1:" in text:
            current_step = 1
        elif "Step 2:" in text:
            current_step = 2
        elif "Step 3:" in text:
            current_step = 3
        elif "Step 4:" in text:
            current_step = 4
        elif "Step 5:" in text:
            current_step = 5

        meta["currentStep"] = current_step
        meta["log"] = "\n".join(log_lines[-50:])
        save_meta(meta_path, meta)

    await process.wait()

    meta["completedAt"] = utcnow_iso()
    meta["log"] = "\n".join(log_lines)

    if process.returncode == 0 and output.exists():
        meta["status"] = "done"
        meta["fileSize"] = output.stat().st_size

        # Calculate duration
        if meta.get("startedAt") and meta.get("completedAt"):
            try:
                start_dt = datetime.fromisoformat(
                    meta["startedAt"].replace("Z", "+00:00")
                )
                end_dt = datetime.fromisoformat(
                    meta["completedAt"].replace("Z", "+00:00")
                )
                meta["duration"] = (end_dt - start_dt).total_seconds()
            except (ValueError, TypeError):
                pass

        # Generate thumbnail from first frame
        thumb = output_dir / "thumbnail.jpg"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(output),
                "-vframes",
                "1",
                "-q:v",
                "5",
                "-vf",
                "scale=480:-1",
                str(thumb),
            ],
            capture_output=True,
        )
    else:
        meta["status"] = "failed"

    save_meta(meta_path, meta)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.post("/api/jobs")
async def create_job(
    video: UploadFile = File(...),
    scenario: str | None = Form(None),
    auto_scenario: bool = Form(False, alias="autoScenario"),
    title: str | None = Form(None),
    language: str | None = Form(None),
) -> JSONResponse:
    """Accept a video with either manual scenario JSON or auto-scenario hints."""
    job_id = str(uuid.uuid4())
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded video
    input_path = job_dir / "input.mp4"
    with input_path.open("wb") as f:
        while chunk := await video.read(1024 * 1024):
            f.write(chunk)

    if auto_scenario and scenario:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail="Provide either manual scenario JSON or autoScenario=true, not both.",
        )
    if not auto_scenario and not scenario:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail="Manual mode requires scenario JSON. Use autoScenario=true for AI-assisted submission.",
        )

    title_hint = (title or "").strip()
    language_hint = (language or "").strip()
    resolved_title = ""

    if auto_scenario:
        resolved_title = derive_title(title_hint or None, video.filename)
    else:
        try:
            scenario_data = json.loads(scenario or "")
        except json.JSONDecodeError as exc:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=f"Invalid scenario JSON: {exc}")
        try:
            scenario_data = normalize_scenario(scenario_data)
        except ScenarioContractError as exc:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=str(exc))

        scenario_path = job_dir / "scenario.json"
        with scenario_path.open("w", encoding="utf-8") as f:
            json.dump(scenario_data, f, indent=2, ensure_ascii=False)

        resolved_title = scenario_data.get("title", scenario_data.get("name", "Untitled"))

    meta = {
        "id": job_id,
        "title": resolved_title,
        "inputMode": "auto" if auto_scenario else "manual",
        "titleHint": title_hint or None,
        "languageHint": language_hint or None,
        "status": "queued",
        "currentStep": 0,
        "createdAt": utcnow_iso(),
        "startedAt": None,
        "completedAt": None,
        "fileSize": 0,
        "duration": None,
        "log": "",
    }
    save_meta(job_dir / "meta.json", meta)

    # Launch pipeline in background
    asyncio.create_task(run_pipeline(job_id, job_dir))

    return JSONResponse(
        status_code=201,
        content={"id": job_id, "status": "queued"},
    )


@app.get("/api/jobs")
async def list_jobs() -> list[dict]:
    """Return all jobs sorted by createdAt (newest first)."""
    if not JOBS_DIR.exists():
        return []

    summaries: list[dict] = []
    for child in JOBS_DIR.iterdir():
        if not child.is_dir():
            continue
        summary = job_summary(child)
        if summary is not None:
            summaries.append(summary)

    summaries.sort(key=lambda s: s.get("createdAt") or "", reverse=True)
    return summaries


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    """Return full job details."""
    job_dir = JOBS_DIR / job_id
    meta_path = job_dir / "meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    meta = load_meta(meta_path)

    # Enrich with output file info
    output = job_dir / "output" / "final.mp4"
    meta["hasVideo"] = output.exists()

    thumb = job_dir / "output" / "thumbnail.jpg"
    meta["hasThumbnail"] = thumb.exists()

    edit_path = job_dir / "output" / "edit.json"
    if not edit_path.exists():
        edit_path = job_dir / "edit.json"
    meta["hasEdit"] = edit_path.exists()
    scenario_path = job_dir / "scenario.json"
    meta["hasScenario"] = scenario_path.exists()
    voiceover_dir = job_dir / "voiceover"
    meta["hasVoiceoverArtifacts"] = voiceover_dir.exists()
    meta["hasVoiceover"] = False
    meta["voiceoverTrackCount"] = 0

    if edit_path.exists():
        try:
            with edit_path.open("r", encoding="utf-8") as f:
                edit_data = json.load(f)
            has_voiceover, track_count = voiceover_summary(edit_data)
            meta["hasVoiceover"] = has_voiceover
            meta["voiceoverTrackCount"] = track_count
        except (json.JSONDecodeError, OSError):
            pass

    # Include scenario if available
    if scenario_path.exists():
        try:
            with scenario_path.open("r", encoding="utf-8") as f:
                meta["scenario"] = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    if voiceover_dir.exists():
        meta["voiceoverArtifacts"] = sorted(
            path.name for path in voiceover_dir.iterdir() if path.is_file()
        )

    return meta


@app.get("/api/jobs/{job_id}/video")
async def get_video(job_id: str) -> FileResponse:
    """Stream the final rendered video."""
    output = JOBS_DIR / job_id / "output" / "final.mp4"
    if not output.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    return FileResponse(
        path=str(output),
        media_type="video/mp4",
        filename=f"{job_id}.mp4",
    )


@app.get("/api/jobs/{job_id}/thumbnail")
async def get_thumbnail(job_id: str) -> FileResponse:
    """Return thumbnail image, generating it on the fly if missing."""
    job_dir = JOBS_DIR / job_id
    thumb = job_dir / "output" / "thumbnail.jpg"
    output = job_dir / "output" / "final.mp4"

    if not thumb.exists() and output.exists():
        thumb.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(output),
                "-vframes",
                "1",
                "-q:v",
                "5",
                "-vf",
                "scale=480:-1",
                str(thumb),
            ],
            capture_output=True,
        )

    if not thumb.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not available")

    return FileResponse(
        path=str(thumb),
        media_type="image/jpeg",
        filename=f"{job_id}_thumb.jpg",
    )


@app.get("/api/jobs/{job_id}/edit")
async def get_edit(job_id: str) -> dict:
    """Return the edit.json content."""
    job_dir = JOBS_DIR / job_id

    # Check multiple possible locations
    candidates = [
        job_dir / "output" / "edit.json",
        job_dir / "edit.json",
    ]

    for path in candidates:
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

    raise HTTPException(status_code=404, detail="Edit JSON not found")


@app.put("/api/jobs/{job_id}/edit")
async def update_edit(job_id: str, payload: dict) -> dict:
    """Save a modified edit.json and return the updated content."""
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    edit_path = job_dir / "edit.json"

    with edit_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return payload


@app.post("/api/jobs/{job_id}/rerender")
async def rerender_job(job_id: str) -> dict:
    """Re-run pipeline with --edit-only flag."""
    job_dir = JOBS_DIR / job_id
    meta_path = job_dir / "meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    meta = load_meta(meta_path)
    meta["status"] = "queued"
    meta["currentStep"] = 0
    meta["completedAt"] = None
    meta["duration"] = None
    meta["log"] = ""
    save_meta(meta_path, meta)

    asyncio.create_task(run_pipeline(job_id, job_dir, edit_only=True))

    return {"id": job_id, "status": "queued"}


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    """Remove entire job directory."""
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    shutil.rmtree(job_dir, ignore_errors=True)
    return {"ok": True}
