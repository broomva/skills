import {
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import { BRAND } from "../data/content";

export const OutroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const mainSpring = spring({ frame, fps, config: { damping: 200 } });
  const ctaSpring = spring({
    frame: frame - 15,
    fps,
    config: { damping: 200 },
  });
  const linksSpring = spring({
    frame: frame - 30,
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
      {/* Background glow */}
      <div
        style={{
          position: "absolute",
          width: 800,
          height: 800,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${BRAND.aiBlue}10, transparent 70%)`,
          filter: "blur(100px)",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
        }}
      />

      {/* Gradient bar */}
      <div
        style={{
          width: interpolate(mainSpring, [0, 1], [0, 300]),
          height: 4,
          background: BRAND.accentGradient,
          borderRadius: 2,
          marginBottom: 40,
        }}
      />

      {/* Headline */}
      <div
        style={{
          opacity: mainSpring,
          transform: `translateY(${interpolate(mainSpring, [0, 1], [30, 0])}px)`,
          fontSize: 56,
          fontWeight: 800,
          color: BRAND.textPrimary,
          textAlign: "center",
          lineHeight: 1.2,
          letterSpacing: -2,
        }}
      >
        Todo es Open Source.
        <br />
        Todo está documentado.
      </div>

      {/* CTA */}
      <div
        style={{
          opacity: ctaSpring,
          transform: `scale(${ctaSpring})`,
          marginTop: 40,
          background: BRAND.accentGradient,
          borderRadius: 14,
          padding: "16px 44px",
          fontSize: 22,
          fontWeight: 700,
          color: "white",
          letterSpacing: 0.5,
        }}
      >
        broomva.tech
      </div>

      {/* Links row */}
      <div
        style={{
          opacity: linksSpring,
          display: "flex",
          gap: 40,
          marginTop: 30,
        }}
      >
        {[
          "github.com/broomva/bstack",
          "github.com/broomva",
          "x.com/broomva_tech",
        ].map((link) => (
          <div
            key={link}
            style={{
              fontSize: 16,
              color: BRAND.textSecondary,
              fontFamily: '"SF Mono", "Fira Code", monospace',
            }}
          >
            {link}
          </div>
        ))}
      </div>

      {/* Brand */}
      <div
        style={{
          opacity: linksSpring,
          marginTop: 30,
          fontSize: 14,
          color: BRAND.textMuted,
          letterSpacing: 3,
          textTransform: "uppercase",
        }}
      >
        Carlos D. Escobar-Valbuena
      </div>
    </div>
  );
};
