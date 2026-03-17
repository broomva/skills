import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { SkillChip } from "../components/SkillChip";
import type { Skill } from "../data/skills";

type CategorySectionProps = {
  label: string;
  color: string;
  skills: Skill[];
  count: number;
};

export const CategorySection: React.FC<CategorySectionProps> = ({
  label,
  color,
  skills: categorySkills,
  count,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Category label entrance
  const labelSpring = spring({ frame, fps, config: { damping: 200 } });
  const labelX = interpolate(labelSpring, [0, 1], [-80, 0]);
  const labelOpacity = interpolate(labelSpring, [0, 1], [0, 1]);

  // Count badge
  const countSpring = spring({
    frame,
    fps,
    config: { damping: 15, stiffness: 200 },
    delay: 6,
  });
  const countScale = interpolate(countSpring, [0, 1], [0, 1]);

  // Accent bar width
  const barWidth = interpolate(frame, [0, 20], [0, 120], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0A0A0F",
        padding: 72,
        justifyContent: "center",
      }}
    >
      {/* Subtle background glow */}
      <div
        style={{
          position: "absolute",
          width: 500,
          height: 500,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${color}12 0%, transparent 70%)`,
          top: 100,
          right: -100,
        }}
      />

      {/* Accent bar */}
      <div
        style={{
          width: barWidth,
          height: 4,
          backgroundColor: color,
          borderRadius: 2,
          marginBottom: 24,
        }}
      />

      {/* Category label + count */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          marginBottom: 40,
          opacity: labelOpacity,
          transform: `translateX(${labelX}px)`,
        }}
      >
        <div
          style={{
            fontSize: 44,
            fontWeight: 700,
            color: "#FFFFFF",
            fontFamily: "system-ui, -apple-system, sans-serif",
            letterSpacing: -1,
          }}
        >
          {label}
        </div>
        <div
          style={{
            transform: `scale(${countScale})`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 40,
            height: 40,
            borderRadius: "50%",
            backgroundColor: `${color}25`,
            border: `2px solid ${color}`,
          }}
        >
          <span
            style={{
              fontSize: 18,
              fontWeight: 700,
              color,
              fontFamily: "system-ui, -apple-system, sans-serif",
            }}
          >
            {count}
          </span>
        </div>
      </div>

      {/* Skill chips - staggered grid */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 12,
          maxWidth: 900,
        }}
      >
        {categorySkills.map((skill, i) => (
          <SkillChip
            key={skill.slug}
            label={skill.shortDescription}
            color={color}
            delay={10 + i * 3}
          />
        ))}
      </div>
    </AbsoluteFill>
  );
};
