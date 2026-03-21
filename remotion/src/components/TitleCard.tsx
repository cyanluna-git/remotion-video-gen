import React from "react";
import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface TitleCardProps {
  text: string;
  subtitle?: string;
  background?: string;
}

export const TitleCard: React.FC<TitleCardProps> = ({
  text,
  subtitle,
  background,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleOpacity = spring({
    frame,
    fps,
    config: { damping: 20, stiffness: 80 },
  });

  const titleTranslateY = spring({
    frame,
    fps,
    config: { damping: 20, stiffness: 80 },
    from: 30,
    to: 0,
  });

  const subtitleDelayFrames = Math.round(0.2 * fps);
  const subtitleFrame = Math.max(0, frame - subtitleDelayFrames);

  const subtitleOpacity = spring({
    frame: subtitleFrame,
    fps,
    config: { damping: 20, stiffness: 80 },
  });

  const subtitleTranslateY = spring({
    frame: subtitleFrame,
    fps,
    config: { damping: 20, stiffness: 80 },
    from: 20,
    to: 0,
  });

  const backgroundStyle: React.CSSProperties = background
    ? background.includes("gradient")
      ? { backgroundImage: background }
      : { backgroundColor: background }
    : {
        background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)",
      };

  return (
    <AbsoluteFill
      style={{
        ...backgroundStyle,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div
        style={{
          opacity: titleOpacity,
          transform: `translateY(${titleTranslateY}px)`,
          color: "#fff",
          fontSize: 72,
          fontWeight: 800,
          textAlign: "center",
          maxWidth: "80%",
          lineHeight: 1.2,
        }}
      >
        {text}
      </div>
      {subtitle ? (
        <div
          style={{
            opacity: subtitleOpacity,
            transform: `translateY(${subtitleTranslateY}px)`,
            color: "rgba(255, 255, 255, 0.75)",
            fontSize: 36,
            fontWeight: 400,
            textAlign: "center",
            maxWidth: "70%",
            marginTop: 24,
            lineHeight: 1.4,
          }}
        >
          {subtitle}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
