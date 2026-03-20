import { Composition } from "remotion";
import { SkillsShowcase } from "./SkillsShowcase";

// 30fps * 48s = 1440 frames (~48 seconds)
export const RemotionRoot = () => {
  return (
    <Composition
      id="SkillsShowcase"
      component={SkillsShowcase}
      durationInFrames={1520}
      fps={30}
      width={1080}
      height={1080}
    />
  );
};
