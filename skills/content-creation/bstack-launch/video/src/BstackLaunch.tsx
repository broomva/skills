import { Series } from "remotion";
import { IntroScene } from "./scenes/Intro";
import { LayerScene } from "./scenes/LayerScene";
import { ProductsScene } from "./scenes/Products";
import { OutroScene } from "./scenes/Outro";
import { layers, BRAND } from "./data/stack";

const INTRO_DURATION = 120; // 4s
const LAYER_DURATION = 75; // 2.5s each × 7 = 17.5s
const PRODUCTS_DURATION = 150; // 5s
const OUTRO_DURATION = 120; // 4s
// Total: 4 + 17.5 + 5 + 4 = 30.5s = ~900 frames

export const BstackLaunch: React.FC = () => {
  return (
    <div
      style={{
        width: 1080,
        height: 1080,
        backgroundColor: BRAND.bgDark,
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif',
        overflow: "hidden",
      }}
    >
      <Series>
        <Series.Sequence durationInFrames={INTRO_DURATION}>
          <IntroScene />
        </Series.Sequence>

        {layers.map((layer) => (
          <Series.Sequence key={layer.id} durationInFrames={LAYER_DURATION}>
            <LayerScene layer={layer} />
          </Series.Sequence>
        ))}

        <Series.Sequence durationInFrames={PRODUCTS_DURATION}>
          <ProductsScene />
        </Series.Sequence>

        <Series.Sequence durationInFrames={OUTRO_DURATION}>
          <OutroScene />
        </Series.Sequence>
      </Series>
    </div>
  );
};
