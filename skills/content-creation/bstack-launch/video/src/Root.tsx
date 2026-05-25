import { Composition } from "remotion";
import { BstackLaunch } from "./BstackLaunch";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="BstackLaunch"
      component={BstackLaunch}
      durationInFrames={900}
      fps={30}
      width={1080}
      height={1080}
    />
  );
};
