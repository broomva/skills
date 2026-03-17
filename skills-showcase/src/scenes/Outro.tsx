import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { totalSkills, totalCategories } from "../data/skills";

export const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Metric line entrance
  const metricSpring = spring({ frame, fps, config: { damping: 200 } });
  const metricOpacity = interpolate(metricSpring, [0, 1], [0, 1]);
  const metricY = interpolate(metricSpring, [0, 1], [50, 0]);

  // Tagline entrance
  const tagSpring = spring({
    frame,
    fps,
    config: { damping: 200 },
    delay: 15,
  });
  const tagOpacity = interpolate(tagSpring, [0, 1], [0, 1]);
  const tagY = interpolate(tagSpring, [0, 1], [40, 0]);

  // CTA entrance
  const ctaSpring = spring({
    frame,
    fps,
    config: { damping: 15, stiffness: 200 },
    delay: 30,
  });
  const ctaScale = interpolate(ctaSpring, [0, 1], [0.8, 1]);
  const ctaOpacity = interpolate(ctaSpring, [0, 1], [0, 1]);

  // Decorative line
  const lineWidth = interpolate(frame, [5, 25], [0, 300], {
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
      {/* Background gradient orbs */}
      <div
        style={{
          position: "absolute",
          width: 500,
          height: 500,
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(139,92,246,0.12) 0%, transparent 70%)",
          bottom: 100,
          left: 100,
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 400,
          height: 400,
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(6,182,212,0.1) 0%, transparent 70%)",
          top: 150,
          right: 150,
        }}
      />

      {/* Summary metric */}
      <div
        style={{
          opacity: metricOpacity,
          transform: `translateY(${metricY}px)`,
          textAlign: "center",
        }}
      >
        <span
          style={{
            fontSize: 96,
            fontWeight: 800,
            background: "linear-gradient(135deg, #8B5CF6, #06B6D4, #10B981)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            fontFamily: "system-ui, -apple-system, sans-serif",
            letterSpacing: -3,
          }}
        >
          {totalSkills}
        </span>
        <div
          style={{
            fontSize: 28,
            fontWeight: 500,
            color: "#71717A",
            fontFamily: "system-ui, -apple-system, sans-serif",
            marginTop: 4,
          }}
        >
          skills across {totalCategories} domains
        </div>
      </div>

      {/* Decorative line */}
      <div
        style={{
          width: lineWidth,
          height: 2,
          background:
            "linear-gradient(90deg, transparent, rgba(139,92,246,0.5), transparent)",
          marginTop: 40,
          marginBottom: 40,
        }}
      />

      {/* Tagline */}
      <div
        style={{
          opacity: tagOpacity,
          transform: `translateY(${tagY}px)`,
          fontSize: 38,
          fontWeight: 600,
          color: "#FFFFFF",
          fontFamily: "system-ui, -apple-system, sans-serif",
          textAlign: "center",
          letterSpacing: -1,
          lineHeight: 1.3,
          maxWidth: 700,
        }}
      >
        Not just an assistant.
        <br />
        <span style={{ color: "#8B5CF6" }}>A full engineering team.</span>
      </div>

      {/* CTA */}
      <div
        style={{
          opacity: ctaOpacity,
          transform: `scale(${ctaScale})`,
          marginTop: 48,
          padding: "16px 40px",
          borderRadius: 100,
          background: "linear-gradient(135deg, #8B5CF6, #6D28D9)",
          fontSize: 22,
          fontWeight: 600,
          color: "#FFFFFF",
          fontFamily: "system-ui, -apple-system, sans-serif",
        }}
      >
        Try Claude Code →
      </div>
    </AbsoluteFill>
  );
};
