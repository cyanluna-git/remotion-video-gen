import React from "react";
import { AbsoluteFill, Sequence, staticFile } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { wipe } from "@remotion/transitions/wipe";
import { ClipSegment } from "./components/ClipSegment";
import { TitleCard } from "./components/TitleCard";
import type { TransitionPresentation } from "@remotion/transitions";
import type { EditScript, TimelineEntry, Transition } from "./types/script";

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
): React.ReactNode {
  if (entry.type === "clip") {
    const rawSrc = sources[entry.source] ?? entry.source;
    const src = rawSrc.startsWith("http") ? rawSrc : staticFile(rawSrc);
    return (
      <ClipSegment
        src={src}
        sourceStartSec={entry.startSec}
        sourceEndSec={entry.endSec}
        overlays={entry.overlays}
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

export const ScriptDrivenVideo: React.FC<ScriptDrivenVideoProps> = ({
  script,
}) => {
  const { fps, timeline, sources } = script;

  if (hasAnyTransition(timeline)) {
    return (
      <AbsoluteFill style={{ backgroundColor: "#000" }}>
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
                {renderEntryContent(entry, sources)}
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
            {renderEntryContent(entry, sources)}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
