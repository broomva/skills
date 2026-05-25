import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";

interface TitleCardProps {
  title: string;
  primaryColor: string;
  secondaryColor: string;
  /** When true, renders as an end card with fade-out instead of entrance */
  isEndCard?: boolean;
}

/**
 * TitleCard — full-screen opening or closing card.
 *
 * Features:
 * - Gradient background from brand colors
 * - Spring animation for text entrance
 * - 2-second duration (set by parent Sequence)
 * - End card variant with a "thank you" subtitle
 */
export const TitleCard: React.FC<TitleCardProps> = ({
  title,
  primaryColor,
  secondaryColor,
  isEndCard = false,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Spring-driven entrance
  const entranceProgress = spring({
    frame,
    fps,
    config: {
      damping: 18,
      stiffness: 60,
      mass: 0.7,
    },
  });

  // Fade out near the end of the sequence
  const exitStart = durationInFrames - Math.round(fps * 0.4);
  const fadeOut = interpolate(
    frame,
    [exitStart, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const opacity = Math.min(entranceProgress, fadeOut);

  // Title slides up on entrance
  const titleTranslateY = interpolate(entranceProgress, [0, 1], [40, 0]);
  const titleScale = interpolate(entranceProgress, [0, 1], [0.92, 1]);

  // Subtitle (end card only) arrives slightly delayed
  const subtitleProgress = spring({
    frame: Math.max(0, frame - 6),
    fps,
    config: {
      damping: 20,
      stiffness: 80,
      mass: 0.6,
    },
  });

  const subtitleTranslateY = interpolate(subtitleProgress, [0, 1], [20, 0]);

  // Decorative line grows from center
  const lineWidth = interpolate(entranceProgress, [0, 1], [0, 120]);

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(135deg, ${secondaryColor} 0%, ${primaryColor}40 50%, ${secondaryColor} 100%)`,
        justifyContent: "center",
        alignItems: "center",
        opacity,
      }}
    >
      {/* Decorative accent line above title */}
      <div
        style={{
          width: lineWidth,
          height: 3,
          backgroundColor: primaryColor,
          borderRadius: 2,
          marginBottom: 28,
          boxShadow: `0 0 20px ${primaryColor}80`,
        }}
      />

      {/* Title */}
      <h1
        style={{
          color: "#ffffff",
          fontSize: isEndCard ? 56 : 64,
          fontFamily: "'Inter', 'SF Pro Display', system-ui, sans-serif",
          fontWeight: 700,
          textAlign: "center",
          maxWidth: "80%",
          lineHeight: 1.2,
          margin: 0,
          transform: `translateY(${titleTranslateY}px) scale(${titleScale})`,
          textShadow: "0 4px 20px rgba(0,0,0,0.4)",
          letterSpacing: -0.5,
        }}
      >
        {title}
      </h1>

      {/* Subtitle — end card only */}
      {isEndCard && (
        <p
          style={{
            color: "#ffffff90",
            fontSize: 28,
            fontFamily: "'Inter', 'SF Pro Display', system-ui, sans-serif",
            fontWeight: 400,
            marginTop: 20,
            opacity: subtitleProgress,
            transform: `translateY(${subtitleTranslateY}px)`,
            letterSpacing: 2,
            textTransform: "uppercase",
          }}
        >
          Thanks for watching
        </p>
      )}

      {/* Decorative line below */}
      <div
        style={{
          width: lineWidth * 0.6,
          height: 2,
          backgroundColor: `${primaryColor}60`,
          borderRadius: 2,
          marginTop: isEndCard ? 32 : 24,
        }}
      />
    </AbsoluteFill>
  );
};
