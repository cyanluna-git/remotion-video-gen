import React from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  Sequence,
  useVideoConfig,
} from "remotion";
import type { Overlay } from "../types/script";
import { CaptionOverlay } from "./CaptionOverlay";
import { HighlightRegion } from "./HighlightRegion";

interface ClipSegmentProps {
  src: string;
  sourceStartSec: number;
  sourceEndSec: number;
  overlays?: Overlay[];
  volume?: number;
}

export const ClipSegment: React.FC<ClipSegmentProps> = ({
  src,
  sourceStartSec,
  overlays,
  volume,
}) => {
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill>
      <OffthreadVideo
        src={src}
        startFrom={Math.round(sourceStartSec * fps)}
        volume={volume ?? 1}
        style={{ width: "100%", height: "100%" }}
      />
      {overlays?.map((overlay, index) => {
        const fromFrame = Math.round(overlay.startSec * fps);
        const durationFrames = Math.round(overlay.durationSec * fps);

        return (
          <Sequence
            key={index}
            from={fromFrame}
            durationInFrames={durationFrames}
          >
            <OverlayRenderer overlay={overlay} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

interface OverlayRendererProps {
  overlay: Overlay;
}

const OverlayRenderer: React.FC<OverlayRendererProps> = ({ overlay }) => {
  if (overlay.type === "caption" && overlay.text) {
    return (
      <CaptionOverlay
        text={overlay.text}
        position={overlay.position ?? "bottom"}
        variant={overlay.captionClass ?? "subtitle"}
      />
    );
  }

  if (overlay.type === "highlight" && overlay.region) {
    return (
      <HighlightRegion
        region={overlay.region}
        color={overlay.color ?? "rgba(255, 255, 0, 0.3)"}
      />
    );
  }

  return null;
};
