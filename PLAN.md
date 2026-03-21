# Remotion Video Generation Pipeline — Plan

> **Created**: 2026-03-21 (Fri)
> **Status**: Planning
> **Author**: Gerald Park

---

## 1. Purpose

스크린 녹화 영상 + 시나리오 스크립트를 입력받아, AI 분석/보정을 거쳐 편집된 최종 영상을 **1 command**로 자동 생성하는 파이프라인.

### Target Use Case

Edwards OQC 플랫폼 데모 영상 제작:
- Server Frontend(관리 대시보드) 조작 과정 녹화
- Edge Frontend(테스트 실행 UI) 조작 과정 녹화
- 시나리오 스크립트에 맞춰 자막, 타이틀 카드, 트랜지션 자동 삽입
- 변경 시 스크립트 수정 후 재렌더링만으로 영상 갱신

### Why Not 기존 도구?

| 기존 도구 | 문제 |
|-----------|------|
| Premiere/DaVinci | 전문 편집 도구 학습 비용, 수작업 반복 |
| OBS + 수동 편집 | 시나리오 변경 시 처음부터 재작업 |
| Loom/Screen.studio | 자막/트랜지션 커스터마이징 한계 |

### Why Remotion?

| 장점 | 설명 |
|------|------|
| 코드로 영상 제작 | React 컴포넌트 = 영상 프레임. 재현 가능 |
| JSON 기반 편집 | edit.json 수정으로 편집 결정 변경 |
| CLI 렌더링 | `npx remotion render` — CI/CD 통합 가능 |
| 프리뷰 | `npx remotion studio` — 브라우저에서 실시간 확인 |
| React 생태계 | 기존 React 개발 경험 그대로 활용 |

---

## 2. Architecture

### 전체 파이프라인 흐름

```
INPUT                          AI ANALYSIS                    OUTPUT
─────                          ──────────                     ──────

녹화 MP4 ──┐
           │
           ▼
    ┌──────────────┐
    │ Step 1       │
    │ ffmpeg 전처리 │  1920x1080, 30fps 정규화
    │ + 오디오 추출  │  PCM WAV 16kHz mono
    └──────┬───────┘
      ┌────┴─────┐
      ▼          ▼
┌──────────┐ ┌──────────┐
│ Step 2a  │ │ Step 2b  │  ← 병렬 실행
│ Whisper  │ │ ffmpeg   │
│ 음성→자막 │ │ 씬/묵음   │
│          │ │ 감지      │
└────┬─────┘ └────┬─────┘
     │            │
     ▼            ▼
┌─────────────────────────┐
│ Step 3                  │
│ Claude API              │ ◀── 시나리오 스크립트 (사용자 작성)
│                         │
│ Input:                  │
│  • 시나리오 JSON/MD      │
│  • Whisper 자막          │
│  • 씬 변경 타임스탬프     │
│  • 묵음 구간             │
│                         │
│ Output:                 │
│  • edit.json (편집 결정)  │
│  • 교정된 자막            │
└──────────┬──────────────┘
           │
           ▼
    ┌──────────────┐
    │ Step 4       │
    │ Remotion     │  React 기반 영상 합성
    │ Render       │  clip + 자막 + 타이틀 + 트랜지션
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Step 5       │
    │ ffmpeg 후처리 │  오디오 loudnorm, 최종 인코딩
    └──────┬───────┘
           │
           ▼
      최종 MP4 출력
```

### 데이터 흐름 (파일 기반)

```
input.mp4
  │
  ├──→ .work/normalized.mp4        (Step 1: 정규화)
  ├──→ .work/audio.wav             (Step 1: 오디오 추출)
  │
  ├──→ .work/transcript.json       (Step 2a: Whisper)
  ├──→ .work/scenes.json           (Step 2b: 씬 감지)
  ├──→ .work/silences.json         (Step 2b: 묵음 감지)
  │
  ├──→ .work/edit.json             (Step 3: Claude → 편집 결정)
  │
  └──→ output/final.mp4            (Step 4+5: Remotion + 후처리)
```

### 핵심 설계 원칙

1. **edit.json이 Single Source of Truth** — 모든 편집 결정은 이 파일에. AI가 생성하고, 사람이 미세조정 가능
2. **단계 독립성** — 각 Step을 단독 실행 가능. 실패 시 해당 단계만 재실행
3. **중간 결과 캐싱** — `.work/`에 중간 파일 보존. 시나리오만 바꿔서 Step 3부터 재실행 가능
4. **Remotion은 렌더러일 뿐** — 편집 로직은 edit.json에, Remotion은 해석/합성만 담당

---

## 3. Edit Script JSON Schema (핵심 계약)

이 JSON이 파이프라인의 중심. AI가 생성하고, Remotion이 소비.

```typescript
// types/script.ts

interface EditScript {
  version: "1.0";
  fps: number;                    // 보통 30
  resolution: {
    width: number;                // 1920
    height: number;               // 1080
  };
  sources: Record<string, string>; // 소스 비디오 경로 매핑

  timeline: TimelineEntry[];       // 순서대로 재생
  captions?: Caption[];            // 글로벌 자막 (선택)
  audio?: AudioConfig;             // 배경 음악/나레이션 (선택)
}

type TimelineEntry = ClipEntry | TitleCardEntry;

interface ClipEntry {
  type: "clip";
  source: string;                  // sources 키 참조
  startSec: number;                // 소스 영상 내 시작 시간
  endSec: number;                  // 소스 영상 내 종료 시간
  speed?: number;                  // 재생 속도 (기본 1.0)
  transition?: Transition;
  overlays?: Overlay[];
}

interface TitleCardEntry {
  type: "title-card";
  text: string;
  subtitle?: string;
  durationSec: number;
  background?: string;             // CSS 색상 또는 그라디언트
  transition?: Transition;
}

interface Transition {
  type: "fade" | "slide-left" | "slide-right" | "wipe" | "none";
  durationSec: number;             // 보통 0.3~0.5
}

interface Overlay {
  type: "caption" | "highlight" | "arrow" | "zoom";
  startSec: number;                // 클립 내 상대 시간
  durationSec: number;

  // caption 전용
  text?: string;
  position?: "top" | "bottom" | "center";

  // highlight 전용
  region?: { x: number; y: number; width: number; height: number };
  color?: string;

  // zoom 전용
  zoomFactor?: number;             // 1.5 = 150%
  zoomCenter?: { x: number; y: number };
}

interface Caption {
  startSec: number;                // 전체 타임라인 기준
  endSec: number;
  text: string;
  speaker?: string;
}

interface AudioConfig {
  backgroundMusic?: {
    src: string;
    volume: number;                // 0.0 ~ 1.0
    fadeIn?: number;               // seconds
    fadeOut?: number;
  };
  voiceover?: {
    src: string;
    volume: number;
  };
}
```

### Example: OQC Dashboard Demo

```json
{
  "version": "1.0",
  "fps": 30,
  "resolution": { "width": 1920, "height": 1080 },
  "sources": {
    "main": "recordings/oqc-dashboard-demo.mp4"
  },
  "timeline": [
    {
      "type": "title-card",
      "text": "OQC Automation Platform",
      "subtitle": "Server Dashboard Demo",
      "durationSec": 3,
      "background": "linear-gradient(135deg, #c8102e, #1e1b4b)",
      "transition": { "type": "fade", "durationSec": 0.5 }
    },
    {
      "type": "clip",
      "source": "main",
      "startSec": 2.0,
      "endSec": 15.5,
      "overlays": [
        {
          "type": "caption",
          "text": "로그인 후 메인 대시보드 진입",
          "startSec": 0,
          "durationSec": 3,
          "position": "bottom"
        }
      ],
      "transition": { "type": "fade", "durationSec": 0.3 }
    },
    {
      "type": "title-card",
      "text": "FT&CC 관리",
      "durationSec": 2,
      "background": "#1a1a2e",
      "transition": { "type": "slide-left", "durationSec": 0.4 }
    },
    {
      "type": "clip",
      "source": "main",
      "startSec": 30.0,
      "endSec": 55.0,
      "overlays": [
        {
          "type": "highlight",
          "region": { "x": 200, "y": 150, "width": 500, "height": 40 },
          "startSec": 2,
          "durationSec": 3,
          "color": "rgba(200, 16, 46, 0.2)"
        },
        {
          "type": "caption",
          "text": "테스트 시나리오 편집기",
          "startSec": 5,
          "durationSec": 4,
          "position": "bottom"
        }
      ]
    }
  ]
}
```

---

## 4. AI Integration — 상세 설계

### 4-1. Whisper 자막 생성

**모델 선택**: `medium` (한국어+영어 혼합 음성에 적합한 밸런스)
- `small`: 빠르지만 한국어 정확도 부족
- `medium`: 한/영 혼합에 실용적
- `large-v3`: 최고 정확도, 느림 (최종 품질 필요 시)

```bash
whisper audio.wav \
  --model medium \
  --language ko \
  --output_format json \
  --word_timestamps True \
  --output_dir .work/
```

**출력 → Remotion 자막 변환**:
```python
# Whisper segment → Caption 변환
{
  "start": 2.34, "end": 5.12,
  "text": "이 화면에서 테스트 시나리오를 편집합니다"
}
# →
{
  "startSec": 2.34, "endSec": 5.12,
  "text": "이 화면에서 테스트 시나리오를 편집합니다"
}
```

### 4-2. ffmpeg 씬/묵음 감지

**씬 변경 감지** — 스크린 녹화 특성 고려:
- 스크린 녹화는 실사 영상보다 씬 변화가 명확 (페이지 전환, 모달 열기)
- threshold `0.15~0.25` 권장 (실사 영상의 `0.3~0.4`보다 민감하게)

```bash
# 씬 감지
ffmpeg -i normalized.mp4 \
  -filter:v "select='gt(scene,0.2)',showinfo" \
  -f null - 2>&1 | grep pts_time

# 묵음 감지 (2초 이상 무음)
ffmpeg -i normalized.mp4 \
  -af "silencedetect=noise=-30dB:d=2" \
  -f null - 2>&1 | grep silence
```

### 4-3. Claude API — 편집 스크립트 생성

**프롬프트 전략**: 시나리오 + 분석 데이터를 합쳐 edit.json 생성

```
Input to Claude:
1. 시나리오 스크립트 (사용자가 작성한 의도/구성)
2. Whisper 자막 (실제 음성 내용 + 타임스탬프)
3. 씬 변경 타임스탬프 (화면 전환 지점)
4. 묵음 구간 (제거 후보)

Claude Output:
→ edit.json (timeline + overlays + transitions)

핵심 지시:
- 묵음 3초 이상 구간은 제거
- 시나리오 순서에 맞춰 클립 재배치
- 섹션 전환 시 타이틀 카드 삽입
- 주요 UI 동작에 자막 배치
```

### 4-4. 자막 교정 (후처리)

Whisper 자막의 오탈자/어색한 표현을 Claude가 교정:
- 기술 용어 교정 (예: "모드버스" → "Modbus")
- 불완전한 문장 정리
- 한/영 혼합 표현 통일

---

## 5. Project Structure

```
remotion-video-gen/
├── PLAN.md                      # 이 문서
├── CLAUDE.md                    # Claude Code 컨벤션
├── pipeline.sh                  # 메인 파이프라인 스크립트
│
├── remotion/                    # Remotion React 프로젝트
│   ├── src/
│   │   ├── index.ts             # Entry point
│   │   ├── Root.tsx             # Composition 등록
│   │   ├── ScriptDrivenVideo.tsx # 핵심: edit.json → 영상
│   │   ├── components/
│   │   │   ├── ClipSegment.tsx      # 비디오 클립 렌더
│   │   │   ├── TitleCard.tsx        # 타이틀 카드
│   │   │   ├── CaptionOverlay.tsx   # 자막 오버레이
│   │   │   ├── HighlightRegion.tsx  # 영역 하이라이트
│   │   │   └── CrossFade.tsx        # 트랜지션 래퍼
│   │   └── types/
│   │       └── script.ts            # EditScript 타입 정의
│   ├── public/
│   │   └── recordings/              # 원본 녹화 → .gitignore
│   ├── remotion.config.ts
│   ├── package.json
│   └── tsconfig.json
│
├── scripts/                     # Python 분석 스크립트
│   ├── transcribe.py                # Whisper 래퍼
│   ├── detect_scenes.py             # ffmpeg 씬 변경 감지
│   ├── detect_silence.py            # ffmpeg 묵음 구간 감지
│   ├── generate_edit.py             # Claude API → edit.json
│   └── convert_captions.py          # Whisper → Remotion 자막
│
├── scenarios/                   # 사용자 시나리오 스크립트
│   └── example-oqc-demo.json
│
├── output/                      # 최종 출력 → .gitignore
├── .work/                       # 중간 파일 → .gitignore
├── requirements.txt             # Python 의존성
├── .env.example                 # 환경변수 템플릿
└── .gitignore
```

---

## 6. Implementation Phases

### Phase 1: Walking Skeleton (MVP)

**목표**: 수동 edit.json으로 영상 1개 렌더링 성공

| Task | 설명 | 산출물 |
|------|------|--------|
| Remotion 프로젝트 init | `npm init video@latest` + 구조 정리 | `remotion/` |
| EditScript 타입 정의 | TypeScript 인터페이스 | `types/script.ts` |
| ScriptDrivenVideo | edit.json → Sequence + OffthreadVideo | `ScriptDrivenVideo.tsx` |
| ClipSegment | 비디오 클립 + startFrom | `ClipSegment.tsx` |
| TitleCard | 타이틀 카드 (텍스트, 배경색) | `TitleCard.tsx` |
| Example edit.json | 수동 작성 테스트용 | `scenarios/example.json` |
| pipeline.sh (basic) | ffmpeg 전처리 → Remotion render | `pipeline.sh` |
| E2E 검증 | 10초 녹화 → 편집 → 출력 확인 | 성공 영상 |

### Phase 2: AI Analysis Pipeline

**목표**: 녹화 영상에서 자동으로 분석 데이터 추출

| Task | 설명 | 산출물 |
|------|------|--------|
| transcribe.py | Whisper 래퍼 (medium, 한/영) | `scripts/transcribe.py` |
| detect_scenes.py | ffmpeg 씬 감지 + JSON 출력 | `scripts/detect_scenes.py` |
| detect_silence.py | ffmpeg 묵음 감지 + JSON 출력 | `scripts/detect_silence.py` |
| convert_captions.py | Whisper → Remotion 자막 변환 | `scripts/convert_captions.py` |
| CaptionOverlay | 자막 오버레이 (fade-in, 스타일링) | `CaptionOverlay.tsx` |
| pipeline.sh (analysis) | Step 1~2 통합 (전처리 + 분석) | `pipeline.sh` 확장 |

### Phase 3: AI Edit Script Generation

**목표**: 시나리오 + 분석 데이터 → edit.json 자동 생성

| Task | 설명 | 산출물 |
|------|------|--------|
| generate_edit.py | Claude API → edit.json | `scripts/generate_edit.py` |
| 시나리오 포맷 확정 | 사용자가 작성하는 입력 형식 | `scenarios/FORMAT.md` |
| 자막 교정 기능 | Claude로 Whisper 자막 교정 | generate_edit.py 내 |
| pipeline.sh (full) | Step 1~5 전체 통합 | `pipeline.sh` 완성 |
| HighlightRegion | 영역 하이라이트 (반투명 박스) | `HighlightRegion.tsx` |

### Phase 4: Polish & UX

**목표**: 프로덕션 품질 영상 출력

| Task | 설명 | 산출물 |
|------|------|--------|
| CrossFade 트랜지션 | @remotion/transitions 통합 | `CrossFade.tsx` |
| 오디오 후처리 | ffmpeg loudnorm | pipeline.sh 확장 |
| 에러 핸들링 | 각 단계 실패 시 재시도/스킵 | pipeline.sh 견고화 |
| 캐시 활용 | `.work/` 중간 결과 재사용 | pipeline.sh `--skip-*` 플래그 |

### Phase 5: Advanced (Future)

| Task | 설명 |
|------|------|
| 웹 프리뷰 | @remotion/player 기반 브라우저 프리뷰 |
| 멀티소스 PIP | 화면 + 웹캠 Picture-in-Picture |
| 마크다운 시나리오 | 마크다운 → JSON 변환기 |
| Lambda 렌더링 | AWS Lambda 분산 렌더링 (대용량) |

---

## 7. Dependencies

### System Requirements

```
ffmpeg >= 5.0 (with libx264, libfdk-aac)
node >= 18.0
python >= 3.10
```

### Python (`requirements.txt`)

```
openai-whisper>=20231117
anthropic>=0.40.0
```

### Node.js (Remotion)

```
remotion
@remotion/cli
@remotion/media-utils
@remotion/transitions
@remotion/renderer
```

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| 장시간 녹화 메모리 이슈 | Remotion 렌더링 OOM | `<OffthreadVideo>` 사용, ffmpeg로 사전 분할 |
| Whisper 한국어 정확도 | 자막 품질 저하 | Claude 교정 후처리, `large-v3` 모델 옵션 |
| Claude 편집 결정 품질 | 어색한 편집 | edit.json 수동 미세조정 가능하게 설계 |
| ffmpeg 씬 감지 오탐 | 불필요한 컷 | threshold 조정 + Claude가 필터링 |
| Remotion Chromium 의존 | 첫 실행 느림, 서버 환경 제약 | 로컬 개발 환경 기준, 필요 시 Docker |
| 렌더링 속도 | 긴 영상 시 수십 분 | `--concurrency=N` 병렬 프레임, 사전 분할 |

---

## 9. Success Criteria

### Phase 1 완료 기준
- [ ] 10초 녹화 MP4 → edit.json(수동) → 타이틀+클립+자막 포함 영상 출력
- [ ] `npx remotion studio`에서 프리뷰 확인

### Phase 3 완료 기준 (핵심 목표)
- [ ] 3분 녹화 + 시나리오 JSON → `./pipeline.sh` 1 command로 최종 MP4 출력
- [ ] 자막 자동 생성 + 교정
- [ ] 묵음 구간 자동 제거
- [ ] 섹션 전환 시 타이틀 카드 자동 삽입
