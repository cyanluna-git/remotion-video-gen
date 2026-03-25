import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { wipe } from "@remotion/transitions/wipe";
import { ClipSegment } from "./components/ClipSegment";
import { TitleCard } from "./components/TitleCard";
import type { TransitionPresentation } from "@remotion/transitions";
import type {
  AudioConfig,
  EditScript,
  TimelineEntry,
  Transition,
  VoiceoverTrack,
} from "./types/script";

export interface ScriptDrivenVideoProps extends Record<string, unknown> {
  script: EditScript;
}

function getEntryDurationSec(entry: TimelineEntry): number {
  if (entry.type === "clip") {
    const rawDuration = entry.endSec - entry.startSec;
    return rawDuration / (entry.speed ?? 1);
  }
  return entry.durationSec;
}

function getPresentation(
  transition: Transition,
): TransitionPresentation<Record<string, unknown>> | undefined {
  switch (transition.type) {
    case "fade":
      return fade();
    case "slide-left":
      return slide({ direction: "from-left" });
    case "slide-right":
      return slide({ direction: "from-right" });
    case "wipe":
      return wipe();
    case "none":
      return undefined;
  }
}

function hasAnyTransition(timeline: TimelineEntry[]): boolean {
  return timeline.some(
    (entry) => entry.transition && entry.transition.type !== "none",
  );
}

function renderEntryContent(
  entry: TimelineEntry,
  sources: Record<string, string>,
  originalAudioVolume: number,
): React.ReactNode {
  if (entry.type === "clip") {
    const src = resolveMediaSrc(sources[entry.source] ?? entry.source);
    return (
      <ClipSegment
        src={src}
        sourceStartSec={entry.startSec}
        sourceEndSec={entry.endSec}
        overlays={entry.overlays}
        volume={originalAudioVolume}
      />
    );
  }

  if (entry.type === "title-card") {
    return (
      <TitleCard
        text={entry.text}
        subtitle={entry.subtitle}
        background={entry.background}
      />
    );
  }

  return null;
}

function resolveMediaSrc(src: string): string {
  return src.startsWith("http") ? src : staticFile(src);
}

function normalizeVoiceoverTracks(audio?: AudioConfig): VoiceoverTrack[] {
  const voiceover = audio?.voiceover;
  if (!voiceover) {
    return [];
  }
  if ("tracks" in voiceover) {
    return voiceover.tracks;
  }
  return [
    {
      src: voiceover.src,
      volume: voiceover.volume,
      startSec: 0,
      label: "legacy-voiceover",
    },
  ];
}

function getOriginalAudioVolume(audio: AudioConfig | undefined): number {
  const baseVolume = audio?.originalAudio?.volume ?? 1;
  if (baseVolume === 0) {
    return 0;
  }
  const voiceoverTracks = normalizeVoiceoverTracks(audio);
  if (voiceoverTracks.length === 0) {
    return baseVolume;
  }

  const voiceover = audio?.voiceover;
  if (voiceover && "tracks" in voiceover) {
    return Math.min(baseVolume, voiceover.mix?.duckedVolume ?? 0.35);
  }

  return Math.min(baseVolume, 0.35);
}

function getTotalDurationInFrames(script: EditScript): number {
  const totalSequenceSec = script.timeline.reduce(
    (acc, entry) => acc + getEntryDurationSec(entry),
    0,
  );
  const totalTransitionSec = script.timeline.reduce((acc, entry, index) => {
    if (index > 0 && entry.transition && entry.transition.type !== "none") {
      return acc + entry.transition.durationSec;
    }
    return acc;
  }, 0);

  return Math.max(Math.ceil((totalSequenceSec - totalTransitionSec) * script.fps), 1);
}

function renderAudioLayers(
  audio: AudioConfig | undefined,
  fps: number,
  totalDurationInFrames: number,
): React.ReactNode {
  if (!audio) {
    return null;
  }

  const layers: React.ReactNode[] = [];

  if (audio.backgroundMusic?.src) {
    layers.push(
      <Audio
        key="bgm"
        src={resolveMediaSrc(audio.backgroundMusic.src)}
        volume={audio.backgroundMusic.volume}
      />,
    );
  }

  normalizeVoiceoverTracks(audio).forEach((track, index) => {
    const from = Math.max(0, Math.round((track.startSec ?? 0) * fps));
    const offsetFrames = Math.max(0, Math.round((track.offsetSec ?? 0) * fps));
    const durationInFrames = Math.max(totalDurationInFrames - from, 1);

    layers.push(
      <Sequence
        key={`voiceover-${track.id ?? index}`}
        from={from}
        durationInFrames={durationInFrames}
      >
        <Audio
          src={resolveMediaSrc(track.src)}
          startFrom={offsetFrames}
          volume={track.volume ?? 1}
          playbackRate={track.playbackRate ?? 1}
        />
      </Sequence>,
    );
  });

  return layers;
}

export const ScriptDrivenVideo: React.FC<ScriptDrivenVideoProps> = ({
  script,
}) => {
  const { fps, timeline, sources, audio } = script;
  const originalAudioVolume = getOriginalAudioVolume(audio);
  const totalDurationInFrames = getTotalDurationInFrames(script);

  if (hasAnyTransition(timeline)) {
    return (
      <AbsoluteFill style={{ backgroundColor: "#000" }}>
        {renderAudioLayers(audio, fps, totalDurationInFrames)}
        <TransitionSeries>
          {timeline.flatMap((entry, index) => {
            const durationSec = getEntryDurationSec(entry);
            const durationInFrames = Math.ceil(durationSec * fps);
            const elements: React.ReactNode[] = [];

            if (
              index > 0 &&
              entry.transition &&
              entry.transition.type !== "none"
            ) {
              const presentation = getPresentation(entry.transition);
              const transitionDurationInFrames = Math.ceil(
                entry.transition.durationSec * fps,
              );
              elements.push(
                <TransitionSeries.Transition
                  key={`transition-${index}`}
                  presentation={presentation}
                  timing={linearTiming({
                    durationInFrames: transitionDurationInFrames,
                  })}
                />,
              );
            }

            const name =
              entry.type === "clip"
                ? `clip-${entry.source}`
                : `title-${index}`;

            elements.push(
              <TransitionSeries.Sequence
                key={`seq-${index}`}
                durationInFrames={durationInFrames}
                name={name}
              >
                {renderEntryContent(entry, sources, originalAudioVolume)}
              </TransitionSeries.Sequence>,
            );

            return elements;
          })}
        </TransitionSeries>
      </AbsoluteFill>
    );
  }

  let currentFrame = 0;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {renderAudioLayers(audio, fps, totalDurationInFrames)}
      {timeline.map((entry, index) => {
        const durationSec = getEntryDurationSec(entry);
        const durationInFrames = Math.ceil(durationSec * fps);
        const from = currentFrame;
        currentFrame += durationInFrames;

        const name =
          entry.type === "clip" ? `clip-${entry.source}` : `title-${index}`;

        return (
          <Sequence
            key={index}
            from={from}
            durationInFrames={durationInFrames}
            name={name}
          >
            {renderEntryContent(entry, sources, originalAudioVolume)}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
