import {
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import { BRAND, coreInfra } from "../data/content";

export const InfraScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleSpring = spring({ frame, fps, config: { damping: 200 } });

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
      <div
        style={{
          opacity: titleSpring,
          transform: `translateY(${interpolate(titleSpring, [0, 1], [30, 0])}px)`,
          fontSize: 18,
          fontWeight: 600,
          color: BRAND.web3Green,
          textTransform: "uppercase",
          letterSpacing: 4,
          marginBottom: 12,
        }}
      >
        Life Agent OS
      </div>
      <div
        style={{
          opacity: titleSpring,
          transform: `translateY(${interpolate(titleSpring, [0, 1], [20, 0])}px)`,
          fontSize: 44,
          fontWeight: 800,
          color: BRAND.textPrimary,
          textAlign: "center",
          letterSpacing: -1,
          marginBottom: 50,
        }}
      >
        7 Rust Crates. Un runtime completo para agentes.
      </div>

      {/* Crate grid */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 20,
          justifyContent: "center",
          maxWidth: 1400,
        }}
      >
        {coreInfra.map((crate, i) => {
          const cardSpring = spring({
            frame: frame - 15 - i * 5,
            fps,
            config: { damping: 200 },
          });
          return (
            <div
              key={crate.name}
              style={{
                opacity: cardSpring,
                transform: `scale(${interpolate(cardSpring, [0, 1], [0.9, 1])}) translateY(${interpolate(cardSpring, [0, 1], [15, 0])}px)`,
                background: BRAND.bgCard,
                border: `1px solid ${BRAND.glassBorder}`,
                borderRadius: 16,
                padding: "24px 32px",
                width: 280,
                display: "flex",
                flexDirection: "column",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                <div
                  style={{
                    fontSize: 24,
                    fontWeight: 700,
                    color: BRAND.textPrimary,
                  }}
                >
                  {crate.name}
                </div>
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: BRAND.warning,
                    background: `${BRAND.warning}15`,
                    border: `1px solid ${BRAND.warning}30`,
                    borderRadius: 6,
                    padding: "2px 8px",
                  }}
                >
                  {crate.lang}
                </div>
              </div>
              <div
                style={{
                  fontSize: 16,
                  color: BRAND.textSecondary,
                  lineHeight: 1.4,
                }}
              >
                {crate.desc}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
