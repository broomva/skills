import React from "react";

/* The plain-voice work states — Broomva's canon vocabulary. The dot
   carries the color; running wears the tidepool, standing pulses.
   System enums (Todo/InProgress/Blocked/InReview) are a developer
   surface only — never render them here. */
const STATES = {
  queued:    { label: "Queued",    color: "var(--bv-gray-400)" },
  running:   { label: "Running",   color: "var(--bv-blue)", live: true },
  stuck:     { label: "Stuck",     color: "var(--bv-warning)" },
  "needs-you": { label: "Needs you", color: "var(--bv-blue-accent)" },
  done:      { label: "Done",      color: "var(--bv-success)" },
  standing:  { label: "Standing",  color: "var(--bv-blue)", pulse: true },
};

export function WorkState({ state = "queued", variant = "inline", children, style }) {
  const s = STATES[state] || STATES.queued;
  const dot = s.live ? (
    <span className="bv-dot-live" style={{ width: 10, height: 10 }}></span>
  ) : (
    <span
      className={s.pulse ? "bv-dot--pulse" : undefined}
      style={{ width: 8, height: 8, borderRadius: 99, flexShrink: 0, background: s.color }}
    ></span>
  );
  if (variant === "chip") {
    return (
      <span style={{
        display: "inline-flex", alignItems: "center", gap: 7,
        height: 26, padding: "0 12px",
        borderRadius: "var(--bv-radius-full)", background: "var(--bv-canvas-soft)",
        fontSize: 12, fontWeight: 500, color: "var(--foreground)", ...style,
      }}>
        {dot}{children || s.label}
      </span>
    );
  }
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      fontSize: 13, fontWeight: 500, color: "var(--foreground)", ...style,
    }}>
      {dot}{children || s.label}
    </span>
  );
}
