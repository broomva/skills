import React from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
  interpolate,
} from "remotion";
import {
  TransitionSeries,
  linearTiming,
} from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import type { ShotEntry } from "../hooks/useManifest";

interface ClipSequenceProps {
  shots: ShotEntry[];
  fps: number;
  crossfadeDurationSeconds: number;
}

/**
 * ClipSequence — chains video clips with crossfade transitions.
 *
 * Uses @remotion/transitions TransitionSeries for smooth crossfades
 * between clips. Each clip is rendered with OffthreadVideo for
 * non-blocking decoding.
 *
 * Falls back to a styled brief card when a clip file is missing.
 */
export const ClipSequence: React.FC<ClipSequenceProps> = ({
  shots,
  fps,
  crossfadeDurationSeconds,
}) => {
  const crossfadeFrames = Math.round(crossfadeDurationSeconds * fps);

  const validShots = shots.filter((s) => s.status !== "failed" || s.clip);

  if (validShots.length === 0) {
    return (
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          backgroundColor: "#0a0a0a",
        }}
      >
        <p style={{ color: "#666", fontSize: 32, fontFamily: "sans-serif" }}>
          No clips available
        </p>
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill>
      <TransitionSeries>
        {validShots.map((shot, index) => {
          const durationFrames = Math.round((shot.durationSeconds ?? 8) * fps);

          return (
            <React.Fragment key={shot.name}>
              <TransitionSeries.Sequence durationInFrames={durationFrames}>
                {shot.clip ? (
                  <ClipFrame clipPath={shot.clip} />
                ) : (
                  <BriefCard
                    name={shot.name}
                    prompt={shot.prompt}
                  />
                )}
              </TransitionSeries.Sequence>

              {/* Crossfade between clips (skip after last) */}
              {index < validShots.length - 1 && (
                <TransitionSeries.Transition
                  presentation={fade()}
                  timing={linearTiming({
                    durationInFrames: crossfadeFrames,
                  })}
                />
              )}
            </React.Fragment>
          );
        })}
      </TransitionSeries>
    </AbsoluteFill>
  );
};

/**
 * Renders a single video clip with OffthreadVideo.
 * The clip path is resolved relative to the public directory.
 */
const ClipFrame: React.FC<{ clipPath: string }> = ({ clipPath }) => {
  // Resolve clip: if it's an absolute path or URL, use directly;
  // otherwise treat as relative to the Remotion public dir.
  const src = clipPath.startsWith("http") || clipPath.startsWith("/")
    ? clipPath
    : staticFile(clipPath);

  return (
    <AbsoluteFill>
      <OffthreadVideo
        src={src}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
        }}
      />
    </AbsoluteFill>
  );
};

/**
 * Fallback card shown when a clip file is missing.
 * Displays the shot name and a truncated version of the prompt.
 */
const BriefCard: React.FC<{ name: string; prompt: string }> = ({
  name,
  prompt,
}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 12], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        backgroundColor: "#111118",
        padding: 80,
        opacity,
      }}
    >
      <h2
        style={{
          color: "#6B8AFF",
          fontSize: 42,
          fontFamily: "sans-serif",
          fontWeight: 600,
          marginBottom: 24,
          textAlign: "center",
        }}
      >
        {name}
      </h2>
      <p
        style={{
          color: "#888",
          fontSize: 28,
          fontFamily: "sans-serif",
          lineHeight: 1.5,
          maxWidth: 900,
          textAlign: "center",
        }}
      >
        {prompt.length > 200 ? `${prompt.slice(0, 200)}...` : prompt}
      </p>
    </AbsoluteFill>
  );
};
