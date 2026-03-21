import React from "react";
import { Composition } from "remotion";
import {
  ScriptDrivenVideo,
  type ScriptDrivenVideoProps,
} from "./ScriptDrivenVideo";
import type { EditScript } from "./types/script";

const DEFAULT_SCRIPT: EditScript = {
  version: "1.0",
  fps: 30,
  resolution: { width: 1920, height: 1080 },
  sources: {},
  timeline: [],
};

function getTimelineEntryDurationSec(
  entry: EditScript["timeline"][number],
): number {
  if (entry.type === "clip") {
    const rawDuration = entry.endSec - entry.startSec;
    return rawDuration / (entry.speed ?? 1);
  }
  return entry.durationSec;
}

function calculateTotalDurationInFrames(script: EditScript): number {
  const fps = script.fps;
  const totalSec = script.timeline.reduce(
    (acc, entry) => acc + getTimelineEntryDurationSec(entry),
    0,
  );

  const totalFrames = Math.ceil(totalSec * fps);
  return Math.max(totalFrames, 1);
}

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ScriptDrivenVideo"
        component={ScriptDrivenVideo}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={300}
        defaultProps={{ script: DEFAULT_SCRIPT }}
        calculateMetadata={({ props }) => {
          const durationInFrames = calculateTotalDurationInFrames(props.script);
          return {
            durationInFrames,
            fps: props.script.fps,
            width: props.script.resolution.width,
            height: props.script.resolution.height,
          };
        }}
      />
    </>
  );
};
