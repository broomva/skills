import {
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import { BRAND } from "../data/content";

export const NotVibeCoding: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const strikeSpring = spring({ frame, fps, config: { damping: 200 } });
  const newSpeciesSpring = spring({
    frame: frame - 20,
    fps,
    config: { damping: 200 },
  });
  const pillarsSpring = spring({
    frame: frame - 40,
    fps,
    config: { damping: 200 },
  });

  const strikeWidth = interpolate(strikeSpring, [0, 1], [0, 100]);

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
        padding: 80,
      }}
    >
      {/* "Vibe Coding" struck through */}
      <div
        style={{
          opacity: strikeSpring,
          transform: `translateY(${interpolate(strikeSpring, [0, 1], [30, 0])}px)`,
          fontSize: 52,
          fontWeight: 600,
          color: BRAND.textMuted,
          position: "relative",
          marginBottom: 20,
        }}
      >
        Vibe Coding
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: 0,
            width: `${strikeWidth}%`,
            height: 4,
            backgroundColor: "#FF3B30",
            borderRadius: 2,
          }}
        />
      </div>

      {/* New species */}
      <div
        style={{
          opacity: newSpeciesSpring,
          transform: `translateY(${interpolate(newSpeciesSpring, [0, 1], [40, 0])}px)`,
          fontSize: 72,
          fontWeight: 800,
          color: BRAND.textPrimary,
          textAlign: "center",
          lineHeight: 1.2,
          letterSpacing: -2,
          marginBottom: 50,
        }}
      >
        Una{" "}
        <span
          style={{
            background: BRAND.accentGradient,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          especie nueva
        </span>
      </div>

      {/* Two pillars */}
      <div style={{ display: "flex", gap: 40 }}>
        {[
          {
            label: "Harness Engineering",
            desc: "Flujos deterministas con gates de seguridad",
            icon: "⚙",
          },
          {
            label: "Agent Orchestration",
            desc: "Agentes que toman tickets y entregan PRs",
            icon: "🎼",
          },
        ].map((pillar, i) => {
          const cardSpring = spring({
            frame: frame - 45 - i * 10,
            fps,
            config: { damping: 200 },
          });
          return (
            <div
              key={pillar.label}
              style={{
                opacity: cardSpring,
                transform: `translateY(${interpolate(cardSpring, [0, 1], [30, 0])}px)`,
                background: BRAND.bgCard,
                border: `1px solid ${BRAND.glassBorder}`,
                borderRadius: 20,
                padding: "40px 48px",
                width: 420,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: 48, marginBottom: 16 }}>{pillar.icon}</div>
              <div
                style={{
                  fontSize: 26,
                  fontWeight: 700,
                  color: BRAND.textPrimary,
                  marginBottom: 8,
                }}
              >
                {pillar.label}
              </div>
              <div
                style={{
                  fontSize: 18,
                  color: BRAND.textSecondary,
                  lineHeight: 1.4,
                }}
              >
                {pillar.desc}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
