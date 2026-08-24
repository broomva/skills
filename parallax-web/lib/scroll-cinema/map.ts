/**
 * Pure scroll->playback mapping. No DOM, no side effects.
 *
 * Everything the runtime does to decide *what frame to show* lives here so it
 * can be tested by calling these exact functions. The engine in `scrubber.ts`
 * imports them rather than reimplementing the arithmetic inline — a test that
 * re-derives this logic would be testing its own copy.
 */

export const clamp = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, value));

export const clamp01 = (value: number): number => clamp(value, 0, 1);

/** Which clip is on screen, and how far into it, for a 0..1 scroll position. */
export interface Placement {
  /** Index of the clip currently showing. */
  segment: number;
  /** Position within that clip, 0..1. */
  local: number;
}

/**
 * Map normalized scroll progress onto the clip chain.
 *
 * At progress === 1 the naive `floor` lands one past the last clip, so the
 * segment is clamped and `local` resolves to exactly 1 — the final frame.
 */
export function placement(progress: number, clipCount: number): Placement {
  if (!Number.isFinite(clipCount) || clipCount <= 0) return { segment: 0, local: 0 };
  // A NaN progress must not propagate: `clips[NaN]` downstream is a silent
  // undefined source rather than a visible error.
  // Only NaN resets; +/-Infinity is an overscroll and clamps to an end.
  if (Number.isNaN(progress)) return { segment: 0, local: 0 };
  const exact = clamp01(progress) * clipCount;
  const segment = Math.min(clipCount - 1, Math.floor(exact));
  return { segment, local: clamp01(exact - segment) };
}

/**
 * First-order lag toward a target, independent of frame rate.
 *
 * The reference implementation used a per-frame constant (`+= (t - c) * 0.16`),
 * which converges twice as fast on a 120Hz display as on a 60Hz one. Deriving
 * the coefficient from elapsed time makes the motion feel identical everywhere,
 * including across dropped frames.
 *
 * @param tau Time constant in seconds. ~0.096 reproduces the reference feel at 60Hz.
 */
export function easeToward(current: number, target: number, dt: number, tau: number): number {
  if (!Number.isFinite(current)) return target;
  if (tau <= 0 || dt <= 0) return target;
  const k = 1 - Math.exp(-dt / tau);
  return current + (target - current) * k;
}

/**
 * Crossfade weight for the *incoming* clip, over the final `fraction` of a segment.
 * Returns 0 for most of the segment, ramping to 1 exactly at the seam.
 */
export function fadeAt(local: number, fraction: number): number {
  if (fraction <= 0) return 0;
  // Exact at the seam: (1 - 0.9) / 0.1 is 0.9999999999999998 in binary floating
  // point, which would leave the incoming clip a hair short of opaque forever.
  if (local >= 1) return 1;
  if (fraction >= 1) return clamp01(local);
  const start = 1 - fraction;
  return clamp01((local - start) / fraction);
}

/**
 * Which of the two video elements holds a given segment.
 *
 * The whole memory story rests on this: only the current clip and the one it is
 * fading into can ever be visible, so two elements suffice for any story length.
 * Guarded against negative input so a bad caller cannot produce index -1.
 */
export function slotFor(segment: number): 0 | 1 {
  // Must return a usable index for any input a JS caller can supply: `%` on a
  // fractional or infinite value yields 0.5 / NaN, which would index nothing.
  if (!Number.isFinite(segment)) return 0;
  const i = Math.trunc(segment);
  return (((i % 2) + 2) % 2) as 0 | 1;
}

/**
 * The segments allowed to occupy a decoder, in priority order.
 *
 * Only the clip being scrubbed and the one it fades into may be bound. This is
 * deliberately NOT `residentSet`: that is a *memory retention* policy which
 * includes the previous clip, and binding it would collide with the incoming
 * clip (`slotFor(n-1) === slotFor(n+1)`) and thrash a decoder every frame.
 */
export function bindTargets(segment: number, clipCount: number): number[] {
  if (!Number.isFinite(clipCount) || clipCount <= 0) return [];
  if (!Number.isFinite(segment)) return [];
  const out: number[] = [];
  for (const i of [Math.trunc(segment), Math.trunc(segment) + 1]) {
    if (i >= 0 && i < clipCount) out.push(i);
  }
  return out;
}

/**
 * Playback time for a clip, given position within it.
 *
 * Never returns exactly `duration`: seeking to the very end puts some decoders
 * into an ended state that then renders black instead of the final frame.
 */
export function timeFor(local: number, duration: number, endGuard = 1 / 48): number {
  if (!Number.isFinite(duration) || duration <= 0) return 0;
  if (Number.isNaN(local)) return 0;
  // The guard is temporal, not fractional. A fractional ceiling (0.998) scales
  // with length: on a 300s clip it would stop 600ms early and never reach the
  // authored end frame, breaking the seam the whole keyframe chain depends on.
  const last = Math.max(0, duration - Math.max(0, endGuard));
  return clamp01(local) * last;
}

/**
 * Whether a seek is worth issuing. Sub-frame deltas are invisible and only
 * thrash the decoder, so they are skipped.
 */
export function shouldSeek(currentTime: number, targetTime: number, epsilon: number): boolean {
  if (!Number.isFinite(currentTime) || !Number.isFinite(targetTime)) return false;
  return Math.abs(currentTime - targetTime) > epsilon;
}

/**
 * Which clips should be held in memory, in priority order.
 *
 * Current first (required to render), then next (required to crossfade into),
 * then previous (cheap insurance against scrolling back up). Truncated to `max`,
 * which is what bounds resident memory regardless of how many clips exist.
 */
export function residentSet(segment: number, clipCount: number, max: number): number[] {
  if (clipCount <= 0 || max <= 0) return [];
  const wanted = [segment, segment + 1, segment - 1];
  const seen = new Set<number>();
  const out: number[] = [];
  for (const i of wanted) {
    if (i < 0 || i >= clipCount || seen.has(i)) continue;
    seen.add(i);
    out.push(i);
    if (out.length >= max) break;
  }
  return out;
}

/**
 * Scroll progress of the track, 0..1.
 *
 * Returns 0 rather than NaN/Infinity when the track is not taller than the
 * viewport, which happens transiently during layout and on very short pages.
 */
export function trackProgress(scrollTop: number, scrollHeight: number, viewport: number): number {
  if (Number.isNaN(scrollTop)) return 0;
  const scrollable = scrollHeight - viewport;
  if (!Number.isFinite(scrollable) || scrollable <= 0) return 0;
  return clamp01(scrollTop / scrollable);
}

/**
 * Whether a freshly bound slot may be shown yet.
 *
 * A slot is revealed once the compositor confirms a frame at (near) the
 * requested time. Until then it stays hidden and the poster covers it -- that is
 * what stops a clip appearing at frame 0 while the viewer is mid-segment.
 *
 * `requestVideoFrameCallback` gives no timing guarantee, so an unconditional
 * wait can leave a slot invisible forever. `elapsedMs > timeoutMs` is a
 * deliberate fail-open: a stale frame beats a page that never shows video. The
 * deadline is wall-clock on purpose -- it is a liveness budget, not a frame
 * budget, so unlike the tolerance it does not derive from frame rate.
 *
 * Pure and exported so the NaN case is directly testable: an earlier inline
 * version inverted this predicate and revealed immediately when no frame had
 * been reported, which is precisely when it should have waited.
 *
 * @param paintedTime mediaTime of the last compositor-painted frame; NaN if none.
 */
export function shouldReveal(
  paintedTime: number,
  targetTime: number,
  tolerance: number,
  elapsedMs: number,
  timeoutMs: number,
): boolean {
  const confirmed =
    Number.isFinite(paintedTime) &&
    Number.isFinite(targetTime) &&
    Math.abs(paintedTime - targetTime) <= Math.max(0, tolerance);
  if (confirmed) return true;
  return elapsedMs > timeoutMs;
}
