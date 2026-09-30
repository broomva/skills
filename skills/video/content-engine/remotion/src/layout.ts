import type React from "react";
import { useVideoConfig } from "remotion";
import contract from "../../layout/vertical-9x16.json";

/**
 * Vertical (9:16) overlay geometry, read from the same contract that
 * scripts/check_vertical_layout.py enforces (layout/vertical-9x16.json;
 * rules in references/vertical-layout.md). Nothing here hard-codes a pixel:
 * change the contract and both the renderer and the gate move together.
 */

type Zone = { x0: number; y0: number; x1: number; y1: number };
type Band = { y0: number; y1: number; x0?: number; x1?: number };

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface VerticalLayout {
  width: number;
  height: number;
  /** Everything important stays inside this (VL2). */
  safe: Rect;
  /** Title hook text sits in this band (VL4). */
  titleBand: Rect;
  /** Captions sit in this band, centred (VL5); it stops short of the action rail. */
  captionBand: Rect;
  /**
   * The safe zone above the first avoid zone that cuts into it (the action
   * rail). Full-width text centred here cannot reach the rail (VL3).
   */
  upper: Rect;
  /** Black outline for overlay text; the contract's answer to busy backgrounds (VL9). */
  strokePx: number;
}

const profiles = contract.profiles as Record<
  string,
  {
    safe_zone: Zone;
    avoid: Array<Zone & { name: string }>;
    title_band: Band | null;
    caption_band: Band | null;
  }
>;
const organic = profiles["reels-organic"];

function zoneRect(z: Zone, w: number, h: number): Rect {
  return {
    left: Math.round(z.x0 * w),
    top: Math.round(z.y0 * h),
    width: Math.round((z.x1 - z.x0) * w),
    height: Math.round((z.y1 - z.y0) * h),
  };
}

function bandRect(b: Band, safe: Rect, w: number, h: number): Rect {
  const left = b.x0 === undefined ? safe.left : Math.round(b.x0 * w);
  const right = b.x1 === undefined ? safe.left + safe.width : Math.round(b.x1 * w);
  return {
    left,
    top: Math.round(b.y0 * h),
    width: right - left,
    height: Math.round((b.y1 - b.y0) * h),
  };
}

/** Geometry for a portrait canvas; null for landscape or square. */
export function verticalLayout(
  width: number,
  height: number
): VerticalLayout | null {
  if (height <= width || !organic.title_band || !organic.caption_band) {
    return null;
  }
  const safe = zoneRect(organic.safe_zone, width, height);
  const s = organic.safe_zone;
  const cutTop = Math.min(
    s.y1,
    ...organic.avoid
      .filter((a) => a.x0 < s.x1 && a.x1 > s.x0 && a.y0 > s.y0)
      .map((a) => a.y0)
  );
  return {
    width,
    height,
    safe,
    titleBand: bandRect(organic.title_band, safe, width, height),
    captionBand: bandRect(organic.caption_band, safe, width, height),
    upper: { ...safe, height: Math.round(cutTop * height) - safe.top },
    strokePx: Math.max(3, Math.round(width / 180)),
  };
}

export function useVerticalLayout(): VerticalLayout | null {
  const { width, height } = useVideoConfig();
  return verticalLayout(width, height);
}

/**
 * Largest font size (<= `preferred`) at which `text` fits `width` on one line.
 * Bold sans averages ~0.62em per character; this is an estimate, and the gate
 * (check_vertical_layout.py VL3/VL5) is what verifies the rendered result.
 */
export function fitFontSize(text: string, width: number, preferred: number): number {
  const estimate = Math.floor(width / Math.max(1, text.length * 0.62));
  return Math.max(24, Math.min(preferred, estimate));
}

/** Outline style for white overlay text on footage. */
export function strokeStyle(px: number): React.CSSProperties {
  return {
    WebkitTextStroke: `${px}px #000`,
    paintOrder: "stroke fill",
  };
}
