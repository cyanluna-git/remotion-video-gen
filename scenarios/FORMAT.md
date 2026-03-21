# Scenario Input Format

> **Version**: 1.0
> **Last Updated**: 2026-03-21

## Overview

A **scenario file** is a JSON document that describes how a screen recording should be edited into a polished video. It is the **user-authored input** to the pipeline -- not the generated `edit.json` that Remotion consumes.

### How it fits in the pipeline

```
scenario.json  (you write this)
     |
     v
pipeline.sh  ──>  Whisper + Scene/Silence detection
     |                        |
     v                        v
Claude API  <── merges scenario intent + analysis data
     |
     v
edit.json  (AI-generated, Remotion-ready)
     |
     v
Remotion render  ──>  final MP4
```

The scenario tells the AI **what** you want the video to show and **where** in the recording each section lives. The AI combines this intent with detected speech, scene changes, and silence gaps to produce the final edit script.

---

## JSON Schema

```jsonc
{
  // ── Video metadata ──
  "title": "string",
  "subtitle": "string?",
  "author": "string?",
  "language": "string",

  // ── Content structure ──
  "sections": [ /* ... */ ],

  // ── Visual style ──
  "style": { /* ... */ },

  // ── Processing options ──
  "options": { /* ... */ }
}
```

### Top-level fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | `string` | Yes | Video title displayed on the opening title card |
| `subtitle` | `string` | No | Subtitle shown below the title |
| `author` | `string` | No | Author name (displayed on title card if provided) |
| `language` | `string` | Yes | Primary language code (`ko`, `en`, etc.) or `"auto"` for detection. Guides Whisper and Claude |
| `sections` | `Section[]` | Yes | Ordered list of content sections (min 1) |
| `style` | `Style` | No | Visual customization. Defaults applied if omitted |
| `options` | `Options` | No | Processing behavior flags. Defaults applied if omitted |

### Section

Each section maps to a segment of the source recording and becomes a titled chapter in the output.

```jsonc
{
  "title": "string",
  "description": "string",
  "timeRange": {
    "startSec": 0,
    "endSec": 30
  },
  "emphasis": [ /* optional */ ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | `string` | Yes | Section heading. A title card is auto-generated for each section |
| `description` | `string` | Yes | What this section demonstrates. Claude uses this to make editing decisions (which parts to keep, how to caption) |
| `timeRange` | `object` | Yes | Maps to the source recording timestamps |
| `timeRange.startSec` | `number` | Yes | Start time in the source recording (seconds) |
| `timeRange.endSec` | `number` | Yes | End time in the source recording (seconds) |
| `emphasis` | `Emphasis[]` | No | Specific moments to highlight or caption |

### Legacy Compatibility

During migration, legacy payloads with flat timing fields are still accepted at ingestion time:

```jsonc
{
  "title": "Legacy Section",
  "description": "Old frontend payload shape",
  "startSec": 0,
  "endSec": 30
}
```

They are normalized to the canonical `timeRange` shape before they are saved or passed deeper into the pipeline. New writes should always emit `timeRange`.

### Emphasis

Marks a specific moment within a section for visual emphasis.

```jsonc
{
  "timeSec": 12.5,
  "type": "caption",
  "text": "Click the Start button",
  "region": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `timeSec` | `number` | Yes | Absolute time in the source recording (not relative to section start) |
| `type` | `"caption" \| "highlight"` | Yes | `caption` = text overlay, `highlight` = colored region box |
| `text` | `string` | When `type=caption` | Caption text to display |
| `region` | `object` | When `type=highlight` | Screen region to highlight |
| `region.x` | `number` | - | X coordinate (pixels from left) |
| `region.y` | `number` | - | Y coordinate (pixels from top) |
| `region.width` | `number` | - | Region width in pixels |
| `region.height` | `number` | - | Region height in pixels |

### Style

Controls the visual appearance of the generated video.

```jsonc
{
  "titleCardBackground": "linear-gradient(135deg, #c8102e, #1e1b4b)",
  "captionPosition": "bottom",
  "transition": "fade",
  "transitionDuration": 0.5
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `titleCardBackground` | `string` | `"linear-gradient(135deg, #c8102e, #1e1b4b)"` | CSS color or gradient for title cards |
| `captionPosition` | `"top" \| "bottom" \| "center"` | `"bottom"` | Default vertical position for captions |
| `transition` | `"fade" \| "slide-left" \| "slide-right" \| "wipe" \| "none"` | `"fade"` | Transition type between sections |
| `transitionDuration` | `number` | `0.5` | Transition length in seconds |

### Options

Controls pipeline processing behavior.

```jsonc
{
  "removeSilence": true,
  "silenceThreshold": 3.0,
  "autoCaption": true,
  "correctCaptions": true
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `removeSilence` | `boolean` | `true` | Automatically cut silence gaps from the recording |
| `silenceThreshold` | `number` | `3.0` | Minimum silence duration (seconds) to trigger removal |
| `autoCaption` | `boolean` | `true` | Run Whisper speech-to-text for automatic subtitles |
| `correctCaptions` | `boolean` | `true` | Use Claude to fix Whisper transcription errors (technical terms, grammar) |

---

## Required vs Optional Fields

### Required (must be present)

- `title`
- `language` (`"auto"` is allowed when the caller wants Whisper to detect the language)
- `sections` (at least one section)
  - `sections[].title`
  - `sections[].description`
  - `sections[].timeRange.startSec`
  - `sections[].timeRange.endSec`

### Required conditionally

- `emphasis[].text` -- required when `type` is `"caption"`
- `emphasis[].region` -- required when `type` is `"highlight"`

### Optional (defaults applied)

- `subtitle`, `author`
- `style` (all sub-fields)
- `options` (all sub-fields)
- `sections[].emphasis`

---

## Example: OQC Dashboard Demo

See [`example-oqc-demo.json`](./example-oqc-demo.json) for a full realistic scenario. It demonstrates:

- Edwards branding with custom gradient
- 4 sections covering a 3-minute recording
- Mixed caption and highlight emphasis
- Korean language with technical terms

---

## Tips

### Writing good section descriptions

The `description` field is what Claude reads to understand your intent. Be specific about what the viewer should notice:

```jsonc
// Too vague
"description": "Shows the dashboard"

// Better
"description": "Login flow and main dashboard overview. Show the navigation sidebar and KPI summary cards."
```

### How timeRange maps to your recording

`startSec` and `endSec` refer to timestamps in your **original source recording** (before any processing). Use any media player with a timestamp display to find the right values.

```
Recording timeline:
0s ──── 30s ──── 60s ──── 90s ──── 120s
|  Intro  |  Feature A  |  Feature B  |  Wrap-up  |

Section 1: { "startSec": 0, "endSec": 30 }
Section 2: { "startSec": 30, "endSec": 60 }
...
```

The pipeline may trim silence within each range, but it will never include footage outside the specified range.

### Emphasis timing

`emphasis[].timeSec` is an **absolute** timestamp in the source recording, not relative to the section start. This keeps things simple when you're scrubbing through the video to find the right moments.

```
Section timeRange: 30s - 60s
Emphasis at timeSec: 45  -->  45 seconds into the recording
```

### Overlapping sections

Sections should not overlap in time. If they do, the AI may produce unexpected clip arrangements. Keep `timeRange` values sequential and non-overlapping.

### Minimal scenario

The simplest valid scenario is:

```json
{
  "title": "My Video",
  "language": "auto",
  "sections": [
    {
      "title": "Full Recording",
      "description": "Show the entire recording with auto-generated captions",
      "timeRange": { "startSec": 0, "endSec": 60 }
    }
  ]
}
```

Everything else is optional and will use sensible defaults.
