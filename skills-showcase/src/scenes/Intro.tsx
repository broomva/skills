import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { totalSkills, totalCategories } from "../data/skills";

export const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Title entrance
  const titleSpring = spring({ frame, fps, config: { damping: 200 } });
  const titleY = interpolate(titleSpring, [0, 1], [60, 0]);
  const titleOpacity = interpolate(titleSpring, [0, 1], [0, 1]);

  // Subtitle entrance (delayed)
  const subtitleSpring = spring({
    frame,
    fps,
    config: { damping: 200 },
    delay: 12,
  });
  const subtitleOpacity = interpolate(subtitleSpring, [0, 1], [0, 1]);
  const subtitleY = interpolate(subtitleSpring, [0, 1], [40, 0]);

  // Stats line entrance
  const statsSpring = spring({
    frame,
    fps,
    config: { damping: 200 },
    delay: 24,
  });
  const statsOpacity = interpolate(statsSpring, [0, 1], [0, 1]);

  // Decorative line width
  const lineWidth = interpolate(frame, [8, 30], [0, 200], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0A0A0F",
        justifyContent: "center",
        alignItems: "center",
        padding: 80,
      }}
    >
      {/* Accent gradient orb */}
      <div
        style={{
          position: "absolute",
          width: 600,
          height: 600,
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(139,92,246,0.15) 0%, transparent 70%)",
          top: 140,
          left: 240,
        }}
      />

      {/* Title */}
      <div
        style={{
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontSize: 72,
            fontWeight: 800,
            color: "#FFFFFF",
            fontFamily: "system-ui, -apple-system, sans-serif",
            letterSpacing: -2,
            lineHeight: 1.1,
          }}
        >
          Composable
        </div>
        <div
          style={{
            fontSize: 72,
            fontWeight: 800,
            background: "linear-gradient(135deg, #8B5CF6, #06B6D4)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            fontFamily: "system-ui, -apple-system, sans-serif",
            letterSpacing: -2,
            lineHeight: 1.1,
          }}
        >
          Capabilities
        </div>
      </div>

      {/* Decorative line */}
      <div
        style={{
          width: lineWidth,
          height: 3,
          background: "linear-gradient(90deg, #8B5CF6, #06B6D4)",
          borderRadius: 2,
          marginTop: 32,
          marginBottom: 32,
        }}
      />

      {/* Subtitle */}
      <div
        style={{
          opacity: subtitleOpacity,
          transform: `translateY(${subtitleY}px)`,
          fontSize: 32,
          fontWeight: 400,
          color: "#A1A1AA",
          fontFamily: "system-ui, -apple-system, sans-serif",
          textAlign: "center",
          maxWidth: 700,
          lineHeight: 1.4,
        }}
      >
        One agent. {totalSkills} specialized skills.
        <br />
        Every layer of the stack.
      </div>

      {/* Stats pill */}
      <div
        style={{
          opacity: statsOpacity,
          marginTop: 48,
          display: "flex",
          gap: 24,
        }}
      >
        <StatPill value={String(totalSkills)} label="Skills" />
        <StatPill value={String(totalCategories)} label="Categories" />
      </div>
    </AbsoluteFill>
  );
};

const StatPill: React.FC<{ value: string; label: string }> = ({
  value,
  label,
}) => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      gap: 10,
      padding: "12px 24px",
      borderRadius: 100,
      border: "1px solid rgba(255,255,255,0.1)",
      backgroundColor: "rgba(255,255,255,0.05)",
    }}
  >
    <span
      style={{
        fontSize: 28,
        fontWeight: 700,
        color: "#8B5CF6",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      {value}
    </span>
    <span
      style={{
        fontSize: 18,
        color: "#71717A",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      {label}
    </span>
  </div>
);
