import {
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import { BRAND, stackLayers } from "../data/content";

export const StackLayers: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleSpring = spring({ frame, fps, config: { damping: 200 } });

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        backgroundColor: BRAND.bgDark,
        padding: 60,
      }}
    >
      {/* Left side — title */}
      <div
        style={{
          flex: "0 0 480px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          paddingRight: 40,
        }}
      >
        <div
          style={{
            opacity: titleSpring,
            transform: `translateX(${interpolate(titleSpring, [0, 1], [-40, 0])}px)`,
          }}
        >
          <div
            style={{
              fontSize: 18,
              fontWeight: 600,
              color: BRAND.aiBlue,
              textTransform: "uppercase",
              letterSpacing: 4,
              marginBottom: 16,
            }}
          >
            bstack
          </div>
          <div
            style={{
              fontSize: 52,
              fontWeight: 800,
              color: BRAND.textPrimary,
              lineHeight: 1.15,
              letterSpacing: -2,
            }}
          >
            24 Skills
            <br />
            7 Capas
          </div>
          <div
            style={{
              fontSize: 20,
              color: BRAND.textSecondary,
              marginTop: 16,
              lineHeight: 1.5,
            }}
          >
            Un solo comando:
          </div>
          <div
            style={{
              fontSize: 18,
              fontFamily: '"SF Mono", "Fira Code", "JetBrains Mono", monospace',
              color: BRAND.web3Green,
              marginTop: 8,
              background: BRAND.bgCard,
              border: `1px solid ${BRAND.glassBorder}`,
              borderRadius: 10,
              padding: "10px 16px",
              display: "inline-block",
            }}
          >
            npx skills add broomva/bstack
          </div>
        </div>
      </div>

      {/* Right side — layer stack */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: 10,
        }}
      >
        {stackLayers.map((layer, i) => {
          const layerSpring = spring({
            frame: frame - 15 - i * 8,
            fps,
            config: { damping: 200 },
          });

          return (
            <div
              key={layer.label}
              style={{
                opacity: layerSpring,
                transform: `translateX(${interpolate(layerSpring, [0, 1], [60, 0])}px)`,
                display: "flex",
                alignItems: "center",
                background: BRAND.bgCard,
                border: `1px solid ${layer.color}30`,
                borderLeft: `4px solid ${layer.color}`,
                borderRadius: 12,
                padding: "14px 24px",
              }}
            >
              {/* Layer label */}
              <div
                style={{
                  width: 180,
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                }}
              >
                <span style={{ fontSize: 22 }}>{layer.emoji}</span>
                <span
                  style={{
                    fontSize: 20,
                    fontWeight: 700,
                    color: layer.color,
                  }}
                >
                  {layer.label}
                </span>
              </div>

              {/* Skills */}
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                {layer.skills.map((skill) => (
                  <div
                    key={skill}
                    style={{
                      background: `${layer.color}12`,
                      border: `1px solid ${layer.color}30`,
                      borderRadius: 8,
                      padding: "6px 14px",
                      fontSize: 15,
                      fontWeight: 500,
                      color: BRAND.textPrimary,
                    }}
                  >
                    {skill}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
