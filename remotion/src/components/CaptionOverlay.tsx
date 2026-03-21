import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface CaptionOverlayProps {
  text: string;
  position?: "top" | "bottom" | "center";
  style?: "subtitle" | "announcement";
}

export const CaptionOverlay: React.FC<CaptionOverlayProps> = ({
  text,
  position = "bottom",
  style = "subtitle",
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

  const positionStyle: React.CSSProperties =
    position === "top"
      ? { top: 80, left: 0, right: 0 }
      : position === "center"
        ? { top: 0, bottom: 0, left: 0, right: 0 }
        : { bottom: 80, left: 0, right: 0 };

  const containerAlign: React.CSSProperties =
    position === "center"
      ? {
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }
      : {
          display: "flex",
          justifyContent: "center",
        };

  const isAnnouncement = style === "announcement";

  const textStyle: React.CSSProperties = isAnnouncement
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
    <AbsoluteFill
      style={{
        ...positionStyle,
        ...containerAlign,
        opacity,
        pointerEvents: "none",
      }}
    >
      <div style={textStyle}>{text}</div>
    </AbsoluteFill>
  );
};
