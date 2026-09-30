import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { strokeStyle, useVerticalLayout } from "../layout";

/**
 * TitleHook — the persistent hook line in the title band of a 9:16 video
 * ("that's where you tie the hook"; check_vertical_layout.py VL4). Two lines
 * at most, white with a black stroke, centred in the band. Renders nothing on
 * landscape canvases, where the full-screen TitleCard carries the title.
 */
export const TitleHook: React.FC<{ title: string }> = ({ title }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const vertical = useVerticalLayout();
  if (!vertical || !title) {
    return null;
  }
  const entrance = spring({ frame, fps, config: { damping: 20, stiffness: 90, mass: 0.6 } });

  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          ...vertical.titleBand,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          opacity: entrance,
          transform: `translateY(${interpolate(entrance, [0, 1], [-16, 0])}px)`,
        }}
      >
        <span
          style={{
            color: "#ffffff",
            fontFamily: "'Inter', 'SF Pro Display', system-ui, sans-serif",
            fontWeight: 800,
            fontSize: 64,
            lineHeight: 1.12,
            maxWidth: vertical.safe.width,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
            ...strokeStyle(vertical.strokePx),
          }}
        >
          {title}
        </span>
      </div>
    </AbsoluteFill>
  );
};
