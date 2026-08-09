import React from "react";

/* The composer: rounded-28 glass capsule with the frosted-blue halo.
   The single dramatic depth cue in the product. */
export function Composer({ placeholder = "Message Broomva", value, onChange, onSend, leading, style, ...rest }) {
  const [inner, setInner] = React.useState("");
  const text = value !== undefined ? value : inner;
  const set = onChange || setInner;
  const send = () => { if (text.trim() && onSend) onSend(text.trim()); if (value === undefined) setInner(""); };
  return (
    <div
      className="bv-glass-composer"
      style={{
        borderRadius: "var(--bv-radius-composer)", padding: 10,
        display: "grid", gridTemplateColumns: leading ? "auto 1fr auto" : "1fr auto",
        alignItems: "center", gap: 4,
        ...style,
      }}
      {...rest}
    >
      {leading}
      <input
        value={text}
        onChange={(e) => set(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") send(); }}
        placeholder={placeholder}
        style={{
          border: "none", background: "transparent", outline: "none",
          font: "inherit", fontSize: 16, padding: "8px 10px",
          color: "var(--foreground)", minWidth: 0,
        }}
      />
      <button
        type="button"
        aria-label="Send"
        onClick={send}
        style={{
          width: 36, height: 36, borderRadius: 18,
          background: "var(--primary)", color: "var(--primary-foreground)",
          border: "none", cursor: "pointer",
          display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        }}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: 18, height: 18 }}>
          <path d="M12 19V5" /><path d="m5 12 7-7 7 7" />
        </svg>
      </button>
    </div>
  );
}
