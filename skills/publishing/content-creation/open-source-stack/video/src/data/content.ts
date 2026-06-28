export const BRAND = {
  aiBlue: "#0066FF",
  web3Green: "#00CC66",
  bgDark: "#0A0A0F",
  bgCard: "#12121A",
  bgSurface: "#1A1A2E",
  textPrimary: "#F0F0F5",
  textSecondary: "#8888AA",
  textMuted: "#6B6B80",
  glassBorder: "rgba(255,255,255,0.08)",
  accentGradient: "linear-gradient(135deg, #0066FF, #00CC66)",
  warning: "#FFD60A",
} as const;

export interface StackLayer {
  label: string;
  emoji: string;
  skills: string[];
  color: string;
}

export const stackLayers: StackLayer[] = [
  {
    label: "Foundation",
    emoji: "🏗",
    skills: ["Control Metalayer", "Safety Shields", "Harness Gates"],
    color: "#FF3366",
  },
  {
    label: "Memory",
    emoji: "🧠",
    skills: ["Consciousness", "Knowledge Graph", "Prompt Library"],
    color: "#FF6633",
  },
  {
    label: "Orchestration",
    emoji: "🎼",
    skills: ["Symphony", "AutoAny (EGRI)", "Symphony Forge"],
    color: "#FFCC00",
  },
  {
    label: "Research",
    emoji: "🔬",
    skills: ["Deep Research", "Competitor Intel", "Skills Catalog"],
    color: "#00CC66",
  },
  {
    label: "Design",
    emoji: "🎨",
    skills: ["Arcan Glass", "Next.js Templates", "Content Pipeline"],
    color: "#0066FF",
  },
  {
    label: "Platform",
    emoji: "⚡",
    skills: ["Haima (x402 Payments)", "Finance Engine", "Deployment"],
    color: "#6633FF",
  },
  {
    label: "Strategy",
    emoji: "♟",
    skills: ["Pre-mortem", "Drift Check", "Weekly Review"],
    color: "#CC33FF",
  },
];

export const coreInfra = [
  { name: "Arcan", desc: "Agent Runtime", lang: "Rust" },
  { name: "Lago", desc: "Event-Sourced Persistence", lang: "Rust" },
  { name: "Symphony", desc: "Orchestration Daemon", lang: "Rust" },
  { name: "Autonomic", desc: "Homeostasis Controller", lang: "Rust" },
  { name: "Praxis", desc: "Tool Execution Sandbox", lang: "Rust" },
  { name: "Vigil", desc: "OpenTelemetry Observability", lang: "Rust" },
  { name: "Haima", desc: "Agentic Finance (x402)", lang: "Rust" },
];

export const realWorldProofs = [
  {
    label: "FIFA World Cup 2026",
    detail: "AI procurement agent — thousands of vendor requests",
  },
  {
    label: "Stimulus",
    detail: "Enterprise AI solutions at scale",
  },
  {
    label: "broomva.tech",
    detail: "Personal projects shipped in record time",
  },
];

export const metrics = [
  { label: "Rust Crates", value: "31" },
  { label: "Agent Skills", value: "24" },
  { label: "Stack Layers", value: "7" },
  { label: "Public Repos", value: "30" },
];
