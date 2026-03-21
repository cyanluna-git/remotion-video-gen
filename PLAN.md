# Remotion Video Generation Pipeline — Plan

> **Created**: 2026-03-21 (Fri)
> **Status**: Planning
> **Author**: Gerald Park

## Purpose

스크린 녹화 영상 + 시나리오 스크립트를 입력받아, AI 보정을 거쳐 편집된 최종 영상을 자동 생성하는 파이프라인.

## Problem

- 데모/소개 영상 제작에 반복적 수작업 필요 (자막, 편집, 트랜지션)
- 시나리오 변경 시 매번 영상 편집 도구로 재작업
- 전문 영상 편집 도구 학습 비용

## Solution

Remotion (React 기반 프로그래매틱 영상 생성) + ffmpeg + Whisper + Claude API를 조합한 셸 파이프라인.

---

## Architecture

```
녹화 영상 (MP4)  +  시나리오 스크립트 (JSON)
       │                      │
       ▼                      │
┌─────────────────┐           │
│ ffmpeg 전처리    │           │
│ • 해상도 정규화   │           │
│ • 오디오 추출     │           │
└────────┬────────┘           │
    ┌────┴────┐               │
    ▼         ▼               │
 Whisper    ffmpeg            │
 (자막생성)  (씬/묵음 감지)     │
    └────┬────┘               │
         ▼                    │
┌─────────────────┐           │
│ Claude API       │◀──────────┘
│ 스크립트 + 분석   │
│ → edit.json 생성  │
└────────┬────────┘
         ▼
┌─────────────────┐
│ Remotion Render  │
│ • 클립 편집       │
│ • 자막 오버레이   │
│ • 타이틀 카드     │
│ • 트랜지션       │
└────────┬────────┘
         ▼
┌─────────────────┐
│ ffmpeg 후처리    │
│ • 오디오 정규화   │
└────────┬────────┘
         ▼
    최종 MP4 출력
```

## Project Structure

```
remotion-video-gen/
├── PLAN.md                  # 이 문서
├── CLAUDE.md                # Claude Code 프로젝트 컨벤션
├── pipeline.sh              # 메인 실행 스크립트 (1 command)
├── remotion/                # Remotion React 프로젝트
│   ├── src/
│   │   ├── index.ts
│   │   ├── Root.tsx             # Composition 등록
│   │   ├── ScriptDrivenVideo.tsx # 타임라인 인터프리터 (핵심)
│   │   ├── components/
│   │   │   ├── CaptionOverlay.tsx
│   │   │   ├── TitleCard.tsx
│   │   │   ├── HighlightRegion.tsx
│   │   │   └── TransitionWrapper.tsx
│   │   └── types/
│   │       └── script.ts        # Edit script JSON 타입 정의
│   ├── public/
│   │   └── recordings/          # 원본 녹화 파일 (.gitignore)
│   ├── remotion.config.ts
│   ├── package.json
│   └── tsconfig.json
├── scripts/                 # Python AI/분석 스크립트
│   ├── transcribe.py            # Whisper 래퍼
│   ├── detect_scenes.py         # ffmpeg 씬 변경 감지
│   ├── detect_silence.py        # ffmpeg 묵음 구간 감지
│   ├── generate_edit.py         # Claude API → edit.json
│   └── convert_captions.py      # Whisper JSON → Remotion 자막
├── scenarios/               # 시나리오 스크립트 보관
│   └── example.json
├── output/                  # 최종 출력 (.gitignore)
├── .work/                   # 중간 파일 (.gitignore)
├── requirements.txt         # Python 의존성
└── .gitignore
```

## Edit Script JSON Schema

```json
{
  "version": "1.0",
  "fps": 30,
  "resolution": { "width": 1920, "height": 1080 },
  "sources": {
    "main": "recordings/session-01.mp4"
  },
  "timeline": [
    {
      "type": "title-card",
      "text": "OQC Dashboard Demo",
      "durationSec": 3,
      "background": "#1a1a2e",
      "transition": { "type": "fade", "durationSec": 0.5 }
    },
    {
      "type": "clip",
      "source": "main",
      "startSec": 0,
      "endSec": 12.5,
      "overlays": [
        {
          "type": "caption",
          "text": "로그인 후 메인 대시보드",
          "startSec": 1,
          "durationSec": 3,
          "position": "bottom"
        },
        {
          "type": "highlight",
          "region": { "x": 100, "y": 200, "width": 400, "height": 50 },
          "startSec": 2,
          "durationSec": 2,
          "color": "rgba(255,255,0,0.3)"
        }
      ]
    }
  ],
  "captions": [
    { "startSec": 0.0, "endSec": 2.5, "text": "Welcome to the demo" }
  ],
  "audio": {
    "backgroundMusic": { "src": "audio/bg.mp3", "volume": 0.1 }
  }
}
```

## AI Integration Points

| Step | Tool | Input | Output |
|------|------|-------|--------|
| 자막 생성 | **Whisper** (medium) | 오디오 WAV | 타임스탬프 포함 자막 JSON |
| 씬 감지 | **ffmpeg** `select='gt(scene,0.3)'` | MP4 | 씬 변경 타임스탬프 배열 |
| 묵음 감지 | **ffmpeg** `silencedetect` | MP4 | 묵음 구간 배열 |
| 편집 스크립트 | **Claude API** | 시나리오 + 자막 + 씬/묵음 | edit.json |
| 자막 교정 | **Claude API** | Whisper 원본 자막 | 교정된 자막 |

## Tech Stack

| Category | Technology |
|----------|-----------|
| Video Framework | Remotion (React) |
| Video Processing | ffmpeg |
| Speech-to-Text | Whisper (openai-whisper) |
| AI Edit/Caption | Claude API (Anthropic SDK) |
| Language | TypeScript (Remotion), Python (scripts) |
| Shell | Bash (pipeline orchestration) |
| Package Manager | npm (Remotion), pip (Python) |

## Key Remotion Components

| Component | Purpose |
|-----------|---------|
| `<OffthreadVideo>` | 스크린 녹화 삽입 (장시간 영상에 최적) |
| `<Sequence>` | 타임라인 구간 배치 |
| `<AbsoluteFill>` | 레이어 오버레이 |
| `@remotion/transitions` | 페이드, 슬라이드 트랜지션 |
| `useCurrentFrame()` | 프레임 기반 애니메이션 |
| `interpolate()` | 값 보간 (opacity, position 등) |

## CLI Commands

```bash
# 전체 파이프라인 실행
./pipeline.sh recording.mp4 scenario.json

# 개별 단계
npx remotion studio                    # 프리뷰 (브라우저)
npx remotion render ScriptDrivenVideo  # 렌더링
whisper audio.wav --model medium       # 자막 생성
```

## Implementation Phases

### Phase 1: Walking Skeleton
- [ ] Remotion 프로젝트 초기화
- [ ] ScriptDrivenVideo 컴포넌트 (clip + title-card)
- [ ] 간단한 edit.json 수동 작성 → 렌더링 확인
- [ ] pipeline.sh 기본 흐름 (ffmpeg 전처리 → Remotion 렌더)

### Phase 2: AI Pipeline
- [ ] Whisper 자막 생성 통합
- [ ] ffmpeg 씬/묵음 감지 통합
- [ ] Claude API edit.json 자동 생성
- [ ] CaptionOverlay, HighlightRegion 컴포넌트

### Phase 3: Polish
- [ ] 트랜지션 효과 (@remotion/transitions)
- [ ] 자막 스타일링 (폰트, 배경, 위치)
- [ ] 오디오 정규화 후처리
- [ ] 에러 핸들링 및 재시도 로직

### Phase 4: Advanced
- [ ] @remotion/player 웹 프리뷰 페이지
- [ ] 시나리오 마크다운 → JSON 변환기
- [ ] 멀티 소스 (화면 + 웹캠) PIP 지원
- [ ] AWS Lambda 렌더링 (대용량 영상)

## Dependencies

### Python
```
openai-whisper>=20231117
anthropic>=0.40.0
```

### Node.js
```
remotion
@remotion/cli
@remotion/media-utils
@remotion/transitions
@remotion/player
@remotion/renderer
```

### System
```
ffmpeg (with libx264)
node >= 18
python >= 3.10
```
