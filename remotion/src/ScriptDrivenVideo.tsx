import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { ClipSegment } from "./components/ClipSegment";
import { TitleCard } from "./components/TitleCard";
import type { EditScript, TimelineEntry } from "./types/script";

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

export const ScriptDrivenVideo: React.FC<ScriptDrivenVideoProps> = ({
  script,
}) => {
  const { fps, timeline, sources } = script;

  let currentFrame = 0;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {timeline.map((entry, index) => {
        const durationSec = getEntryDurationSec(entry);
        const durationInFrames = Math.ceil(durationSec * fps);
        const from = currentFrame;
        currentFrame += durationInFrames;

        if (entry.type === "clip") {
          const src = sources[entry.source] ?? entry.source;
          return (
            <Sequence
              key={index}
              from={from}
              durationInFrames={durationInFrames}
              name={`clip-${entry.source}`}
            >
              <ClipSegment
                src={src}
                sourceStartSec={entry.startSec}
                sourceEndSec={entry.endSec}
                overlays={entry.overlays}
              />
            </Sequence>
          );
        }

        if (entry.type === "title-card") {
          return (
            <Sequence
              key={index}
              from={from}
              durationInFrames={durationInFrames}
              name={`title-${index}`}
            >
              <TitleCard
                text={entry.text}
                subtitle={entry.subtitle}
                background={entry.background}
              />
            </Sequence>
          );
        }

        return null;
      })}
    </AbsoluteFill>
  );
};
