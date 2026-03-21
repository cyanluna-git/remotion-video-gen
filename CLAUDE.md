# CLAUDE.md — Remotion Video Gen

> **Created**: 2026-03-21 (Fri)

## Project Overview

스크린 녹화 영상 + 시나리오 스크립트를 입력받아, AI 분석/보정을 거쳐 Remotion으로 최종 편집 영상을 자동 생성하는 파이프라인.

### Core Mission
- 녹화 MP4 + 시나리오 JSON → 편집된 최종 MP4 (1 command)
- AI가 자막 생성, 묵음/씬 감지, 편집 스크립트 자동 생성
- 시나리오 변경 시 재렌더링만으로 영상 재생성

## Project Structure

```
remotion-video-gen/
├── PLAN.md                  # 계획 문서
├── CLAUDE.md                # 이 파일
├── docs/
│   └── MULTIMODAL_ARTIFACTS.md  # TTS/clip-ranking/vision-QA 계약 문서
├── pipeline.sh              # 메인 파이프라인 (bash)
├── remotion/                # Remotion React 프로젝트
│   ├── src/
│   │   ├── index.ts
│   │   ├── Root.tsx
│   │   ├── ScriptDrivenVideo.tsx
│   │   ├── components/
│   │   └── types/
│   ├── public/recordings/   # 원본 녹화 (.gitignore)
│   ├── remotion.config.ts
│   └── package.json
├── scripts/                 # Python 분석 스크립트
│   ├── transcribe.py
│   ├── detect_scenes.py
│   ├── detect_silence.py
│   ├── generate_scenario.py
│   ├── generate_edit.py
│   ├── generate_clip_ranking.py
│   ├── clip_ranking.py
│   ├── generate_voiceover.py
│   ├── tts_providers.py
│   └── convert_captions.py
├── scenarios/               # 시나리오 JSON/MD
├── output/                  # 최종 출력 (.gitignore)
├── .work/                   # 중간 파일 (.gitignore)
└── requirements.txt
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Video Framework | Remotion 4.x (React + TypeScript) |
| Video Processing | ffmpeg (libx264) |
| Speech-to-Text | Whisper large-v3-turbo (openai-whisper) |
| Scene Detection | PySceneDetect (AdaptiveDetector) |
| AI Edit/Caption | Claude API (anthropic SDK) |
| Scripts | Python 3.12+ (type hints, Black) |
| Pipeline | Bash |
| Package Manager | npm (Remotion), pip (Python) |

## Code Conventions

### TypeScript (Remotion)
- strict mode, no `any`
- Functional components only
- Props: explicit interface
- Naming: PascalCase (components), camelCase (functions), UPPER_SNAKE_CASE (constants)

### Python (Scripts)
- Type hints required on all functions
- Black formatter, line length 120
- snake_case for functions, PascalCase for classes

### Bash (Pipeline)
- `set -euo pipefail` at top
- Functions for each pipeline step
- Clear echo messages for progress

### Git
- Conventional Commits: `feat/fix/refactor/chore(scope): subject`
- Scopes: `remotion`, `scripts`, `pipeline`, `docs`
- Include Co-Authored-By header

## Key Design Decisions

### Edit Script JSON이 중심
- 모든 편집 결정은 `edit.json`에 기록
- Remotion은 이 JSON을 해석하여 영상을 합성
- AI는 이 JSON을 생성/수정
- 사람이 수동으로 JSON을 편집하여 미세조정 가능

### 파이프라인 단계 독립성
- 각 단계는 독립 실행 가능 (전체 파이프라인 불필요)
- 중간 결과물은 `.work/`에 저장하여 재사용
- 실패 시 해당 단계만 재실행

### Video 컴포넌트 선택
- `<Video>` from `@remotion/media` (v4.0.354+) 기본 사용 — Mediabunny + WebCodecs, 가장 빠름
- `<OffthreadVideo>`는 장시간 녹화에서 캐시 비대/렌더 저하 문제 확인됨 (GitHub #3070)
- `<OffthreadVideo>`는 지원 안 되는 코덱 fallback 용도로만

### 씬 감지: PySceneDetect
- ffmpeg `scene` filter는 스크린 녹화에서 커서/스크롤 오탐 → PySceneDetect로 교체
- `AdaptiveDetector(adaptive_threshold=3.0, min_scene_len=15)` 사용
- 묵음 감지만 ffmpeg `silencedetect` 유지

## CLI Commands

```bash
# 전체 파이프라인
./pipeline.sh input.mp4 scenario.json

# AI-assisted 전체 파이프라인
./pipeline.sh input.mp4 --auto-scenario --title "Demo Run" --language ko

# TTS 포함 전체 파이프라인
TTS_PROVIDER=openai OPENAI_API_KEY=sk-... ./pipeline.sh input.mp4 --auto-scenario

# 로컬 mock TTS로 voiceover manifest만 점검
python scripts/generate_voiceover.py --scenario .work/scenario.generated.json --output .work/voiceover/manifest.json --provider mock

# Remotion 프리뷰
cd remotion && npx remotion studio

# Remotion 렌더링
cd remotion && npx remotion render ScriptDrivenVideo output.mp4 --props=edit.json

# Whisper 자막
python scripts/transcribe.py input.mp4

# 분석 결과로 시나리오 생성
python scripts/generate_scenario.py --transcript .work/transcript.json --video input.mp4 --output .work/scenario.generated.json

# 씬/묵음 감지
python scripts/detect_scenes.py input.mp4
python scripts/detect_silence.py input.mp4
```

## Environment Variables

```bash
# .env (gitignored)
ANTHROPIC_API_KEY=sk-ant-...    # Claude API key for edit script generation
OPENAI_API_KEY=sk-...           # Optional OpenAI TTS provider key
CLIP_RANKING_PROVIDER=heuristic # Optional: heuristic | none
TTS_PROVIDER=                   # Optional: openai | mock
TTS_MODEL=gpt-4o-mini-tts       # Default OpenAI TTS model
TTS_VOICE=alloy                 # Default OpenAI voice
TTS_AUDIO_FORMAT=wav            # Voiceover asset format
TTS_INSTRUCTIONS=               # Optional narration style instructions
```

## Important Notes

- `output/`, `.work/`, `remotion/public/recordings/` 는 gitignore 대상
- MP4, WAV 등 미디어 파일은 git에 포함하지 않음
- `ANTHROPIC_API_KEY`는 `.env`에만, 절대 커밋하지 않음
- Remotion은 Chromium 기반 렌더링 — 첫 실행 시 Chromium 다운로드 발생
- 멀티모달 확장 계약의 source of truth는 `docs/MULTIMODAL_ARTIFACTS.md` 와 `scripts/multimodal_contracts.py`
