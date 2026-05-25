import {
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import { BRAND, realWorldProofs } from "../data/content";

export const RealWorldScene: React.FC = () => {
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
        padding: 80,
      }}
    >
      <div
        style={{
          opacity: titleSpring,
          transform: `translateY(${interpolate(titleSpring, [0, 1], [30, 0])}px)`,
          fontSize: 44,
          fontWeight: 800,
          color: BRAND.textPrimary,
          textAlign: "center",
          letterSpacing: -1,
          marginBottom: 50,
        }}
      >
        En producción. No en teoría.
      </div>

      <div style={{ display: "flex", gap: 32 }}>
        {realWorldProofs.map((proof, i) => {
          const cardSpring = spring({
            frame: frame - 15 - i * 10,
            fps,
            config: { damping: 200 },
          });
          return (
            <div
              key={proof.label}
              style={{
                opacity: cardSpring,
                transform: `translateY(${interpolate(cardSpring, [0, 1], [40, 0])}px)`,
                background: BRAND.bgCard,
                border: `1px solid ${BRAND.glassBorder}`,
                borderRadius: 20,
                padding: "44px 40px",
                width: 420,
                textAlign: "center",
              }}
            >
              <div
                style={{
                  fontSize: 28,
                  fontWeight: 700,
                  color: BRAND.textPrimary,
                  marginBottom: 12,
                }}
              >
                {proof.label}
              </div>
              <div
                style={{
                  fontSize: 18,
                  color: BRAND.textSecondary,
                  lineHeight: 1.5,
                }}
              >
                {proof.detail}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
