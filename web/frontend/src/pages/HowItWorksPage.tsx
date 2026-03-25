import { Link } from 'react-router-dom';

type UsageItem = {
  title: string;
  body: string;
};

type PipelineStep = {
  number: string;
  title: string;
  tag: string;
  ai?: boolean;
  description: string;
  inputs: string[];
  outputs: string[];
  notes: string[];
};

type FlowNode = {
  label: string;
  detail: string;
  tone: 'core' | 'ai' | 'optional' | 'output';
  ai?: boolean;
};

type SummaryCard = {
  label: string;
  value: string;
  detail: string;
};

type FaqItem = {
  question: string;
  answer: string;
};

const usageItems: UsageItem[] = [
  {
    title: '1. 소스 영상을 업로드합니다',
    body: 'MP4, MOV, WebM 화면 녹화 영상을 업로드하면 백엔드가 작업 디렉터리를 만들고 백그라운드 파이프라인을 시작합니다.',
  },
  {
    title: '2. 입력 방식을 선택합니다',
    body: 'Auto 모드는 transcript, scene, silence, clip-ranking 힌트로 scenario를 자동 생성합니다. Manual 모드는 섹션을 직접 정의합니다.',
  },
  {
    title: '3. 렌더 완료 후 결과를 검토합니다',
    body: '작업이 끝나면 결과 페이지에서 최종 영상, edit.json, voiceover manifest, clip-ranking, thumbnail, QA 결과를 확인할 수 있습니다.',
  },
];

const operatingRules = [
  '현재 코드에는 분 단위 하드 제한이 없지만, 영상이 길어질수록 scenario/edit 생성 프롬프트에 들어가는 transcript segment 수가 제한되어 품질이 떨어질 수 있습니다.',
  'Auto 모드는 말소리나 장면 변화가 있는 영상에서 가장 잘 동작합니다. 정보량이 낮은 영상도 렌더는 되지만 scenario가 넓게 잡힐 수 있습니다.',
  'TTS, clip ranking, vision QA는 optional stage입니다. 하나가 실패해도 메인 렌더는 계속 진행됩니다.',
  'TTS를 쓰지 않으면 렌더는 원본 영상 오디오만 사용합니다. 원본이 무음이면 결과물도 거의 무음에 가깝습니다.',
];

const pipelineSteps: PipelineStep[] = [
  {
    number: '01',
    title: '작업 접수',
    tag: 'API / UI',
    description:
      '프론트엔드가 소스 영상을 업로드하고, manual scenario 또는 auto-scenario 힌트를 함께 보냅니다. 백엔드는 job 디렉터리를 만들고 백그라운드 실행을 시작합니다.',
    inputs: ['소스 영상', 'manual scenario 또는 auto 모드 플래그', 'optional title/language 힌트'],
    outputs: ['jobs/<id>/input.mp4', 'jobs/<id>/meta.json'],
    notes: ['Manual 모드는 scenario JSON이 필요합니다.', 'Auto 모드는 영상만 올리고 optional 힌트를 추가할 수 있습니다.'],
  },
  {
    number: '02',
    title: '전처리',
    tag: 'ffmpeg',
    description:
      '입력 영상을 안정적인 렌더 포맷으로 정규화하고, 이후 전사용 mono WAV 오디오를 추출합니다.',
    inputs: ['input.mp4'],
    outputs: ['.work/<name>_normalized.mp4', '.work/<name>_audio.wav'],
    notes: ['타깃 포맷은 1920x1080, 30fps입니다.', '오디오는 16kHz mono WAV로 추출됩니다.'],
  },
  {
    number: '03',
    title: '분석',
    tag: 'parallel',
    ai: true,
    description:
      'Whisper 전사, scene detection, silence detection이 병렬로 실행됩니다. transcript가 생성되면 caption용 데이터도 함께 만듭니다.',
    inputs: ['normalized video', 'extracted WAV'],
    outputs: ['transcript.json', 'scenes.json', 'silences.json', 'captions.json'],
    notes: ['분석 작업은 동시에 실행됩니다.', 'transcript가 없으면 caption 변환은 건너뜁니다.'],
  },
  {
    number: '04',
    title: '클립 랭킹',
    tag: 'optional',
    description:
      'transcript 밀도, 장면 변화, silence overlap, 영상 길이를 바탕으로 의미 있어 보이는 구간을 heuristic으로 점수화합니다. 이후 AI 단계의 힌트로만 사용됩니다.',
    inputs: ['transcript.json', 'scenes.json', 'silences.json', 'normalized video'],
    outputs: ['analysis/clip-ranking.json'],
    notes: ['현재 provider는 heuristic입니다.', '실패해도 scenario/edit 생성은 계속 진행됩니다.'],
  },
  {
    number: '05',
    title: '시나리오 생성',
    tag: 'auto mode',
    ai: true,
    description:
      'Auto 모드에서는 Claude가 canonical scenario.json을 생성합니다. prompt에는 transcript, scenes, silences, clip-ranking, duration이 들어갑니다.',
    inputs: ['analysis artifacts', 'optional title/language hints'],
    outputs: ['scenario.json', 'scenario.prompt.txt', 'scenario.error.txt on failure'],
    notes: ['Manual 모드는 이 단계를 건너뜁니다.', 'canonical section은 timeRange.startSec/endSec를 사용합니다.'],
  },
  {
    number: '06',
    title: '나레이션 생성',
    tag: 'optional TTS',
    ai: true,
    description:
      'TTS provider가 켜져 있으면 음성을 합성합니다. 일반 모드는 scenario section별로 생성하고, full-dub 모드는 transcript를 ~12초 청크로 분할 → AI가 나레이션 다듬기 → 청크별 TTS 생성(40-50 트랙)으로 원본 음성을 완전히 대체합니다.',
    inputs: ['scenario.json 또는 transcript chunks', 'TTS provider config'],
    outputs: ['voiceover/*.mp3 or provider format', 'voiceover/manifest.json', 'tts_chunks.json (full-dub)', 'polished_chunks.json (full-dub)'],
    notes: ['현재 provider는 mock, OpenAI, edge(무료)입니다.', 'Full-dub은 edge-tts + en-US-AndrewMultilingualNeural 보이스를 기본 사용합니다.', 'TTS가 실패하면 voiceover 없이 렌더를 계속합니다.'],
  },
  {
    number: '07',
    title: '편집 스크립트 생성',
    tag: 'Claude / Codex',
    ai: true,
    description:
      'AI가 scenario와 각종 분석 산출물을 사용해 최종 edit.json timeline을 생성합니다. caption class, title card, transition, original audio, voiceover track 정보가 여기에 들어갑니다. CLI(Claude), API, Codex 엔진을 선택할 수 있습니다.',
    inputs: ['scenario.json', 'analysis artifacts', 'optional clip ranking', 'optional voiceover manifest'],
    outputs: ['edit.json'],
    notes: ['sources.main은 recordings/normalized.mp4로 정규화됩니다.', 'voiceover manifest가 있을 때만 narration track이 붙습니다.', 'Full-dub 모드는 Codex 엔진을 기본 사용합니다.'],
  },
  {
    number: '07.5',
    title: '타임라인 재구성',
    tag: 'full-dub',
    description:
      'Full-dub 모드에서만 실행됩니다. 나레이션 타이밍을 기반으로 타임라인을 재구성합니다: 각 TTS 트랙 전후에 패딩을 두고(기본 -0.5s/+1.0s), 무음 구간을 잘라냅니다. 인접 클립은 병합(gap < 1.5s)하고, 섹션 경계에 타이틀 카드를 삽입합니다. 원본 음성은 완전히 제거됩니다.',
    inputs: ['edit.json', 'voiceover/manifest.json', 'scenario.json', 'optional captions.json'],
    outputs: ['edit.json (rebuilt with jump-cuts)'],
    notes: ['7분 녹화 → 5분 편집 영상으로 자동 압축됩니다.', '--pad-before, --pad-after, --merge-gap으로 타이밍 조절 가능합니다.'],
  },
  {
    number: '08',
    title: '렌더',
    tag: 'Remotion',
    description:
      '정규화된 영상과 로컬 오디오 자산을 Remotion public 디렉터리로 복사한 뒤, ScriptDrivenVideo가 clip, title, caption, transition, audio layer를 합성해 최종 MP4를 렌더합니다.',
    inputs: ['edit.json', 'normalized video', 'optional voiceover assets', 'optional background music'],
    outputs: ['output/final.mp4'],
    notes: ['voiceover가 없으면 원본 오디오는 기본 볼륨으로 유지됩니다.', 'timeline 길이는 edit.json에서 동적으로 계산됩니다.'],
  },
  {
    number: '09',
    title: '오디오 후처리',
    tag: 'loudnorm',
    description:
      '최종 영상에 loudness normalization을 적용해 재생 음량을 더 일정하게 맞춥니다.',
    inputs: ['output/final.mp4'],
    outputs: ['output/final.mp4 with loudnorm applied'],
    notes: ['QA artifact를 만들기 전 마지막 미디어 변환 단계입니다.'],
  },
  {
    number: '10',
    title: 'QA 및 결과 노출',
    tag: 'review',
    ai: true,
    description:
      '대표 프레임을 샘플링해 thumbnail을 고르고, heuristic QA를 생성합니다. vision QA provider가 있으면 2차 semantic review가 추가되며, 이후 API가 모든 artifact를 UI에 노출합니다.',
    inputs: ['final.mp4', 'edit.json', 'optional vision QA provider'],
    outputs: ['output/thumbnail.jpg', 'output/qa.json', 'output/qa.heuristic.json', 'optional output/qa.vision.json'],
    notes: ['결과 페이지에서 logs, edit JSON, voiceover manifest, clip ranking, QA 요약을 볼 수 있습니다.', 'Vision QA는 heuristic QA를 대체하지 않고 추가됩니다.'],
  },
];

const flowNodes: FlowNode[] = [
  { label: '업로드', detail: '영상 + 입력 모드', tone: 'core' },
  { label: '전처리', detail: '정규화 + WAV 추출', tone: 'core' },
  { label: '분석', detail: 'transcript / scene / silence', tone: 'ai', ai: true },
  { label: '클립 랭킹', detail: '고신호 구간 힌트', tone: 'optional' },
  { label: '시나리오', detail: 'auto 모드에서만 생성', tone: 'ai', ai: true },
  { label: 'TTS', detail: 'section별 또는 세그먼트별 narration', tone: 'optional', ai: true },
  { label: 'edit.json', detail: '최종 타임라인', tone: 'ai', ai: true },
  { label: '타임라인 재구성', detail: 'full-dub: 점프컷 편집', tone: 'optional', ai: true },
  { label: 'Remotion', detail: 'render + loudnorm', tone: 'core' },
  { label: 'QA', detail: 'thumbnail + heuristic + vision', tone: 'output', ai: true },
];

const summaryCards: SummaryCard[] = [
  {
    label: '입력 방식',
    value: 'Auto / Manual',
    detail: '영상만 넣는 흐름과 section을 직접 제어하는 흐름을 둘 다 지원합니다.',
  },
  {
    label: 'Optional AI',
    value: 'Full-Dub / TTS / Ranking / Vision',
    detail: 'Full-dub 모드는 원본 음성을 TTS로 교체하고 점프컷 편집까지 자동화합니다. 나레이션, 클립 랭킹, vision QA는 조건부로 붙으며 실패해도 메인 렌더는 계속됩니다.',
  },
  {
    label: '결과 산출물',
    value: 'Video + JSON + QA',
    detail: '최종 영상뿐 아니라 scenario, edit, voiceover, clip-ranking, QA artifact까지 함께 남습니다.',
  },
];

const recommendations = [
  '말소리가 분명하거나 장면 변화가 눈에 띄는 영상이 auto 모드에서 가장 안정적입니다.',
  '긴 영상은 한 번에 처리하는 것보다 의미 단위로 잘라 여러 job으로 넣는 편이 품질 관리에 유리합니다.',
  '챕터 구성이 중요하거나 섹션 경계를 정확히 통제하고 싶다면 manual mode가 더 안전합니다.',
  'TTS를 켜지 않는 경우 결과 영상의 설명력은 원본 오디오와 caption 품질에 더 크게 의존합니다.',
];

const faqItems: FaqItem[] = [
  {
    question: '입력 영상 길이 제한이 있나요?',
    answer:
      '현재 코드에는 분 단위 하드 제한이 없습니다. 다만 긴 영상일수록 AI 프롬프트에 포함되는 transcript 일부만 사용되기 때문에 자동 생성 품질은 점차 떨어질 수 있습니다.',
  },
  {
    question: '원본 영상에 나레이션이나 음성이 거의 없으면 어떻게 되나요?',
    answer:
      '분석 단계는 계속 진행되지만 transcript와 caption 정보가 적어집니다. 이 경우 auto scenario는 scene, silence, duration 신호에 더 의존하게 되고 결과는 더 넓고 단순한 구조가 될 수 있습니다.',
  },
  {
    question: 'TTS나 vision QA가 실패하면 job 전체가 실패하나요?',
    answer:
      '아닙니다. 이 둘은 optional stage라 실패해도 메인 edit 생성과 렌더는 계속됩니다. 결과 페이지에는 가능한 artifact만 노출됩니다.',
  },
  {
    question: '최종 결과 페이지에서 무엇을 볼 수 있나요?',
    answer:
      '최종 MP4, 진행 로그, edit.json, thumbnail, QA 결과, voiceover manifest, clip-ranking artifact를 확인할 수 있습니다.',
  },
  {
    question: 'Full-dub 모드는 언제 사용하나요?',
    answer:
      '발표자의 음성을 깔끔한 TTS 나레이션으로 완전히 교체하고 싶을 때 사용합니다. 비네이티브 발표자의 데모 녹화, 다국어 더빙, 또는 일관된 톤의 제품 소개 영상을 만들 때 특히 유용합니다. --full-dub 플래그 하나로 전체 워크플로우가 자동화됩니다.',
  },
  {
    question: 'Full-dub에서 사용하는 TTS 엔진은 무엇인가요?',
    answer:
      '기본적으로 Microsoft Edge TTS(edge-tts)를 사용하며, API 키 없이 무료로 이용할 수 있습니다. 보이스는 en-US-AndrewMultilingualNeural(Warm, Confident 톤)이 기본이며 --tts-voice로 변경 가능합니다. OpenAI TTS도 지원합니다.',
  },
];

const artifacts = [
  { label: '핵심 미디어', value: 'input.mp4, final.mp4, thumbnail.jpg' },
  { label: '분석 산출물', value: 'transcript.json, scenes.json, silences.json, captions.json, clip-ranking.json' },
  { label: 'AI 산출물', value: 'scenario.json, edit.json, voiceover/manifest.json, tts_chunks.json, polished_chunks.json' },
  { label: '리뷰 산출물', value: 'qa.json, qa.heuristic.json, qa.vision.json' },
];

export function HowItWorksPage(): React.JSX.Element {
  const toneClassMap: Record<FlowNode['tone'], string> = {
    core: 'border-slate-200 bg-white text-slate-900',
    ai: 'border-[#d5d0ff] bg-[#f4f2ff] text-[#2d2463]',
    optional: 'border-[#eadfcb] bg-[#fff7eb] text-[#8a5a22]',
    output: 'border-[#f2c9cf] bg-[#fff2f4] text-[#8f1730]',
  };

  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden rounded-[28px] border border-slate-200 bg-[linear-gradient(145deg,#fdfcf8_0%,#f5efe3_52%,#ece4d6_100%)] shadow-[0_30px_90px_rgba(66,38,12,0.12)]">
        <div className="absolute inset-y-0 right-0 w-1/2 bg-[radial-gradient(circle_at_top,_rgba(200,16,46,0.12),_transparent_52%),radial-gradient(circle_at_bottom,_rgba(26,26,46,0.12),_transparent_48%)]" />
        <div className="relative grid gap-8 px-8 py-10 md:grid-cols-[1.5fr_0.9fr] md:px-10">
          <div className="space-y-5">
            <span className="inline-flex rounded-full border border-slate-300 bg-white/80 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-600">
              How It Works
            </span>
            <div className="space-y-3">
              <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-slate-900 md:text-5xl">
                영상 입력부터 분석, AI 편집, 렌더, QA까지 한 번에.
              </h1>
              <p className="max-w-2xl text-base leading-7 text-slate-600 md:text-lg">
                이 페이지는 현재 Remotion Video Gen에 실제로 붙어 있는 프로덕션 파이프라인을 설명합니다.
                optional stage인 TTS narration, clip ranking, vision QA까지 포함해 정리했습니다.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link
                to="/"
                className="inline-flex items-center justify-center rounded-full bg-[#1a1a2e] px-5 py-3 text-sm font-semibold text-white transition-transform hover:-translate-y-0.5"
              >
                새 작업 시작
              </Link>
              <Link
                to="/history"
                className="inline-flex items-center justify-center rounded-full border border-slate-300 bg-white/80 px-5 py-3 text-sm font-semibold text-slate-700 transition-colors hover:border-slate-400 hover:text-slate-900"
              >
                작업 히스토리 보기
              </Link>
            </div>
          </div>

          <div className="grid gap-3 self-start">
            {artifacts.map((artifact) => (
              <div
                key={artifact.label}
                className="rounded-[22px] border border-white/70 bg-white/70 p-4 shadow-[0_16px_40px_rgba(39,24,10,0.08)] backdrop-blur"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                  {artifact.label}
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-700">
                  {artifact.value}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {summaryCards.map((card) => (
          <article
            key={card.label}
            className="rounded-[24px] border border-slate-200 bg-white p-6 shadow-sm"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
              {card.label}
            </p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-900">
              {card.value}
            </h2>
            <p className="mt-3 text-sm leading-7 text-slate-600">{card.detail}</p>
          </article>
        ))}
      </section>

      <section className="rounded-[28px] border border-slate-200 bg-white p-8 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-500">
              Quick Diagram
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-900">
              한눈에 보는 파이프라인
            </h2>
          </div>
          <p className="max-w-2xl text-sm leading-7 text-slate-600">
            진한 흐름은 항상 실행되는 단계이고, 연한 색의 블록은 조건부로 붙는 AI 또는 optional stage입니다.
          </p>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          <span className="inline-flex rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700">
            Core
          </span>
          <span className="inline-flex rounded-full border border-[#d5d0ff] bg-[#f4f2ff] px-3 py-1 text-xs font-medium text-[#2d2463]">
            AI decision
          </span>
          <span className="inline-flex rounded-full border border-[#eadfcb] bg-[#fff7eb] px-3 py-1 text-xs font-medium text-[#8a5a22]">
            Optional stage
          </span>
          <span className="inline-flex rounded-full border border-[#f2c9cf] bg-[#fff2f4] px-3 py-1 text-xs font-medium text-[#8f1730]">
            Review / output
          </span>
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          {flowNodes.map((node, index) => (
            <div key={node.label} className="contents">
              <div
                className={`min-w-[160px] flex-1 rounded-[22px] border px-4 py-4 shadow-sm ${toneClassMap[node.tone]}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm font-semibold">{node.label}</p>
                  {node.ai && (
                    <span className="inline-flex rounded-full border border-current/20 bg-white/60 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em]">
                      AI
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs leading-5 opacity-80">{node.detail}</p>
              </div>
              {index < flowNodes.length - 1 && (
                <div className="flex items-center justify-center px-1 text-slate-300">
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M5 12h14m-5-5 5 5-5 5" />
                  </svg>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {usageItems.map((item) => (
          <article
            key={item.title}
            className="rounded-[24px] border border-slate-200 bg-white p-6 shadow-sm"
          >
            <h2 className="text-lg font-semibold text-slate-900">{item.title}</h2>
            <p className="mt-3 text-sm leading-7 text-slate-600">{item.body}</p>
          </article>
        ))}
      </section>

      <section className="rounded-[28px] border border-[#d7cfbf] bg-[#fffdf8] p-8 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.25em] text-[#8a5a22]">
              Usage Notes
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-900">
              업로드 전에 알아둘 운영 기준
            </h2>
          </div>
          <p className="max-w-2xl text-sm leading-7 text-slate-600">
            이 내용은 이상적인 설계가 아니라 현재 실제로 배포된 동작 기준입니다.
          </p>
        </div>
        <div className="mt-6 grid gap-3 md:grid-cols-2">
          {operatingRules.map((rule) => (
            <div
              key={rule}
              className="rounded-[22px] border border-[#eadfcb] bg-white px-5 py-4 text-sm leading-7 text-slate-700"
            >
              {rule}
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-[28px] border border-slate-200 bg-[linear-gradient(180deg,#ffffff_0%,#fbfbfd_100%)] p-8 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-500">
              Recommended Use
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-900">
              이런 입력에서 가장 잘 동작합니다
            </h2>
          </div>
          <p className="max-w-2xl text-sm leading-7 text-slate-600">
            아래 기준은 실패 여부가 아니라 결과 품질을 안정적으로 만들기 위한 운영 팁입니다.
          </p>
        </div>
        <div className="mt-6 grid gap-3 md:grid-cols-2">
          {recommendations.map((item) => (
            <div
              key={item}
              className="rounded-[22px] border border-slate-200 bg-white px-5 py-4 text-sm leading-7 text-slate-700"
            >
              {item}
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-500">
            Pipeline Breakdown
          </p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-900">
            단계별 프로세스
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-600">
            이 파이프라인은 의도적으로 층을 나눠 설계되어 있습니다. 안정적인 미디어 변환이 먼저 일어나고, AI 판단은 중간에, 리뷰 artifact는 렌더 이후에 붙습니다.
          </p>
        </div>

        <div className="space-y-4">
          {pipelineSteps.map((step) => (
            <article
              key={step.number}
              className="grid gap-4 rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm md:grid-cols-[110px_1fr]"
            >
              <div className="flex flex-col gap-3">
                <span className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-[#1a1a2e] text-lg font-semibold text-white shadow-[0_10px_24px_rgba(26,26,46,0.24)]">
                  {step.number}
                </span>
                <div className="flex flex-wrap gap-2">
                  <span className="inline-flex w-fit rounded-full border border-[#e6d9c4] bg-[#fbf4e7] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-[#8a5a22]">
                    {step.tag}
                  </span>
                  {step.ai && (
                    <span className="inline-flex w-fit rounded-full border border-[#d5d0ff] bg-[#f4f2ff] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-[#2d2463]">
                      AI
                    </span>
                  )}
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <h3 className="text-xl font-semibold text-slate-900">{step.title}</h3>
                  <p className="mt-2 text-sm leading-7 text-slate-600">
                    {step.description}
                  </p>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-[22px] border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                      Inputs
                    </p>
                    <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-700">
                      {step.inputs.map((item) => (
                        <li key={item} className="flex gap-2">
                          <span className="mt-2 h-1.5 w-1.5 rounded-full bg-[#c8102e]" />
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="rounded-[22px] border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                      Outputs
                    </p>
                    <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-700">
                      {step.outputs.map((item) => (
                        <li key={item} className="flex gap-2">
                          <span className="mt-2 h-1.5 w-1.5 rounded-full bg-[#1a1a2e]" />
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div className="rounded-[22px] border border-[#eadfcb] bg-[#fff8ee] p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8a5a22]">
                    Notes
                  </p>
                  <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-700">
                    {step.notes.map((item) => (
                      <li key={item} className="flex gap-2">
                        <span className="mt-2 h-1.5 w-1.5 rounded-full bg-[#8a5a22]" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-[28px] border border-slate-200 bg-white p-8 shadow-sm">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-500">
            FAQ
          </p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-900">
            자주 묻는 질문
          </h2>
        </div>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {faqItems.map((item) => (
            <article
              key={item.question}
              className="rounded-[22px] border border-slate-200 bg-slate-50 p-5"
            >
              <h3 className="text-base font-semibold text-slate-900">
                {item.question}
              </h3>
              <p className="mt-3 text-sm leading-7 text-slate-600">
                {item.answer}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-[28px] border border-[#1a1a2e] bg-[#1a1a2e] px-8 py-7 text-white shadow-[0_24px_60px_rgba(26,26,46,0.24)]">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-white/60">
              Current Product Surface
            </p>
            <h2 className="mt-2 text-2xl font-semibold">
              현재 제품은 이미 end-to-end 흐름을 갖고 있습니다.
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-7 text-white/80">
              영상만 업로드하는 zero-input 흐름도 scenario 생성, edit 생성, Remotion 렌더, thumbnail 추출, QA, 프론트엔드 리뷰까지 이미 연결되어 있습니다.
            </p>
          </div>
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-full bg-white px-5 py-3 text-sm font-semibold text-[#1a1a2e] transition-transform hover:-translate-y-0.5"
          >
            영상 만들기
          </Link>
        </div>
      </section>
    </div>
  );
}
