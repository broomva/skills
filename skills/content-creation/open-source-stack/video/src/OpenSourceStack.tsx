import { Series } from "remotion";
import { HookScene } from "./scenes/Hook";
import { NotVibeCoding } from "./scenes/NotVibeCoding";
import { StackLayers } from "./scenes/StackLayers";
import { InfraScene } from "./scenes/Infra";
import { RealWorldScene } from "./scenes/RealWorld";
import { OutroScene } from "./scenes/Outro";
import { BRAND } from "./data/content";

const HOOK_DURATION = 105; // 3.5s
const NOT_VIBE_DURATION = 105; // 3.5s
const STACK_DURATION = 210; // 7s
const INFRA_DURATION = 120; // 4s
const REAL_WORLD_DURATION = 105; // 3.5s
const OUTRO_DURATION = 105; // 3.5s
// Total: 750 frames = 25s

export const OpenSourceStack: React.FC = () => {
  return (
    <div
      style={{
        width: 1920,
        height: 1080,
        backgroundColor: BRAND.bgDark,
        fontFamily:
          'Poppins, -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif',
        overflow: "hidden",
      }}
    >
      <Series>
        <Series.Sequence durationInFrames={HOOK_DURATION}>
          <HookScene />
        </Series.Sequence>

        <Series.Sequence durationInFrames={NOT_VIBE_DURATION}>
          <NotVibeCoding />
        </Series.Sequence>

        <Series.Sequence durationInFrames={STACK_DURATION}>
          <StackLayers />
        </Series.Sequence>

        <Series.Sequence durationInFrames={INFRA_DURATION}>
          <InfraScene />
        </Series.Sequence>

        <Series.Sequence durationInFrames={REAL_WORLD_DURATION}>
          <RealWorldScene />
        </Series.Sequence>

        <Series.Sequence durationInFrames={OUTRO_DURATION}>
          <OutroScene />
        </Series.Sequence>
      </Series>
    </div>
  );
};
