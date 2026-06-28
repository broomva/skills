export interface StackLayer {
  id: string;
  label: string;
  description: string;
  color: string;
  components: string[];
}

export interface Metric {
  label: string;
  value: string;
}

export const BRAND = {
  aiBlue: "#0066FF",
  web3Green: "#00CC66",
  bgDark: "#0A0A0F",
  bgCard: "#12121A",
  textPrimary: "#F0F0F5",
  textSecondary: "#8888AA",
  glassBorder: "rgba(255,255,255,0.08)",
} as const;

export const metrics: Metric[] = [
  { label: "Lines of Rust", value: "37K" },
  { label: "Crates", value: "31" },
  { label: "Tests Passing", value: "1,000" },
  { label: "Agent Skills", value: "16" },
  { label: "Products", value: "5" },
];

export const layers: StackLayer[] = [
  {
    id: "kernel",
    label: "Kernel",
    description: "Agent OS contract & typed state vector",
    color: "#FF3366",
    components: ["aiOS", "AgentStateVector", "8-Phase Tick", "6 Operating Modes"],
  },
  {
    id: "runtime",
    label: "Runtime",
    description: "Agent daemon with content-addressed edits",
    color: "#FF6633",
    components: ["Arcan", "Hashline Edits", "Multi-Provider", "SSE Streaming"],
  },
  {
    id: "persistence",
    label: "Persistence",
    description: "Event-sourced journal & blob storage",
    color: "#FFCC00",
    components: ["Lago", "Event Journal", "Blob Store", "Branching FS"],
  },
  {
    id: "regulation",
    label: "Regulation",
    description: "Three-pillar homeostatic controller",
    color: "#00CC66",
    components: ["Autonomic", "Operational", "Cognitive", "Economic"],
  },
  {
    id: "tools",
    label: "Tools",
    description: "Sandboxed execution with workspace isolation",
    color: "#0066FF",
    components: ["Praxis", "Blake3 Hashes", "FsPolicy", "MCP Bridge"],
  },
  {
    id: "orchestration",
    label: "Orchestration",
    description: "Multi-agent coordination daemon",
    color: "#6633FF",
    components: ["Symphony", "Dispatch", "Control Gates", "Dashboard"],
  },
  {
    id: "consciousness",
    label: "Consciousness",
    description: "Persistent three-substrate memory",
    color: "#CC33FF",
    components: ["Control Metalayer", "Knowledge Graph", "Episodic Memory"],
  },
];

export const products = [
  { name: "chatOS", desc: "Multi-model AI chat", tech: "Next.js 16 + AI SDK v6" },
  { name: "Symphony Cloud", desc: "Managed orchestration SaaS", tech: "next-forge + Stripe" },
  { name: "Mission Control", desc: "Desktop agent cockpit", tech: "Tauri 2.0 + Liquid Glass" },
  { name: "Control", desc: "Local-first dev terminal", tech: "Tauri + SQLite + Git graph" },
  { name: "Arcan Glass", desc: "AI-native design system", tech: "Tailwind v4 + OKLCh" },
];
