import {
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import { metrics, BRAND } from "../data/stack";

export const IntroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleSpring = spring({ frame, fps, config: { damping: 200 } });
  const subtitleSpring = spring({
    frame: frame - 15,
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
        padding: 60,
      }}
    >
      {/* Logo / Brand Mark */}
      <div
        style={{
          opacity: titleSpring,
          transform: `translateY(${interpolate(titleSpring, [0, 1], [40, 0])}px)`,
          marginBottom: 20,
        }}
      >
        <div
          style={{
            width: 80,
            height: 80,
            borderRadius: 20,
            background: `linear-gradient(135deg, ${BRAND.aiBlue}, ${BRAND.web3Green})`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 36,
            fontWeight: 800,
            color: "white",
            letterSpacing: -1,
          }}
        >
          B
        </div>
      </div>

      {/* Title */}
      <div
        style={{
          opacity: titleSpring,
          transform: `translateY(${interpolate(titleSpring, [0, 1], [40, 0])}px)`,
          fontSize: 72,
          fontWeight: 800,
          color: BRAND.textPrimary,
          letterSpacing: -3,
          textAlign: "center",
          lineHeight: 1.1,
        }}
      >
        Agent OS
      </div>

      {/* Subtitle */}
      <div
        style={{
          opacity: subtitleSpring,
          transform: `translateY(${interpolate(subtitleSpring, [0, 1], [30, 0])}px)`,
          fontSize: 28,
          color: BRAND.textSecondary,
          marginTop: 16,
          textAlign: "center",
          letterSpacing: 1,
        }}
      >
        The infrastructure layer for autonomous AI agents
      </div>

      {/* Metrics pills */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 16,
          marginTop: 50,
          justifyContent: "center",
        }}
      >
        {metrics.map((m, i) => {
          const pillSpring = spring({
            frame: frame - 30 - i * 6,
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
                borderRadius: 12,
                padding: "12px 20px",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
              }}
            >
              <span
                style={{
                  fontSize: 32,
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
