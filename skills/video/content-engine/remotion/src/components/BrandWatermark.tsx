import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate, spring, useVideoConfig } from "remotion";
import { useVerticalLayout } from "../layout";

interface BrandWatermarkProps {
  brandName: string;
  primaryColor: string;
}

/**
 * BrandWatermark — subtle lower-third brand overlay.
 *
 * Renders a semi-transparent pill with the brand name positioned at
 * bottom-right. Fades in with a spring animation on entry and remains
 * non-intrusive throughout the clip sequence.
 *
 * On a 9:16 canvas bottom-right is the platform's action rail and caption
 * band ("avoid at all costs", check_vertical_layout.py VL3), so the pill moves
 * to the safe zone's bottom-left corner instead.
 */
export const BrandWatermark: React.FC<BrandWatermarkProps> = ({
  brandName,
  primaryColor,
}) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const vertical = useVerticalLayout();

  // Spring entrance animation
  const entrance = spring({
    frame,
    fps,
    config: {
      damping: 20,
      stiffness: 80,
      mass: 0.8,
    },
  });

  // Subtle opacity — never fully opaque to stay non-intrusive
  const opacity = interpolate(entrance, [0, 1], [0, 0.7]);
  const translateY = interpolate(entrance, [0, 1], [20, 0]);

  // Parse primary color to create a semi-transparent background
  const bgColor = hexToRgba(primaryColor, 0.25);
  const borderColor = hexToRgba(primaryColor, 0.4);

  return (
    <AbsoluteFill
      style={
        vertical
          ? {
              justifyContent: "flex-end",
              alignItems: "flex-start",
              paddingLeft: vertical.safe.left,
              paddingBottom: height - (vertical.safe.top + vertical.safe.height),
            }
          : {
              justifyContent: "flex-end",
              alignItems: "flex-end",
              padding: 32,
            }
      }
    >
      <div
        style={{
          opacity,
          transform: `translateY(${translateY}px)`,
          backgroundColor: bgColor,
          border: `1px solid ${borderColor}`,
          borderRadius: 20,
          padding: "8px 18px",
          backdropFilter: "blur(8px)",
          WebkitBackdropFilter: "blur(8px)",
        }}
      >
        <span
          style={{
            color: "#ffffff",
            fontSize: vertical ? 28 : 16,
            fontFamily: "'Inter', 'SF Pro Display', system-ui, sans-serif",
            fontWeight: 600,
            letterSpacing: 0.5,
            textTransform: "uppercase",
            textShadow: "0 1px 3px rgba(0,0,0,0.4)",
          }}
        >
          {brandName}
        </span>
      </div>
    </AbsoluteFill>
  );
};

/**
 * Convert a hex color string to rgba().
 */
function hexToRgba(hex: string, alpha: number): string {
  const cleaned = hex.replace("#", "");
  if (cleaned.length < 6) {
    return `rgba(107, 138, 255, ${alpha})`;
  }
  const r = parseInt(cleaned.substring(0, 2), 16);
  const g = parseInt(cleaned.substring(2, 4), 16);
  const b = parseInt(cleaned.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
