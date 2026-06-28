import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import type { ShotEntry } from "../hooks/useManifest";

// ---------------------------------------------------------------------------
// CWI (Contextual Word Intelligence) Types — from OpenCaptions
// ---------------------------------------------------------------------------

export interface CWIWord {
  /** The word text */
  text: string;
  /** Start time in seconds (absolute within the full video) */
  startTime: number;
  /** End time in seconds */
  endTime: number;
  /** Font weight: 100-900 (normal=400, bold=700) */
  weight?: number;
  /** Font size multiplier relative to base (0.7-1.5, default 1.0) */
  size?: number;
  /** Speaker index for color assignment */
  speaker?: number;
  /** Whether this word should have emphasis (glow effect) */
  emphasis?: boolean;
}

export interface CaptionEvent {
  /** Start time of this caption group in seconds */
  startTime: number;
  /** End time of this caption group in seconds */
  endTime: number;
  /** The words in this caption group with CWI data */
  words: CWIWord[];
}

export interface CaptionOverlayProps {
  /** CWI caption events from OpenCaptions. Null = use shot briefs as fallback. */
  captions: CaptionEvent[] | null;
  /** Shots array for fallback text */
  shots: ShotEntry[];
  /** Frames per second */
  fps: number;
  /** Crossfade overlap in seconds (to offset shot timing) */
  crossfadeDurationSeconds: number;
}

/**
 * WCAG AA compliant speaker palette.
 * High contrast against dark backgrounds.
 */
const SPEAKER_COLORS = [
  "#6B8AFF", // blue
  "#FF6B6B", // coral
  "#6BFFA3", // mint
  "#FFD76B", // gold
  "#FF6BFF", // pink
  "#6BFFFF", // cyan
] as const;

const BASE_FONT_SIZE = 48;

/**
 * CaptionOverlay — word-by-word caption renderer.
 *
 * When CWI data is provided (from OpenCaptions), renders words with:
 * - font-weight from CWI weight (100-900)
 * - font-size from CWI size multiplier (0.7-1.5x of base 48px)
 * - color from speaker palette (WCAG AA compliant)
 * - emphasis -> text-shadow glow effect
 * - Words appear word-by-word synced to timestamps
 *
 * When no CWI data is provided, falls back to displaying the current
 * shot's brief text as a simple subtitle.
 */
export const CaptionOverlay: React.FC<CaptionOverlayProps> = ({
  captions,
  shots,
  fps,
  crossfadeDurationSeconds,
}) => {
  const frame = useCurrentFrame();
  const currentTime = frame / fps;

  if (captions && captions.length > 0) {
    return (
      <CWICaptions
        captions={captions}
        currentTime={currentTime}
      />
    );
  }

  return (
    <FallbackCaptions
      shots={shots}
      currentTime={currentTime}
      fps={fps}
      crossfadeDurationSeconds={crossfadeDurationSeconds}
    />
  );
};

// ---------------------------------------------------------------------------
// CWI Caption Renderer
// ---------------------------------------------------------------------------

const CWICaptions: React.FC<{
  captions: CaptionEvent[];
  currentTime: number;
}> = ({ captions, currentTime }) => {
  // Find the active caption event
  const activeEvent = captions.find(
    (evt) => currentTime >= evt.startTime && currentTime <= evt.endTime
  );

  if (!activeEvent) {
    return null;
  }

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 80,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(0, 0, 0, 0.65)",
          borderRadius: 12,
          padding: "16px 32px",
          maxWidth: "85%",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: "4px 8px",
        }}
      >
        {activeEvent.words.map((word, i) => (
          <CWIWordSpan
            key={`${word.text}-${i}`}
            word={word}
            currentTime={currentTime}
          />
        ))}
      </div>
    </AbsoluteFill>
  );
};

const CWIWordSpan: React.FC<{
  word: CWIWord;
  currentTime: number;
}> = ({ word, currentTime }) => {
  const isVisible = currentTime >= word.startTime;
  const speakerIndex = word.speaker ?? 0;
  const color = SPEAKER_COLORS[speakerIndex % SPEAKER_COLORS.length];
  const weight = word.weight ?? 400;
  const sizeMultiplier = word.size ?? 1.0;
  const fontSize = Math.round(BASE_FONT_SIZE * sizeMultiplier);
  const isEmphasis = word.emphasis ?? false;

  // Fade in over ~100ms from word start time
  const timeSinceAppear = currentTime - word.startTime;
  const opacity = isVisible
    ? Math.min(1, timeSinceAppear / 0.1)
    : 0;

  // Scale pop on appearance
  const scale = isVisible
    ? interpolate(
        timeSinceAppear,
        [0, 0.08],
        [1.15, 1.0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
      )
    : 1;

  return (
    <span
      style={{
        color,
        fontFamily: "'Inter', 'SF Pro Display', system-ui, sans-serif",
        fontWeight: weight,
        fontSize,
        opacity,
        transform: `scale(${scale})`,
        display: "inline-block",
        textShadow: isEmphasis
          ? `0 0 16px ${color}, 0 0 32px ${color}80`
          : "0 2px 4px rgba(0,0,0,0.5)",
        transition: "opacity 0.05s ease-out",
      }}
    >
      {word.text}
    </span>
  );
};

// ---------------------------------------------------------------------------
// Fallback Caption Renderer (scene brief text)
// ---------------------------------------------------------------------------

const FallbackCaptions: React.FC<{
  shots: ShotEntry[];
  currentTime: number;
  fps: number;
  crossfadeDurationSeconds: number;
}> = ({ shots, currentTime, fps, crossfadeDurationSeconds }) => {
  // Determine which shot is currently active
  let elapsed = 0;
  let activeShotIndex = -1;

  for (let i = 0; i < shots.length; i++) {
    const shotDuration = shots[i].durationSeconds ?? 8;
    const crossfadeOffset = i > 0 ? crossfadeDurationSeconds : 0;
    const start = elapsed - crossfadeOffset;

    if (currentTime >= start && currentTime < start + shotDuration) {
      activeShotIndex = i;
      break;
    }

    elapsed += shotDuration;
    if (i > 0) {
      elapsed -= crossfadeDurationSeconds;
    }
  }

  if (activeShotIndex < 0) {
    return null;
  }

  const shot = shots[activeShotIndex];
  const briefText = shot.name;

  if (!briefText) {
    return null;
  }

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 80,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(0, 0, 0, 0.55)",
          borderRadius: 10,
          padding: "12px 28px",
          maxWidth: "70%",
        }}
      >
        <span
          style={{
            color: "#e0e0e0",
            fontSize: 32,
            fontFamily: "'Inter', 'SF Pro Display', system-ui, sans-serif",
            fontWeight: 500,
            textAlign: "center",
            display: "block",
            textShadow: "0 2px 4px rgba(0,0,0,0.5)",
          }}
        >
          {briefText}
        </span>
      </div>
    </AbsoluteFill>
  );
};
