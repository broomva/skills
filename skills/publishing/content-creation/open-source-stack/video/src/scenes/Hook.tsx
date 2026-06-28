import {
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import { BRAND, metrics } from "../data/content";

export const HookScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const badgeSpring = spring({ frame, fps, config: { damping: 200 } });
  const titleSpring = spring({
    frame: frame - 10,
    fps,
    config: { damping: 200 },
  });
  const subtitleSpring = spring({
    frame: frame - 20,
    fps,
    config: { damping: 200 },
  });

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: BRAND.bgDark,
        position: "relative",
      }}
    >
      {/* Subtle gradient orb background */}
      <div
        style={{
          position: "absolute",
          width: 600,
          height: 600,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${BRAND.aiBlue}15, transparent 70%)`,
          filter: "blur(80px)",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
        }}
      />

      {/* Open Source badge */}
      <div
        style={{
          opacity: badgeSpring,
          transform: `scale(${badgeSpring})`,
          background: `${BRAND.aiBlue}20`,
          border: `1px solid ${BRAND.aiBlue}50`,
          borderRadius: 100,
          padding: "10px 32px",
          fontSize: 20,
          fontWeight: 600,
          color: BRAND.aiBlue,
          letterSpacing: 3,
          textTransform: "uppercase",
          marginBottom: 30,
        }}
      >
        Open Source
      </div>

      {/* Main title */}
      <div
        style={{
          opacity: titleSpring,
          transform: `translateY(${interpolate(titleSpring, [0, 1], [50, 0])}px)`,
          fontSize: 80,
          fontWeight: 800,
          color: BRAND.textPrimary,
          textAlign: "center",
          lineHeight: 1.1,
          letterSpacing: -3,
          maxWidth: 1400,
        }}
      >
        Mi Stack Completo para
        <br />
        <span
          style={{
            background: BRAND.accentGradient,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Desarrollo Autónomo
        </span>
      </div>

      {/* Subtitle */}
      <div
        style={{
          opacity: subtitleSpring,
          transform: `translateY(${interpolate(subtitleSpring, [0, 1], [30, 0])}px)`,
          fontSize: 28,
          color: BRAND.textSecondary,
          marginTop: 24,
          textAlign: "center",
          letterSpacing: 1,
        }}
      >
        El playbook para crear sistemas de forma escalable y automática
      </div>

      {/* Metrics row */}
      <div
        style={{
          display: "flex",
          gap: 24,
          marginTop: 50,
        }}
      >
        {metrics.map((m, i) => {
          const pillSpring = spring({
            frame: frame - 35 - i * 5,
            fps,
            config: { damping: 200 },
          });
          return (
            <div
              key={m.label}
              style={{
                opacity: pillSpring,
                transform: `scale(${pillSpring})`,
                background: BRAND.bgCard,
                border: `1px solid ${BRAND.glassBorder}`,
                borderRadius: 14,
                padding: "14px 28px",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
              }}
            >
              <span
                style={{
                  fontSize: 36,
                  fontWeight: 700,
                  color: BRAND.aiBlue,
                }}
              >
                {m.value}
              </span>
              <span
                style={{
                  fontSize: 14,
                  color: BRAND.textSecondary,
                  marginTop: 4,
                }}
              >
                {m.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
