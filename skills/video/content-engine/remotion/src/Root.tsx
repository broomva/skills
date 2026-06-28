import { Composition } from "remotion";
import { ContentEngineVideo } from "./ContentEngineVideo";
import { type ManifestData, manifestSchema } from "./hooks/useManifest";

const FPS = 24;
const WIDTH = 1920;
const HEIGHT = 1080;

/**
 * Default duration when no manifest is provided (10 seconds).
 * The actual duration is calculated from the manifest at render time.
 */
const DEFAULT_DURATION_FRAMES = FPS * 10;

/**
 * Calculate total duration in frames from a manifest.
 * Each clip defaults to 8 seconds if no explicit duration is set.
 * Adds 2 seconds each for title and end cards.
 */
function calculateDuration(manifest: ManifestData): number {
  const TITLE_CARD_SECONDS = 2;
  const END_CARD_SECONDS = 2;
  const CROSSFADE_SECONDS = 0.5;

  const clipsDuration = manifest.shots.reduce((total, shot) => {
    return total + (shot.durationSeconds ?? 8);
  }, 0);

  const crossfadeCount = Math.max(0, manifest.shots.length - 1);
  const crossfadeTotal = crossfadeCount * CROSSFADE_SECONDS;

  const totalSeconds =
    TITLE_CARD_SECONDS + clipsDuration - crossfadeTotal + END_CARD_SECONDS;

  return Math.ceil(totalSeconds * FPS);
}

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ContentEngineVideo"
        component={ContentEngineVideo}
        durationInFrames={DEFAULT_DURATION_FRAMES}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        schema={manifestSchema}
        calculateMetadata={async ({ props }) => {
          if (props.shots && props.shots.length > 0) {
            return {
              durationInFrames: calculateDuration(props as ManifestData),
            };
          }
          return {};
        }}
        defaultProps={{
          title: "Content Engine Video",
          brand: null,
          generated: new Date().toISOString(),
          backend: "veo-3.0",
          shots: [],
          brandDna: null,
          captions: null,
        }}
      />
    </>
  );
};
