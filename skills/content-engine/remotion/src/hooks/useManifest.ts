import { z } from "zod";

// ---------------------------------------------------------------------------
// Zod Schema — used by Remotion's calculateMetadata & props validation
// ---------------------------------------------------------------------------

const shotSchema = z.object({
  /** Shot name (e.g., "Shot 1: Establishing") */
  name: z.string(),
  /** Prompt / brief text for the shot */
  prompt: z.string().default(""),
  /** Filename of the generated clip (relative to output dir) */
  clip: z.string().nullable().default(null),
  /** Generation status */
  status: z.enum(["generated", "failed", "pending"]).default("pending"),
  /** Duration of this clip in seconds (default 8) */
  durationSeconds: z.number().optional().default(8),
});

const brandDnaSchema = z.object({
  mood: z.string().optional(),
  lighting_type: z.string().optional(),
  lighting_temp: z.string().optional(),
  composition: z.string().optional(),
  colors: z.string().optional(),
  texture: z.string().optional(),
});

const captionWordSchema = z.object({
  text: z.string(),
  startTime: z.number(),
  endTime: z.number(),
  weight: z.number().optional(),
  size: z.number().optional(),
  speaker: z.number().optional(),
  emphasis: z.boolean().optional(),
});

const captionEventSchema = z.object({
  startTime: z.number(),
  endTime: z.number(),
  words: z.array(captionWordSchema),
});

export const manifestSchema = z.object({
  /** Video / campaign title */
  title: z.string().default("Content Engine Video"),
  /** Brand slug */
  brand: z.string().nullable().default(null),
  /** ISO 8601 timestamp of generation */
  generated: z.string().default(""),
  /** Backend used for clip generation */
  backend: z.string().default("veo-3.0"),
  /** Array of shots with clip info */
  shots: z.array(shotSchema).default([]),
  /** Optional brand DNA for styling */
  brandDna: brandDnaSchema.nullable().optional().default(null),
  /** Optional CWI caption data from OpenCaptions */
  captions: z.array(captionEventSchema).nullable().optional().default(null),
});

// ---------------------------------------------------------------------------
// Derived TypeScript types
// ---------------------------------------------------------------------------

export type ShotEntry = z.infer<typeof shotSchema>;
export type BrandDna = z.infer<typeof brandDnaSchema>;
export type CaptionWord = z.infer<typeof captionWordSchema>;
export type CaptionEvent = z.infer<typeof captionEventSchema>;
export type ManifestData = z.infer<typeof manifestSchema>;

// ---------------------------------------------------------------------------
// Layout calculator — used by composition & components
// ---------------------------------------------------------------------------

export interface ManifestLayout {
  /** Frames per second */
  fps: number;
  /** Duration of the title card in frames */
  titleCardFrames: number;
  /** Duration of the end card in frames */
  endCardFrames: number;
  /** Duration of the clips region in frames (between title & end cards) */
  clipsRegionFrames: number;
  /** Crossfade overlap in seconds */
  crossfadeSeconds: number;
  /** Per-shot frame info */
  shotFrames: Array<{
    /** Absolute start frame within the clips region */
    startFrame: number;
    /** Duration in frames (before accounting for crossfade overlap) */
    durationFrames: number;
    shot: ShotEntry;
  }>;
  /** Total video duration in frames */
  totalFrames: number;
}

const TITLE_CARD_SECONDS = 2;
const END_CARD_SECONDS = 2;
const CROSSFADE_SECONDS = 0.5;
const DEFAULT_FPS = 24;

/**
 * Compute the full layout from manifest data.
 *
 * This is the single source of truth for frame positions. Both the
 * Root.tsx calculateMetadata and the component tree use this.
 */
export function useManifestLayout(
  manifest: ManifestData,
  fps: number = DEFAULT_FPS
): ManifestLayout {
  const titleCardFrames = Math.round(TITLE_CARD_SECONDS * fps);
  const endCardFrames = Math.round(END_CARD_SECONDS * fps);

  const shotFrames: ManifestLayout["shotFrames"] = [];
  let currentFrame = 0;

  for (let i = 0; i < manifest.shots.length; i++) {
    const shot = manifest.shots[i];
    const durationSeconds = shot.durationSeconds ?? 8;
    const durationFrames = Math.round(durationSeconds * fps);

    shotFrames.push({
      startFrame: currentFrame,
      durationFrames,
      shot,
    });

    // Advance by full duration, then subtract crossfade overlap
    // (the next clip starts during the crossfade of the current one)
    currentFrame += durationFrames;
    if (i < manifest.shots.length - 1) {
      currentFrame -= Math.round(CROSSFADE_SECONDS * fps);
    }
  }

  const clipsRegionFrames = currentFrame;
  const totalFrames = titleCardFrames + clipsRegionFrames + endCardFrames;

  return {
    fps,
    titleCardFrames,
    endCardFrames,
    clipsRegionFrames,
    crossfadeSeconds: CROSSFADE_SECONDS,
    shotFrames,
    totalFrames,
  };
}
