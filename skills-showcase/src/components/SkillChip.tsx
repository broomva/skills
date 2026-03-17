import {
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type SkillChipProps = {
  label: string;
  color: string;
  delay: number;
};

export const SkillChip: React.FC<SkillChipProps> = ({
  label,
  color,
  delay,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const entrance = spring({
    frame,
    fps,
    config: { damping: 20, stiffness: 200 },
    delay,
  });

  const scale = interpolate(entrance, [0, 1], [0.7, 1]);
  const opacity = interpolate(entrance, [0, 1], [0, 1]);

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 16px",
        borderRadius: 8,
        backgroundColor: `${color}18`,
        border: `1px solid ${color}40`,
        transform: `scale(${scale})`,
        opacity,
      }}
    >
      <div
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          backgroundColor: color,
        }}
      />
      <span
        style={{
          fontSize: 16,
          fontWeight: 500,
          color: "#E4E4E7",
          fontFamily: "system-ui, -apple-system, sans-serif",
          whiteSpace: "nowrap",
        }}
      >
        {label}
      </span>
    </div>
  );
};
