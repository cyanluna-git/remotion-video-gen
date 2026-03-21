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

# ── Step 1: ffmpeg Preprocessing ──
if [ "$EDIT_ONLY" = false ]; then
  echo ""
  echo "═══ Step 1: Preprocessing ═══"

  if [ "$FORCE" = true ] || [ ! -f "$NORMALIZED" ]; then
    echo "  Normalizing video → 1920x1080, 30fps..."
    ffmpeg -y -i "$INPUT" \
      -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" \
      -r 30 -c:v libx264 -preset fast -crf 18 \
      -c:a aac -ar 44100 \
      "$NORMALIZED" 2>/dev/null
    echo "  ✓ Normalized: $NORMALIZED"

    echo "  Extracting audio → WAV 16kHz mono..."
    ffmpeg -y -i "$NORMALIZED" \
      -vn -acodec pcm_s16le -ar 16000 -ac 1 \
      "$WORK_DIR/${BASENAME}_audio.wav" 2>/dev/null
    echo "  ✓ Audio: $WORK_DIR/${BASENAME}_audio.wav"
  else
    echo "  [CACHE] Normalized video exists, skipping"
  fi
fi

# ── Step 4: Remotion Render ──
echo ""
echo "═══ Step 4: Remotion Render ═══"

# Copy normalized video to Remotion public directory
mkdir -p "$REMOTION_DIR/public/recordings"
RECORDING_NAME="${BASENAME}_normalized.mp4"

if [ -f "$NORMALIZED" ]; then
  cp "$NORMALIZED" "$REMOTION_DIR/public/recordings/$RECORDING_NAME"
  echo "  Copied recording → remotion/public/recordings/$RECORDING_NAME"
fi

echo "  Rendering with Remotion (concurrency=$CONCURRENCY)..."
cd "$REMOTION_DIR"
npx remotion render ScriptDrivenVideo \
  "$OUTPUT_FILE" \
  --props="$EDIT_JSON" \
  --concurrency="$CONCURRENCY" \
  2>&1 | tail -5

echo ""
echo "═══ Done ═══"
echo "  Output: $OUTPUT_FILE"
echo "  Size: $(du -h "$OUTPUT_FILE" 2>/dev/null | cut -f1 || echo 'N/A')"
