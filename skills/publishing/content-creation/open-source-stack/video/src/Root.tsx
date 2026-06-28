import { Composition } from "remotion";
import { OpenSourceStack } from "./OpenSourceStack";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="OpenSourceStack"
      component={OpenSourceStack}
      durationInFrames={750}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
