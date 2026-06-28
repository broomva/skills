import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { type ManifestData } from "./hooks/useManifest";
import { useManifestLayout } from "./hooks/useManifest";
import { ClipSequence } from "./components/ClipSequence";
import { TitleCard } from "./components/TitleCard";
import { BrandWatermark } from "./components/BrandWatermark";
import { CaptionOverlay } from "./components/CaptionOverlay";

/**
 * ContentEngineVideo — main Remotion composition.
 *
 * Renders: TitleCard -> ClipSequence (with crossfade transitions) -> EndCard
 * Overlays: BrandWatermark + CaptionOverlay on top of clip sequence.
 */
export const ContentEngineVideo: React.FC<ManifestData> = (props) => {
  const layout = useManifestLayout(props);

  const { title, brandDna, captions, shots } = props;

  const brandColors = brandDna?.colors
    ? brandDna.colors.split(",").map((c) => c.trim())
    : ["#6B8AFF", "#1a1a2e"];

  const primaryColor = brandColors[0] ?? "#6B8AFF";
  const secondaryColor = brandColors[1] ?? "#1a1a2e";
  const brandName = brandDna?.mood ? props.brand ?? "" : props.brand ?? "";

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0a" }}>
      {/* Title Card */}
      <Sequence from={0} durationInFrames={layout.titleCardFrames}>
        <TitleCard
          title={title}
          primaryColor={primaryColor}
          secondaryColor={secondaryColor}
        />
      </Sequence>

      {/* Clip Sequence with transitions */}
      {shots.length > 0 && (
        <Sequence
          from={layout.titleCardFrames}
          durationInFrames={layout.clipsRegionFrames}
        >
          <ClipSequence
            shots={shots}
            fps={layout.fps}
            crossfadeDurationSeconds={layout.crossfadeSeconds}
          />

          {/* Caption Overlay — positioned over clips */}
          <CaptionOverlay
            captions={captions ?? null}
            shots={shots}
            fps={layout.fps}
            crossfadeDurationSeconds={layout.crossfadeSeconds}
          />
        </Sequence>
      )}

      {/* End Card */}
      <Sequence
        from={layout.titleCardFrames + layout.clipsRegionFrames}
        durationInFrames={layout.endCardFrames}
      >
        <TitleCard
          title={title}
          primaryColor={primaryColor}
          secondaryColor={secondaryColor}
          isEndCard
        />
      </Sequence>

      {/* Brand Watermark — visible during clips */}
      {brandName && (
        <Sequence
          from={layout.titleCardFrames}
          durationInFrames={layout.clipsRegionFrames}
        >
          <BrandWatermark
            brandName={brandName}
            primaryColor={primaryColor}
          />
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
