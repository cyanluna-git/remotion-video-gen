import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { CaptionClass } from "../types/script";

interface CaptionOverlayProps {
  text: string;
  position?: "top" | "bottom" | "center";
  variant?: CaptionClass;
}

export const CaptionOverlay: React.FC<CaptionOverlayProps> = ({
  text,
  position = "bottom",
  variant = "subtitle",
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const fadeInEnd = Math.round(fps * 0.3);
  const fadeOutStart = durationInFrames - Math.round(fps * 0.3);

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

  const containerStyle: React.CSSProperties = {
    position: "absolute",
    left: 0,
    right: 0,
    display: "flex",
    justifyContent: "center",
    opacity,
    pointerEvents: "none",
    ...(position === "top"
      ? { top: 80 }
      : position === "center"
        ? { top: 0, bottom: 0, alignItems: "center" }
        : { bottom: 80 }),
  };

  const textStyle: React.CSSProperties =
    variant === "announcement"
      ? {
          width: "100%",
          backgroundColor: "rgba(0, 0, 0, 0.75)",
          color: "#fff",
          fontSize: 48,
          fontWeight: 700,
          fontFamily: "Inter, -apple-system, sans-serif",
          textAlign: "center",
          padding: "16px 32px",
          lineHeight: 1.3,
        }
      : variant === "technical-term"
        ? {
            backgroundColor: "rgba(12, 18, 44, 0.88)",
            color: "#fef3c7",
            fontSize: 34,
            fontWeight: 700,
            fontFamily: "'SF Mono', 'Roboto Mono', monospace",
            textAlign: "center",
            padding: "12px 24px",
            borderRadius: 10,
            border: "2px solid rgba(251, 191, 36, 0.65)",
            boxShadow: "0 12px 32px rgba(15, 23, 42, 0.35)",
            letterSpacing: "0.02em",
            lineHeight: 1.3,
          }
        : {
            backgroundColor: "rgba(0, 0, 0, 0.75)",
            color: "#fff",
            fontSize: 36,
            fontWeight: 600,
            fontFamily: "Inter, -apple-system, sans-serif",
            textAlign: "center",
            padding: "12px 24px",
            borderRadius: 8,
            lineHeight: 1.3,
          };

  return (
    <div style={containerStyle}>
      <div style={textStyle}>{text}</div>
    </div>
  );
};
