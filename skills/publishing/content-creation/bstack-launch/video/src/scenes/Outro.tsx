import {
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import { BRAND } from "../data/stack";

export const OutroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const mainSpring = spring({ frame, fps, config: { damping: 200 } });
  const ctaSpring = spring({
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
        padding: 80,
      }}
    >
      {/* Gradient accent */}
      <div
        style={{
          width: interpolate(mainSpring, [0, 1], [0, 200]),
          height: 4,
          background: `linear-gradient(90deg, ${BRAND.aiBlue}, ${BRAND.web3Green})`,
          borderRadius: 2,
          marginBottom: 40,
        }}
      />

      <div
        style={{
          opacity: mainSpring,
          transform: `translateY(${interpolate(mainSpring, [0, 1], [30, 0])}px)`,
          fontSize: 48,
          fontWeight: 800,
          color: BRAND.textPrimary,
          textAlign: "center",
          lineHeight: 1.2,
          letterSpacing: -2,
        }}
      >
        LLMs are controllers.
        {"\n"}
        Not chatbots.
      </div>

      <div
        style={{
          opacity: mainSpring,
          transform: `translateY(${interpolate(mainSpring, [0, 1], [20, 0])}px)`,
          fontSize: 24,
          color: BRAND.textSecondary,
          textAlign: "center",
          marginTop: 24,
          maxWidth: 600,
          lineHeight: 1.5,
        }}
      >
        37K lines of Rust. 31 crates. 16 skills. 5 products.
        {"\n"}
        One unified architecture.
      </div>

      {/* CTA */}
      <div
        style={{
          opacity: ctaSpring,
          transform: `scale(${ctaSpring})`,
          marginTop: 50,
          background: `linear-gradient(135deg, ${BRAND.aiBlue}, ${BRAND.web3Green})`,
          borderRadius: 14,
          padding: "16px 40px",
          fontSize: 22,
          fontWeight: 700,
          color: "white",
          letterSpacing: 0.5,
        }}
      >
        npx skills add broomva/bstack
      </div>

      {/* Brand */}
      <div
        style={{
          opacity: ctaSpring,
          marginTop: 30,
          fontSize: 16,
          color: BRAND.textSecondary,
          letterSpacing: 2,
        }}
      >
        BROOMVA
      </div>
    </div>
  );
};
