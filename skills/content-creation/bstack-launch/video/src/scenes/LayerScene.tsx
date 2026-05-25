import {
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import type { StackLayer } from "../data/stack";
import { BRAND } from "../data/stack";

interface Props {
  layer: StackLayer;
}

export const LayerScene: React.FC<Props> = ({ layer }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enterSpring = spring({ frame, fps, config: { damping: 200 } });
  const labelSpring = spring({
    frame: frame - 8,
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
      {/* Layer color accent bar */}
      <div
        style={{
          width: interpolate(enterSpring, [0, 1], [0, 600]),
          height: 4,
          backgroundColor: layer.color,
          borderRadius: 2,
          marginBottom: 40,
        }}
      />

      {/* Layer label */}
      <div
        style={{
          opacity: labelSpring,
          transform: `translateY(${interpolate(labelSpring, [0, 1], [20, 0])}px)`,
          fontSize: 20,
          fontWeight: 600,
          color: layer.color,
          textTransform: "uppercase",
          letterSpacing: 4,
          marginBottom: 12,
        }}
      >
        {layer.label}
      </div>

      {/* Description */}
      <div
        style={{
          opacity: labelSpring,
          transform: `translateY(${interpolate(labelSpring, [0, 1], [20, 0])}px)`,
          fontSize: 36,
          fontWeight: 700,
          color: BRAND.textPrimary,
          textAlign: "center",
          lineHeight: 1.3,
          maxWidth: 800,
          marginBottom: 50,
        }}
      >
        {layer.description}
      </div>

      {/* Components grid */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 16,
          justifyContent: "center",
          maxWidth: 800,
        }}
      >
        {layer.components.map((comp, i) => {
          const chipSpring = spring({
            frame: frame - 15 - i * 5,
            fps,
            config: { damping: 20, stiffness: 200 },
          });
          return (
            <div
              key={comp}
              style={{
                opacity: chipSpring,
                transform: `scale(${chipSpring}) translateY(${interpolate(chipSpring, [0, 1], [10, 0])}px)`,
                background: `${layer.color}15`,
                border: `1px solid ${layer.color}40`,
                borderRadius: 10,
                padding: "14px 24px",
                fontSize: 22,
                fontWeight: 600,
                color: layer.color,
              }}
            >
              {comp}
            </div>
          );
        })}
      </div>
    </div>
  );
};
