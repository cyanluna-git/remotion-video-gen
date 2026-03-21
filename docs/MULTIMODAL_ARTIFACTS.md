# Multimodal Artifact Contracts

This document defines the canonical job-scoped artifacts used by the multimodal
pipeline expansion. These contracts are the source of truth for later tasks that
add TTS, clip-ranking, and vision QA providers.

## Design Rules

- All artifacts are job-scoped and live under `jobs/<id>/...`.
- Optional stages must degrade gracefully. Missing artifacts should not break the
  baseline pipeline.
- New contracts are additive and must stay compatible with the current
  `audio.voiceover.tracks` render path and `output/qa.json` summary handling.
- Full reruns may regenerate all artifacts. Edit-only rerenders may reuse an
  artifact only if its upstream inputs have not changed.

## Canonical Paths

| Artifact | Canonical path | Producer | Consumer |
|---|---|---|---|
| Voiceover manifest | `jobs/<id>/voiceover/manifest.json` | TTS stage | Edit generation, backend job detail |
| Voiceover assets | `jobs/<id>/voiceover/*` | TTS stage | Render prop preparation |
| Clip ranking | `jobs/<id>/analysis/clip-ranking.json` | Ranking stage | Scenario generation, edit generation, backend job detail |
| Combined QA | `jobs/<id>/output/qa.json` | Heuristic QA stage, optional vision QA stage | Backend, UI |
| Heuristic QA snapshot | `jobs/<id>/output/qa.heuristic.json` | Heuristic QA stage | QA merge logic |
| Vision QA snapshot | `jobs/<id>/output/qa.vision.json` | Vision QA stage | QA merge logic |

## Voiceover Manifest

Path: `jobs/<id>/voiceover/manifest.json`

```json
{
  "version": "1.0",
  "artifact": "voiceover-manifest",
  "generatedAt": "2026-03-21T00:00:00.000000Z",
  "status": "ready",
  "provider": {
    "name": "provider-name",
    "model": "model-id",
    "voice": "voice-id"
  },
  "revision": {
    "scenarioHash": "optional",
    "editHash": "optional"
  },
  "summary": {
    "trackCount": 2,
    "totalDurationSec": 12.4,
    "status": "ready"
  },
  "tracks": [
    {
      "id": "track-1",
      "label": "Intro",
      "src": "voiceover/intro.wav",
      "startSec": 0.0,
      "durationSec": 3.2,
      "text": "Narration text",
      "offsetSec": 0.0,
      "playbackRate": 1.0,
      "volume": 1.0,
      "provider": {
        "name": "provider-name",
        "model": "model-id"
      }
    }
  ]
}
```

Contract notes:

- `src` must be job-relative, never absolute.
- `tracks[].src` is the value edit generation should reference in
  `audio.voiceover.tracks`.
- `status` may be `ready`, `partial`, `failed`, or `skipped`.
- Failed or skipped stages may still emit a manifest when that is useful for
  diagnostics, but the pipeline must not require it.

## Clip-Ranking Artifact

Path: `jobs/<id>/analysis/clip-ranking.json`

```json
{
  "version": "1.0",
  "artifact": "clip-ranking",
  "generatedAt": "2026-03-21T00:00:00.000000Z",
  "status": "ready",
  "provider": {
    "name": "provider-name",
    "model": "model-id"
  },
  "revision": {
    "transcriptHash": "optional",
    "sceneHash": "optional",
    "silenceHash": "optional"
  },
  "summary": {
    "candidateCount": 4,
    "topCandidateIds": ["candidate-1", "candidate-3", "candidate-2"],
    "status": "ready"
  },
  "candidates": [
    {
      "id": "candidate-1",
      "startSec": 0.0,
      "endSec": 8.0,
      "score": 0.91,
      "rank": 1,
      "sourceSignals": ["transcript", "scenes"],
      "rationale": "Optional explanation",
      "transcriptExcerpt": "Optional excerpt"
    }
  ]
}
```

Contract notes:

- Ranking is additive. Scenario/edit generation must remain functional when this
  artifact is absent.
- `sourceSignals` should record which upstream artifacts contributed to the
  candidate.
- `score` scale may vary by provider, so consumers should treat it as relative
  ordering unless a later contract version states otherwise.

## Combined QA Artifact

Path: `jobs/<id>/output/qa.json`

The combined QA file extends the existing heuristic review instead of replacing
it. `summary`, `thumbnail`, and `autoRerender` remain top-level for backward
compatibility.

```json
{
  "version": "1.0",
  "artifact": "qa-review",
  "generatedAt": "2026-03-21T00:00:00.000000Z",
  "method": "heuristic",
  "videoDurationSec": 12.3,
  "thumbnail": {
    "path": "jobs/<id>/output/thumbnail.jpg"
  },
  "checks": {},
  "summary": {
    "status": "warn",
    "warningCount": 1,
    "failCount": 0
  },
  "autoRerender": false,
  "reviews": {
    "heuristic": {
      "version": "1.0",
      "method": "heuristic",
      "summary": {
        "status": "warn",
        "warningCount": 1,
        "failCount": 0
      }
    },
    "vision": {
      "version": "1.0",
      "method": "vision",
      "summary": {
        "status": "pass",
        "warningCount": 0,
        "failCount": 0
      }
    }
  }
}
```

Contract notes:

- `reviews.heuristic` is the current baseline review.
- `reviews.vision` is optional and may be omitted.
- Merged `summary.status` must reflect the most severe review result.
- `qa.heuristic.json` and `qa.vision.json` are optional implementation aids for
  stage-specific caching and debugging.

## Lifecycle Rules

| Trigger | Voiceover manifest | Clip ranking | QA artifacts |
|---|---|---|---|
| Fresh full run | Generate | Generate | Generate heuristic, optionally vision |
| Full rerun with changed upstream analysis | Invalidate and regenerate if dependent inputs changed | Invalidate and regenerate | Regenerate |
| Edit-only rerender with unchanged narration contract | Reuse if referenced inputs still match revision | Reuse | Regenerate |
| Missing provider credentials | Mark skipped or failed, continue baseline pipeline | Mark skipped or failed, continue baseline pipeline | Skip vision layer, keep heuristic QA |

## Backend Surface Expectations

Job summary/detail surfaces should eventually expose:

- `hasVoiceoverArtifacts`
- `voiceoverTrackCount`
- `hasClipRanking`
- `clipRankingCandidateCount`
- `qaStatus`
- `qaReviewMethods`
- `hasVisionQa`

Those additions should be additive so older jobs remain readable.
