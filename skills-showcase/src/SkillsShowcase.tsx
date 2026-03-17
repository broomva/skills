import { Series } from "remotion";
import { Intro } from "./scenes/Intro";
import { CategorySection } from "./scenes/CategorySection";
import { Outro } from "./scenes/Outro";
import { skillsByCategory } from "./data/skills";

// Timeline pacing (frames at 30fps):
// Intro: 120 frames (4s)
// 15 categories × 80 frames each = 1200 frames (40s)
// Outro: 120 frames (4s)
// Total: 1440 frames (48s)

const INTRO_DURATION = 120;
const CATEGORY_DURATION = 80;
const OUTRO_DURATION = 120;

export const SkillsShowcase: React.FC = () => {
  return (
    <Series>
      <Series.Sequence durationInFrames={INTRO_DURATION}>
        <Intro />
      </Series.Sequence>

      {skillsByCategory.map((cat) => (
        <Series.Sequence key={cat.id} durationInFrames={CATEGORY_DURATION}>
          <CategorySection
            label={cat.label}
            color={cat.color}
            skills={cat.skills}
            count={cat.count}
          />
        </Series.Sequence>
      ))}

      <Series.Sequence durationInFrames={OUTRO_DURATION}>
        <Outro />
      </Series.Sequence>
    </Series>
  );
};
