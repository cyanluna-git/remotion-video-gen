import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface HighlightRegionProps {
  region: { x: number; y: number; width: number; height: number };
  color?: string;
  borderColor?: string;
  borderWidth?: number;
}

export const HighlightRegion: React.FC<HighlightRegionProps> = ({
  region,
  color = "rgba(255, 255, 0, 0.3)",
  borderColor,
  borderWidth = 2,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const fadeInEnd = Math.round(fps * 0.2);
  const fadeOutStart = durationInFrames - Math.round(fps * 0.2);

  const fadeIn = interpolate(frame, [0, fadeInEnd], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const fadeOut = interpolate(
    frame,
    [fadeOutStart, durationInFrames],
    [1, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  const opacity = fadeIn * fadeOut;

  const resolvedBorderColor =
    borderColor ?? color.replace(/[\d.]+\)$/, "0.8)");

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          left: region.x,
          top: region.y,
          width: region.width,
          height: region.height,
          backgroundColor: color,
          border: `${borderWidth}px solid ${resolvedBorderColor}`,
          borderRadius: 4,
          opacity,
        }}
      />
    </AbsoluteFill>
  );
};
