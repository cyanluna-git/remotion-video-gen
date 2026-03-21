#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════
# Remotion Video Gen Pipeline
# Usage:
#   ./pipeline.sh <input.mp4> <scenario-or-edit.json> [options]
#   ./pipeline.sh <input.mp4> --auto-scenario [options]
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

# ── Handle --clean before arg count check ──
for arg in "$@"; do
  if [ "$arg" = "--clean" ]; then
    echo "  [CLEAN] Removing .work/ and output/ directories..."
    rm -rf "$WORK_DIR" "$OUTPUT_DIR"
    echo "  [OK] Clean complete."
    exit 0
  fi
done

# Parse args
print_usage() {
  echo "Usage:"
  echo "  ./pipeline.sh <input.mp4> <edit-or-scenario.json> [options]"
  echo "  ./pipeline.sh <input.mp4> --auto-scenario [options]"
  echo ""
  echo "Args:"
  echo "  input.mp4          Source video file"
  echo "  edit-or-scenario   Manual scenario JSON, or direct edit JSON when --skip-ai/--edit-only"
  echo ""
  echo "Options:"
  echo "  --auto-scenario    Generate scenario.json from Step 2 artifacts before edit generation"
  echo "  --title TEXT       Optional title hint for auto-scenario mode"
  echo "  --language CODE    Optional language hint for auto-scenario mode"
  echo "  --scenario-output PATH"
  echo "                     Where generated scenario.json should be saved in auto mode"
  echo "  --prompt-output PATH"
  echo "                     Where generated scenario prompt text should be saved in auto mode"
  echo "  --scenario-error-output PATH"
  echo "                     Where scenario-generation errors should be saved in auto mode"
  echo "  --edit-output PATH Where generated edit.json should be saved (default: .work/edit.json)"
  echo "  --voiceover-manifest PATH"
  echo "                     Optional provider-agnostic narration manifest to feed into edit generation"
  echo "  --skip-analysis    Skip Step 2 (use cached .work/ files)"
  echo "  --skip-ai          Skip Step 3 (use existing edit.json)"
  echo "  --edit-only        Only run Step 4 (Remotion render)"
  echo "  --force            Ignore cache, re-run everything"
  echo "  --clean            Delete .work/ and output/, then exit"
  echo "  --from-step=N      Start from step N (1-5), skip earlier steps"
  echo "  --output PATH      Output file (default: output/final.mp4)"
  echo "  --concurrency N    Remotion parallel frames (default: 4)"
}

if [ $# -lt 1 ]; then
  print_usage
  exit 1
fi

INPUT="$(realpath "$1")"
MANUAL_INPUT=""
AUTO_SCENARIO=false
TITLE_HINT=""
LANGUAGE_HINT=""
SCENARIO_OUTPUT=""
PROMPT_OUTPUT=""
SCENARIO_ERROR_OUTPUT=""
EDIT_OUTPUT=""
VOICEOVER_MANIFEST=""
SKIP_ANALYSIS=false
SKIP_AI=false
EDIT_ONLY=false
FORCE=false
FROM_STEP=1
OUTPUT_FILE="$OUTPUT_DIR/final.mp4"
CONCURRENCY=4

# Parse optional flags
shift
while [ $# -gt 0 ]; do
  case "$1" in
    --auto-scenario) AUTO_SCENARIO=true ;;
    --title) TITLE_HINT="$2"; shift ;;
    --language) LANGUAGE_HINT="$2"; shift ;;
    --scenario-output) SCENARIO_OUTPUT="$2"; shift ;;
    --prompt-output) PROMPT_OUTPUT="$2"; shift ;;
    --scenario-error-output) SCENARIO_ERROR_OUTPUT="$2"; shift ;;
    --edit-output) EDIT_OUTPUT="$2"; shift ;;
    --voiceover-manifest) VOICEOVER_MANIFEST="$2"; shift ;;
    --skip-analysis) SKIP_ANALYSIS=true ;;
    --skip-ai) SKIP_AI=true ;;
    --edit-only) EDIT_ONLY=true ;;
    --force) FORCE=true ;;
    --from-step=*) FROM_STEP="${1#--from-step=}" ;;
    --output) OUTPUT_FILE="$2"; shift ;;
    --concurrency) CONCURRENCY="$2"; shift ;;
    --help|-h) print_usage; exit 0 ;;
    --*) echo "Unknown option: $1"; exit 1 ;;
    *)
      if [ -n "$MANUAL_INPUT" ]; then
        echo "Unexpected extra positional argument: $1"
        exit 1
      fi
      MANUAL_INPUT="$(realpath "$1")"
      ;;
  esac
  shift
done

if [ "$AUTO_SCENARIO" = true ] && [ -n "$MANUAL_INPUT" ]; then
  echo "Error: manual scenario input cannot be combined with --auto-scenario."
  exit 1
fi

if [ "$AUTO_SCENARIO" = false ] && [ -z "$MANUAL_INPUT" ]; then
  echo "Error: manual mode requires <edit-or-scenario.json>."
  print_usage
  exit 1
fi

if [ -z "$EDIT_OUTPUT" ]; then
  EDIT_OUTPUT="$WORK_DIR/edit.json"
fi

if [ "$AUTO_SCENARIO" = true ]; then
  if [ -z "$SCENARIO_OUTPUT" ]; then
    SCENARIO_OUTPUT="$WORK_DIR/scenario.generated.json"
  fi
  if [ -z "$PROMPT_OUTPUT" ]; then
    PROMPT_OUTPUT="${SCENARIO_OUTPUT%.json}.prompt.txt"
  fi
  if [ -z "$SCENARIO_ERROR_OUTPUT" ]; then
    SCENARIO_ERROR_OUTPUT="${SCENARIO_OUTPUT%.json}.error.txt"
  fi
  SCENARIO_FILE="$SCENARIO_OUTPUT"
else
  SCENARIO_FILE="$MANUAL_INPUT"
fi

mkdir -p "$WORK_DIR" "$OUTPUT_DIR"

# ── Step tracking for summary ──
declare -a STEP_NAMES=("Preprocess" "Analysis" "AI Edit" "Render" "Loudnorm")
declare -a STEP_STATUS=("SKIP" "SKIP" "SKIP" "SKIP" "SKIP")
declare -a STEP_ELAPSED=(0 0 0 0 0)

# ── Validate --from-step ──
if ! [[ "$FROM_STEP" =~ ^[1-5]$ ]]; then
  echo "Error: --from-step must be 1-5, got '$FROM_STEP'"
  exit 1
fi

# ── Input file change detection via md5 ──
INPUT_MD5=$(md5 -q "$INPUT" 2>/dev/null || md5sum "$INPUT" | cut -d' ' -f1)
if [ -f "$WORK_DIR/input.md5" ]; then
  PREV_MD5=$(cat "$WORK_DIR/input.md5")
  if [ "$INPUT_MD5" != "$PREV_MD5" ]; then
    echo "  [INVALIDATE] Input file changed, clearing cache"
    rm -rf "$WORK_DIR"/*
    mkdir -p "$WORK_DIR"
  fi
fi
echo "$INPUT_MD5" > "$WORK_DIR/input.md5"

# ── Scenario/edit JSON change detection ──
if [ "$AUTO_SCENARIO" = true ]; then
  SCENARIO_MD5=$(printf '%s' "$INPUT_MD5|$TITLE_HINT|$LANGUAGE_HINT" | md5 -q 2>/dev/null || printf '%s' "$INPUT_MD5|$TITLE_HINT|$LANGUAGE_HINT" | md5sum | cut -d' ' -f1)
else
  SCENARIO_MD5=$(md5 -q "$SCENARIO_FILE" 2>/dev/null || md5sum "$SCENARIO_FILE" | cut -d' ' -f1)
fi
if [ -f "$WORK_DIR/scenario.md5" ]; then
  PREV_SCENARIO_MD5=$(cat "$WORK_DIR/scenario.md5")
  if [ "$SCENARIO_MD5" != "$PREV_SCENARIO_MD5" ]; then
    echo "  [INVALIDATE] Scenario/edit JSON changed, clearing Step 3+ cache"
    rm -f "$EDIT_OUTPUT"
    [ "$AUTO_SCENARIO" = true ] && rm -f "$SCENARIO_OUTPUT"
    # Don't remove Step 1-2 outputs (normalized video, transcript, scenes, silences, captions)
  fi
fi
echo "$SCENARIO_MD5" > "$WORK_DIR/scenario.md5"

# ── --from-step validation: check required files ──
if [ "$FROM_STEP" -gt 1 ]; then
  MISSING_FILES=()
  # Steps 1 produces normalized video + audio
  if [ "$FROM_STEP" -gt 1 ]; then
    BASENAME_CHECK=$(basename "$INPUT" .mp4)
    [ ! -f "$WORK_DIR/${BASENAME_CHECK}_normalized.mp4" ] && MISSING_FILES+=("${BASENAME_CHECK}_normalized.mp4")
  fi
  # Step 2 produces transcript, scenes, silences
  if [ "$FROM_STEP" -gt 2 ]; then
    [ ! -f "$WORK_DIR/transcript.json" ] && MISSING_FILES+=("transcript.json")
    [ ! -f "$WORK_DIR/scenes.json" ] && MISSING_FILES+=("scenes.json")
    [ ! -f "$WORK_DIR/silences.json" ] && MISSING_FILES+=("silences.json")
  fi
  # Step 3 produces edit.json
  if [ "$FROM_STEP" -gt 3 ]; then
    [ ! -f "$EDIT_OUTPUT" ] && [ ! -f "${MANUAL_INPUT:-}" ] && MISSING_FILES+=("edit.json")
  fi
  # Step 4 produces output file
  if [ "$FROM_STEP" -gt 4 ]; then
    [ ! -f "$OUTPUT_FILE" ] && MISSING_FILES+=("$(basename "$OUTPUT_FILE")")
  fi

  if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo "Error: --from-step=$FROM_STEP requires cached files from earlier steps."
    echo "  Missing: ${MISSING_FILES[*]}"
    echo "  Run the full pipeline first, or use a lower --from-step value."
    exit 1
  fi
  echo "  [FROM-STEP] Starting from step $FROM_STEP, skipping earlier steps"
fi

BASENAME=$(basename "$INPUT" .mp4)
NORMALIZED="$WORK_DIR/${BASENAME}_normalized.mp4"
AUDIO_WAV="$WORK_DIR/${BASENAME}_audio.wav"
TRANSCRIPT="$WORK_DIR/transcript.json"
SCENES="$WORK_DIR/scenes.json"
SILENCES="$WORK_DIR/silences.json"
CAPTIONS="$WORK_DIR/captions.json"
AI_EDIT="$EDIT_OUTPUT"

# ═══════════════════════════════════════════
# Step 1: ffmpeg Preprocessing
# ═══════════════════════════════════════════
if [ "$EDIT_ONLY" = false ] && [ "$FROM_STEP" -le 1 ]; then
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
    STEP_STATUS[0]="RAN"
  else
    echo "  [CACHE] Normalized video exists, skipping"
    STEP_STATUS[0]="CACHE"
  fi

  STEP_ELAPSED[0]=$(($(date +%s) - STEP_START))
  echo "  Elapsed: $(step_timer $STEP_START)"
fi

# ═══════════════════════════════════════════
# Step 2: Analysis (Whisper + Scene + Silence)
# ═══════════════════════════════════════════
if [ "$EDIT_ONLY" = false ] && [ "$SKIP_ANALYSIS" = false ] && [ "$FROM_STEP" -le 2 ]; then
  echo ""
  echo "==========================================="
  echo " Step 2: Analysis (parallel)"
  echo "==========================================="
  STEP_START=$(date +%s)

  WHISPER_PID=""
  SCENE_PID=""
  SILENCE_PID=""
  ANALYSIS_FAILED=false
  STEP2_RAN=false

  # Step 2a: Whisper transcription (background)
  if [ "$FORCE" = true ] || [ ! -f "$TRANSCRIPT" ]; then
    echo "  [2a] Whisper transcription starting..."
    python3 "$SCRIPTS_DIR/transcribe.py" "$AUDIO_WAV" \
      --output "$TRANSCRIPT" \
      > "$WORK_DIR/whisper.log" 2>&1 &
    WHISPER_PID=$!
    STEP2_RAN=true
  else
    echo "  [2a] [CACHE] Transcript exists, skipping"
  fi

  # Step 2b: Scene detection (background)
  if [ "$FORCE" = true ] || [ ! -f "$SCENES" ]; then
    echo "  [2b] Scene detection starting..."
    python3 "$SCRIPTS_DIR/detect_scenes.py" "$NORMALIZED" \
      --output "$SCENES" \
      > "$WORK_DIR/scenes.log" 2>&1 &
    SCENE_PID=$!
    STEP2_RAN=true
  else
    echo "  [2b] [CACHE] Scenes exist, skipping"
  fi

  # Step 2c: Silence detection (background)
  if [ "$FORCE" = true ] || [ ! -f "$SILENCES" ]; then
    echo "  [2c] Silence detection starting..."
    python3 "$SCRIPTS_DIR/detect_silence.py" "$NORMALIZED" \
      --output "$SILENCES" \
      > "$WORK_DIR/silences.log" 2>&1 &
    SILENCE_PID=$!
    STEP2_RAN=true
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
      python3 "$SCRIPTS_DIR/convert_captions.py" "$TRANSCRIPT" \
        --output "$CAPTIONS"
      echo "  [OK] Captions: $CAPTIONS"
      STEP2_RAN=true
    else
      echo "  [CACHE] Captions exist, skipping"
    fi
  else
    echo "  [SKIP] No transcript available, skipping caption conversion"
  fi

  if [ "$STEP2_RAN" = true ]; then
    STEP_STATUS[1]="RAN"
  else
    STEP_STATUS[1]="CACHE"
  fi
  STEP_ELAPSED[1]=$(($(date +%s) - STEP_START))
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
if [ "$EDIT_ONLY" = false ] && [ "$SKIP_AI" = false ] && [ "$FROM_STEP" -le 3 ]; then
  echo ""
  echo "==========================================="
  echo " Step 3: AI Edit Script Generation"
  echo "==========================================="
  STEP_START=$(date +%s)

  if [ "$AUTO_SCENARIO" = true ]; then
    if [ "$FORCE" = true ] || [ ! -f "$SCENARIO_OUTPUT" ]; then
      echo "  Generating scenario via AI..."
      SCENARIO_ARGS=(
        --output "$SCENARIO_OUTPUT"
        --prompt-output "$PROMPT_OUTPUT"
        --error-output "$SCENARIO_ERROR_OUTPUT"
        --source-name "$(basename "$INPUT")"
      )
      [ -n "$TITLE_HINT" ] && SCENARIO_ARGS+=(--title "$TITLE_HINT")
      [ -n "$LANGUAGE_HINT" ] && SCENARIO_ARGS+=(--language "$LANGUAGE_HINT")
      [ -f "$TRANSCRIPT" ] && SCENARIO_ARGS+=(--transcript "$TRANSCRIPT")
      [ -f "$SCENES" ] && SCENARIO_ARGS+=(--scenes "$SCENES")
      [ -f "$SILENCES" ] && SCENARIO_ARGS+=(--silences "$SILENCES")
      [ -f "$NORMALIZED" ] && SCENARIO_ARGS+=(--video "$NORMALIZED")

      python3 "$SCRIPTS_DIR/generate_scenario.py" --engine cli "${SCENARIO_ARGS[@]}"
      echo "  [OK] AI scenario: $SCENARIO_OUTPUT"
    else
      echo "  [CACHE] AI-generated scenario exists: $SCENARIO_OUTPUT"
    fi
  fi

  if [ -f "$AI_EDIT" ] && [ "$FORCE" = false ]; then
    echo "  [CACHE] AI-generated edit.json exists: $AI_EDIT"
    echo "  Using cached AI edit script"
    PROPS_FILE="$AI_EDIT"
    STEP_STATUS[2]="CACHE"
  else
    echo "  Generating edit script via AI..."
    if [ -z "$VOICEOVER_MANIFEST" ]; then
      DEFAULT_VOICEOVER_MANIFEST="$(dirname "$AI_EDIT")/voiceover/manifest.json"
      [ -f "$DEFAULT_VOICEOVER_MANIFEST" ] && VOICEOVER_MANIFEST="$DEFAULT_VOICEOVER_MANIFEST"
    fi
    GENERATE_ARGS=(
      --scenario "$SCENARIO_FILE"
      --output "$AI_EDIT"
    )
    [ -f "$TRANSCRIPT" ] && GENERATE_ARGS+=(--transcript "$TRANSCRIPT")
    [ -f "$SCENES" ] && GENERATE_ARGS+=(--scenes "$SCENES")
    [ -f "$SILENCES" ] && GENERATE_ARGS+=(--silences "$SILENCES")
    [ -f "$NORMALIZED" ] && GENERATE_ARGS+=(--video "$NORMALIZED")
    [ -n "$VOICEOVER_MANIFEST" ] && [ -f "$VOICEOVER_MANIFEST" ] && GENERATE_ARGS+=(--voiceover-manifest "$VOICEOVER_MANIFEST")

    python3 "$SCRIPTS_DIR/generate_edit.py" --engine cli "${GENERATE_ARGS[@]}"
    echo "  [OK] AI edit script: $AI_EDIT"
    PROPS_FILE="$AI_EDIT"
    STEP_STATUS[2]="RAN"
  fi

  STEP_ELAPSED[2]=$(($(date +%s) - STEP_START))
  echo "  Elapsed: $(step_timer $STEP_START)"
else
  # Skip AI: use a cached/generated edit.json if available, otherwise fall back
  # to the manual input path for direct edit-json workflows.
  if [ -f "$AI_EDIT" ]; then
    PROPS_FILE="$AI_EDIT"
  else
    PROPS_FILE="$MANUAL_INPUT"
  fi

  if [ "$EDIT_ONLY" = false ]; then
    echo ""
    echo "==========================================="
    echo " Step 3: AI Edit Script Generation [SKIPPED]"
    echo "==========================================="
    echo "  Using provided edit JSON: $PROPS_FILE"
  fi
fi

# ═══════════════════════════════════════════
# Step 4: Remotion Render
# ═══════════════════════════════════════════
if [ "$FROM_STEP" -le 4 ]; then
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
    # Also copy as normalized.mp4 (AI-generated edit.json may reference this name)
    cp "$NORMALIZED" "$REMOTION_DIR/public/recordings/normalized.mp4"
    echo "  Copied recording -> remotion/public/recordings/$RECORDING_NAME"
  fi

  # Wrap edit.json in {script: ...} for Remotion component props
  EDIT_SOURCE="${PROPS_FILE:-$MANUAL_INPUT}"
  WRAPPED_PROPS="$WORK_DIR/remotion-props.json"
  python3 "$SCRIPTS_DIR/prepare_render_props.py" \
    --edit-source "$EDIT_SOURCE" \
    --output "$WRAPPED_PROPS" \
    --public-dir "$REMOTION_DIR/public"

  echo "  Props file: $EDIT_SOURCE -> wrapped"
  echo "  Rendering with Remotion (concurrency=$CONCURRENCY)..."
  cd "$REMOTION_DIR"
  npx remotion render ScriptDrivenVideo \
    "$OUTPUT_FILE" \
    --props="$WRAPPED_PROPS" \
    --concurrency="$CONCURRENCY" \
    2>&1 | tail -5

  STEP_STATUS[3]="RAN"
  STEP_ELAPSED[3]=$(($(date +%s) - STEP_START))
  echo "  Elapsed: $(step_timer $STEP_START)"
fi

# ═══════════════════════════════════════════
# Step 5: Audio Post-Processing (loudnorm)
# ═══════════════════════════════════════════
if [ "$FROM_STEP" -le 5 ]; then
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
    STEP_STATUS[4]="RAN"
  else
    echo "  [SKIP] Output file not found, skipping audio post-processing"
  fi

  STEP_ELAPSED[4]=$(($(date +%s) - STEP_START))
  echo "  Elapsed: $(step_timer $STEP_START)"
fi

# ═══════════════════════════════════════════
# Done — Pipeline Summary
# ═══════════════════════════════════════════
PIPELINE_END=$(date +%s)
TOTAL_ELAPSED=$((PIPELINE_END - PIPELINE_START))
TOTAL_MINS=$((TOTAL_ELAPSED / 60))
TOTAL_SECS=$((TOTAL_ELAPSED % 60))

echo ""
echo "==========================================="
echo " Pipeline Summary"
echo "==========================================="

for i in 0 1 2 3 4; do
  STEP_NUM=$((i + 1))
  STATUS="${STEP_STATUS[$i]}"
  ELAPSED="${STEP_ELAPSED[$i]}"
  NAME="${STEP_NAMES[$i]}"

  # Format status tag
  case "$STATUS" in
    RAN)   STATUS_TAG="[RAN]   " ;;
    CACHE) STATUS_TAG="[CACHE] " ;;
    SKIP)  STATUS_TAG="[SKIP]  " ;;
    *)     STATUS_TAG="[----]  " ;;
  esac

  # Format elapsed time
  if [ "$STATUS" = "SKIP" ]; then
    ELAPSED_STR="-"
  elif [ "$ELAPSED" -eq 0 ] && [ "$STATUS" = "CACHE" ]; then
    ELAPSED_STR="0s"
  else
    E_MINS=$((ELAPSED / 60))
    E_SECS=$((ELAPSED % 60))
    if [ "$E_MINS" -gt 0 ]; then
      ELAPSED_STR="${E_MINS}m ${E_SECS}s"
    else
      ELAPSED_STR="${E_SECS}s"
    fi
  fi

  printf "  Step %d (%-11s) %s %s\n" "$STEP_NUM" "$NAME)" "$STATUS_TAG" "$ELAPSED_STR"
done

echo "  ---"
printf "  %-27s          %s\n" "Total:" "${TOTAL_MINS}m ${TOTAL_SECS}s"

echo ""
echo "  Output: $OUTPUT_FILE"
echo "  Size: $(du -h "$OUTPUT_FILE" 2>/dev/null | cut -f1 || echo 'N/A')"
