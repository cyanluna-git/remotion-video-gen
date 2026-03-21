import React from "react";
import { AbsoluteFill, OffthreadVideo } from "remotion";
import type { Overlay } from "../types/script";

interface ClipSegmentProps {
  src: string;
  sourceStartSec: number;
  sourceEndSec: number;
  overlays?: Overlay[];
}

export const ClipSegment: React.FC<ClipSegmentProps> = ({
  src,
  sourceStartSec,
  overlays,
}) => {
  return (
    <AbsoluteFill>
      <OffthreadVideo
        src={src}
        startFrom={Math.round(sourceStartSec * 30)}
        style={{ width: "100%", height: "100%" }}
      />
      {overlays?.map((overlay, index) => (
        <OverlayRenderer key={index} overlay={overlay} />
      ))}
    </AbsoluteFill>
  );
};

interface OverlayRendererProps {
  overlay: Overlay;
}

const OverlayRenderer: React.FC<OverlayRendererProps> = ({ overlay }) => {
  const positionStyles: Record<string, React.CSSProperties> = {
    top: { top: 40, left: 0, right: 0, textAlign: "center" },
    bottom: { bottom: 40, left: 0, right: 0, textAlign: "center" },
    center: {
      top: "50%",
      left: "50%",
      transform: "translate(-50%, -50%)",
      textAlign: "center",
    },
  };

  if (overlay.type === "caption" && overlay.text) {
    const position = overlay.position ?? "bottom";
    return (
      <div
        style={{
          position: "absolute",
          ...positionStyles[position],
          color: overlay.color ?? "#fff",
          fontSize: 42,
          fontWeight: 700,
          textShadow: "2px 2px 8px rgba(0,0,0,0.8)",
          padding: "8px 16px",
        }}
      >
        {overlay.text}
      </div>
    );
  }

  if (overlay.type === "highlight" && overlay.region) {
    return (
      <div
        style={{
          position: "absolute",
          left: overlay.region.x,
          top: overlay.region.y,
          width: overlay.region.width,
          height: overlay.region.height,
          border: `3px solid ${overlay.color ?? "#ff0"}`,
          borderRadius: 4,
          pointerEvents: "none",
        }}
      />
    );
  }

  return null;
};
