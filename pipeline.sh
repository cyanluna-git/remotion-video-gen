#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════
# Remotion Video Gen Pipeline
# Usage: ./pipeline.sh <input.mp4> <edit.json>
# ═══════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORK_DIR="$SCRIPT_DIR/.work"
OUTPUT_DIR="$SCRIPT_DIR/output"
REMOTION_DIR="$SCRIPT_DIR/remotion"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"

PIPELINE_START=$(date +%s)

# ── Trap: kill background jobs on Ctrl+C ──
cleanup() {
  echo ""
  echo "--- Interrupted. Cleaning up background jobs... ---"
  kill $(jobs -p) 2>/dev/null || true
  wait 2>/dev/null || true
  echo "--- Cleanup done. ---"
  exit 130
}
trap cleanup INT TERM

# ── Helper: elapsed time ──
step_timer() {
  local start=$1
  local end=$(date +%s)
  local elapsed=$((end - start))
  local mins=$((elapsed / 60))
  local secs=$((elapsed % 60))
  if [ "$mins" -gt 0 ]; then
    echo "${mins}m ${secs}s"
  else
    echo "${secs}s"
  fi
}

# Parse args
if [ $# -lt 2 ]; then
  echo "Usage: ./pipeline.sh <input.mp4> <edit-or-scenario.json>"
  echo ""
  echo "Args:"
  echo "  input.mp4          Source video file"
  echo "  edit.json          Edit script (direct) or scenario (for AI generation)"
  echo ""
  echo "Options:"
  echo "  --skip-analysis    Skip Step 2 (use cached .work/ files)"
  echo "  --skip-ai          Skip Step 3 (use existing edit.json)"
  echo "  --edit-only        Only run Step 4 (Remotion render)"
  echo "  --force            Ignore cache, re-run everything"
  echo "  --output PATH      Output file (default: output/final.mp4)"
  echo "  --concurrency N    Remotion parallel frames (default: 4)"
  exit 1
fi

INPUT="$(realpath "$1")"
EDIT_JSON="$(realpath "$2")"
SKIP_ANALYSIS=false
SKIP_AI=false
EDIT_ONLY=false
FORCE=false
OUTPUT_FILE="$OUTPUT_DIR/final.mp4"
CONCURRENCY=4

# Parse optional flags
shift 2
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-analysis) SKIP_ANALYSIS=true ;;
    --skip-ai) SKIP_AI=true ;;
    --edit-only) EDIT_ONLY=true ;;
    --force) FORCE=true ;;
    --output) OUTPUT_FILE="$2"; shift ;;
    --concurrency) CONCURRENCY="$2"; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
  shift
done

mkdir -p "$WORK_DIR" "$OUTPUT_DIR"

BASENAME=$(basename "$INPUT" .mp4)
NORMALIZED="$WORK_DIR/${BASENAME}_normalized.mp4"
AUDIO_WAV="$WORK_DIR/${BASENAME}_audio.wav"
TRANSCRIPT="$WORK_DIR/transcript.json"
SCENES="$WORK_DIR/scenes.json"
SILENCES="$WORK_DIR/silences.json"
CAPTIONS="$WORK_DIR/captions.json"
AI_EDIT="$WORK_DIR/edit.json"

# ═══════════════════════════════════════════
# Step 1: ffmpeg Preprocessing
# ═══════════════════════════════════════════
if [ "$EDIT_ONLY" = false ]; then
  echo ""
  echo "==========================================="
  echo " Step 1: Preprocessing"
  echo "==========================================="
  STEP_START=$(date +%s)

  if [ "$FORCE" = true ] || [ ! -f "$NORMALIZED" ]; then
    echo "  Normalizing video -> 1920x1080, 30fps..."
    ffmpeg -y -i "$INPUT" \
      -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" \
      -r 30 -c:v libx264 -preset fast -crf 18 \
      -c:a aac -ar 44100 \
      "$NORMALIZED" 2>/dev/null
    echo "  [OK] Normalized: $NORMALIZED"

    echo "  Extracting audio -> WAV 16kHz mono..."
    ffmpeg -y -i "$NORMALIZED" \
      -vn -acodec pcm_s16le -ar 16000 -ac 1 \
      "$AUDIO_WAV" 2>/dev/null
    echo "  [OK] Audio: $AUDIO_WAV"
  else
    echo "  [CACHE] Normalized video exists, skipping"
  fi

  echo "  Elapsed: $(step_timer $STEP_START)"
fi

# ═══════════════════════════════════════════
# Step 2: Analysis (Whisper + Scene + Silence)
# ═══════════════════════════════════════════
if [ "$EDIT_ONLY" = false ] && [ "$SKIP_ANALYSIS" = false ]; then
  echo ""
  echo "==========================================="
  echo " Step 2: Analysis (parallel)"
  echo "==========================================="
  STEP_START=$(date +%s)

  WHISPER_PID=""
  SCENE_PID=""
  SILENCE_PID=""
  ANALYSIS_FAILED=false

  # Step 2a: Whisper transcription (background)
  if [ "$FORCE" = true ] || [ ! -f "$TRANSCRIPT" ]; then
    echo "  [2a] Whisper transcription starting..."
    python "$SCRIPTS_DIR/transcribe.py" "$AUDIO_WAV" \
      --output "$TRANSCRIPT" \
      > "$WORK_DIR/whisper.log" 2>&1 &
    WHISPER_PID=$!
  else
    echo "  [2a] [CACHE] Transcript exists, skipping"
  fi

  # Step 2b: Scene detection (background)
  if [ "$FORCE" = true ] || [ ! -f "$SCENES" ]; then
    echo "  [2b] Scene detection starting..."
    python "$SCRIPTS_DIR/detect_scenes.py" "$NORMALIZED" \
      --output "$SCENES" \
      > "$WORK_DIR/scenes.log" 2>&1 &
    SCENE_PID=$!
  else
    echo "  [2b] [CACHE] Scenes exist, skipping"
  fi

  # Step 2c: Silence detection (background)
  if [ "$FORCE" = true ] || [ ! -f "$SILENCES" ]; then
    echo "  [2c] Silence detection starting..."
    python "$SCRIPTS_DIR/detect_silence.py" "$NORMALIZED" \
      --output "$SILENCES" \
      > "$WORK_DIR/silences.log" 2>&1 &
    SILENCE_PID=$!
  else
    echo "  [2c] [CACHE] Silences exist, skipping"
  fi

  # Wait for all background jobs
  echo "  Waiting for analysis tasks to complete..."

  if [ -n "$WHISPER_PID" ]; then
    if wait "$WHISPER_PID"; then
      echo "  [2a] [OK] Whisper transcription complete"
    else
      echo "  [2a] [FAIL] Whisper transcription failed (see $WORK_DIR/whisper.log)"
      ANALYSIS_FAILED=true
    fi
  fi

  if [ -n "$SCENE_PID" ]; then
    if wait "$SCENE_PID"; then
      echo "  [2b] [OK] Scene detection complete"
    else
      echo "  [2b] [FAIL] Scene detection failed (see $WORK_DIR/scenes.log)"
      ANALYSIS_FAILED=true
    fi
  fi

  if [ -n "$SILENCE_PID" ]; then
    if wait "$SILENCE_PID"; then
      echo "  [2c] [OK] Silence detection complete"
    else
      echo "  [2c] [FAIL] Silence detection failed (see $WORK_DIR/silences.log)"
      ANALYSIS_FAILED=true
    fi
  fi

  if [ "$ANALYSIS_FAILED" = true ]; then
    echo ""
    echo "  WARNING: One or more analysis tasks failed."
    echo "  Check logs in $WORK_DIR/ for details."
  fi

  # Convert captions (depends on Whisper transcript)
  if [ -f "$TRANSCRIPT" ]; then
    if [ "$FORCE" = true ] || [ ! -f "$CAPTIONS" ]; then
      echo "  Converting captions from transcript..."
      python "$SCRIPTS_DIR/convert_captions.py" "$TRANSCRIPT" \
        --output "$CAPTIONS"
      echo "  [OK] Captions: $CAPTIONS"
    else
      echo "  [CACHE] Captions exist, skipping"
    fi
  else
    echo "  [SKIP] No transcript available, skipping caption conversion"
  fi

  echo "  Elapsed: $(step_timer $STEP_START)"

elif [ "$EDIT_ONLY" = false ] && [ "$SKIP_ANALYSIS" = true ]; then
  echo ""
  echo "==========================================="
  echo " Step 2: Analysis [SKIPPED]"
  echo "==========================================="
  echo "  Using cached .work/ files"
fi

# ═══════════════════════════════════════════
# Step 3: AI Edit Script Generation
# ═══════════════════════════════════════════
if [ "$EDIT_ONLY" = false ] && [ "$SKIP_AI" = false ]; then
  echo ""
  echo "==========================================="
  echo " Step 3: AI Edit Script Generation"
  echo "==========================================="
  STEP_START=$(date +%s)

  # Determine the props file for Remotion
  # If EDIT_JSON is a scenario (not a direct edit script), generate via AI
  # For now: if .work/edit.json exists from a previous run, or if --skip-ai, use EDIT_JSON directly
  if [ -f "$AI_EDIT" ] && [ "$FORCE" = false ]; then
    echo "  [CACHE] AI-generated edit.json exists: $AI_EDIT"
    echo "  Using cached AI edit script"
    PROPS_FILE="$AI_EDIT"
  else
    echo "  Generating edit script via AI..."
    GENERATE_ARGS=(
      --scenario "$EDIT_JSON"
      --output "$AI_EDIT"
    )
    [ -f "$TRANSCRIPT" ] && GENERATE_ARGS+=(--transcript "$TRANSCRIPT")
    [ -f "$SCENES" ] && GENERATE_ARGS+=(--scenes "$SCENES")
    [ -f "$SILENCES" ] && GENERATE_ARGS+=(--silences "$SILENCES")
    [ -f "$NORMALIZED" ] && GENERATE_ARGS+=(--video "$NORMALIZED")

    python "$SCRIPTS_DIR/generate_edit.py" "${GENERATE_ARGS[@]}"
    echo "  [OK] AI edit script: $AI_EDIT"
    PROPS_FILE="$AI_EDIT"
  fi

  echo "  Elapsed: $(step_timer $STEP_START)"
else
  # Skip AI: use the provided EDIT_JSON directly as props
  PROPS_FILE="$EDIT_JSON"

  if [ "$EDIT_ONLY" = false ]; then
    echo ""
    echo "==========================================="
    echo " Step 3: AI Edit Script Generation [SKIPPED]"
    echo "==========================================="
    echo "  Using provided edit JSON: $EDIT_JSON"
  fi
fi

# ═══════════════════════════════════════════
# Step 4: Remotion Render
# ═══════════════════════════════════════════
echo ""
echo "==========================================="
echo " Step 4: Remotion Render"
echo "==========================================="
STEP_START=$(date +%s)

# Copy normalized video to Remotion public directory
mkdir -p "$REMOTION_DIR/public/recordings"
RECORDING_NAME="${BASENAME}_normalized.mp4"

if [ -f "$NORMALIZED" ]; then
  cp "$NORMALIZED" "$REMOTION_DIR/public/recordings/$RECORDING_NAME"
  echo "  Copied recording -> remotion/public/recordings/$RECORDING_NAME"
fi

echo "  Props file: ${PROPS_FILE:-$EDIT_JSON}"
echo "  Rendering with Remotion (concurrency=$CONCURRENCY)..."
cd "$REMOTION_DIR"
npx remotion render ScriptDrivenVideo \
  "$OUTPUT_FILE" \
  --props="${PROPS_FILE:-$EDIT_JSON}" \
  --concurrency="$CONCURRENCY" \
  2>&1 | tail -5

echo "  Elapsed: $(step_timer $STEP_START)"

# ═══════════════════════════════════════════
# Step 5: Audio Post-Processing (loudnorm)
# ═══════════════════════════════════════════
echo ""
echo "==========================================="
echo " Step 5: Audio Post-Processing"
echo "==========================================="
STEP_START=$(date +%s)

if [ -f "$OUTPUT_FILE" ]; then
  LOUDNORM_TEMP="${OUTPUT_FILE%.mp4}_loudnorm.mp4"

  echo "  Applying loudnorm (I=-14, TP=-1.5, LRA=11)..."
  ffmpeg -y -i "$OUTPUT_FILE" \
    -af "loudnorm=I=-14:TP=-1.5:LRA=11" \
    -c:v copy \
    "$LOUDNORM_TEMP" 2>/dev/null

  mv "$LOUDNORM_TEMP" "$OUTPUT_FILE"
  echo "  [OK] Audio normalized: $OUTPUT_FILE"
else
  echo "  [SKIP] Output file not found, skipping audio post-processing"
fi

echo "  Elapsed: $(step_timer $STEP_START)"

# ═══════════════════════════════════════════
# Done
# ═══════════════════════════════════════════
PIPELINE_END=$(date +%s)
TOTAL_ELAPSED=$((PIPELINE_END - PIPELINE_START))
TOTAL_MINS=$((TOTAL_ELAPSED / 60))
TOTAL_SECS=$((TOTAL_ELAPSED % 60))

echo ""
echo "==========================================="
echo " Done"
echo "==========================================="
echo "  Output: $OUTPUT_FILE"
echo "  Size: $(du -h "$OUTPUT_FILE" 2>/dev/null | cut -f1 || echo 'N/A')"
echo "  Total time: ${TOTAL_MINS}m ${TOTAL_SECS}s"
