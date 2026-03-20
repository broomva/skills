export type Category = {
  id: string;
  label: string;
  color: string;
  order: number;
};

export type Skill = {
  slug: string;
  categoryId: string;
  shortDescription: string;
};

export const categories: Category[] = [
  { id: "ai-agents", label: "AI & Agent Systems", color: "#8B5CF6", order: 0 },
  { id: "memory-knowledge", label: "Memory & Knowledge", color: "#06B6D4", order: 1 },
  { id: "research-intel", label: "Research & Intelligence", color: "#F59E0B", order: 2 },
  { id: "observability", label: "Observability & Debugging", color: "#EF4444", order: 3 },
  { id: "deployment", label: "Deployment & Infrastructure", color: "#10B981", order: 4 },
  { id: "nextjs-react", label: "Next.js & React", color: "#3B82F6", order: 5 },
  { id: "mobile-expo", label: "Mobile & Expo", color: "#EC4899", order: 6 },
  { id: "design-ui", label: "Design & UI Systems", color: "#F97316", order: 7 },
  { id: "json-render", label: "JSON-Render Ecosystem", color: "#84CC16", order: 8 },
  { id: "mcp-protocol", label: "MCP & Protocol Integration", color: "#A855F7", order: 9 },
  { id: "db-api", label: "Database & API", color: "#14B8A6", order: 10 },
  { id: "qa-browser", label: "QA & Browser Testing", color: "#F43F5E", order: 11 },
  { id: "cli-workflow", label: "CLI & Workflow Tooling", color: "#6366F1", order: 12 },
  { id: "design-tooling", label: "Design Tooling", color: "#D946EF", order: 13 },
  { id: "platform", label: "Platform Specialties", color: "#78716C", order: 14 },
  { id: "simulation", label: "Simulation & Optimization", color: "#0EA5E9", order: 15 },
];

export const skills: Skill[] = [
  // AI & Agent Systems
  { slug: "ai-sdk", categoryId: "ai-agents", shortDescription: "Vercel AI SDK integration" },
  { slug: "claude-api", categoryId: "ai-agents", shortDescription: "Anthropic Claude API" },
  { slug: "agentic-control-kernel", categoryId: "ai-agents", shortDescription: "LLM-as-controller architecture" },
  { slug: "autoany", categoryId: "ai-agents", shortDescription: "EGRI recursive improvement" },
  { slug: "control-metalayer-loop", categoryId: "ai-agents", shortDescription: "Control-system metalayer" },
  { slug: "harness-engineering-playbook", categoryId: "ai-agents", shortDescription: "Agent-first harness engineering" },

  // Memory & Knowledge
  { slug: "agent-consciousness", categoryId: "memory-knowledge", shortDescription: "Persistent consciousness architecture" },
  { slug: "knowledge-graph-memory", categoryId: "memory-knowledge", shortDescription: "Obsidian knowledge graph bridge" },
  { slug: "obsidian-markdown", categoryId: "memory-knowledge", shortDescription: "Obsidian-flavored Markdown" },
  { slug: "obsidian-bases", categoryId: "memory-knowledge", shortDescription: "Obsidian Bases database views" },
  { slug: "obsidian-cli", categoryId: "memory-knowledge", shortDescription: "Obsidian vault CLI operations" },

  // Research & Intelligence
  { slug: "deep-research", categoryId: "research-intel", shortDescription: "Multi-source research synthesis" },
  { slug: "deep-dive-research-orchestrator", categoryId: "research-intel", shortDescription: "Coordinated research specialists" },
  { slug: "financial-deep-research", categoryId: "research-intel", shortDescription: "Financial market analysis" },
  { slug: "competitor-intel", categoryId: "research-intel", shortDescription: "Competitive intelligence" },
  { slug: "technical-research", categoryId: "research-intel", shortDescription: "Technical spike investigations" },

  // Observability & Debugging
  { slug: "sentry-fix-issues", categoryId: "observability", shortDescription: "Sentry issue resolution" },
  { slug: "sentry-react-setup", categoryId: "observability", shortDescription: "Sentry React integration" },
  { slug: "sentry-setup-logging", categoryId: "observability", shortDescription: "Sentry structured logging" },
  { slug: "langsmith-trace", categoryId: "observability", shortDescription: "LangSmith trace observability" },
  { slug: "langsmith-fetch", categoryId: "observability", shortDescription: "LangSmith execution debugging" },

  // Deployment & Infrastructure
  { slug: "use-railway", categoryId: "deployment", shortDescription: "Railway infrastructure ops" },
  { slug: "railway-deployment", categoryId: "deployment", shortDescription: "Railway deployment lifecycle" },
  { slug: "vercel-cli", categoryId: "deployment", shortDescription: "Vercel CLI management" },
  { slug: "deployment", categoryId: "deployment", shortDescription: "App Store & Play Store deploy" },
  { slug: "cicd-workflows", categoryId: "deployment", shortDescription: "EAS CI/CD workflow YAML" },
  { slug: "symphony", categoryId: "deployment", shortDescription: "Symphony orchestration engine" },

  // Next.js & React
  { slug: "next-best-practices", categoryId: "nextjs-react", shortDescription: "Next.js conventions & patterns" },
  { slug: "next-cache-components", categoryId: "nextjs-react", shortDescription: "PPR & cache directives" },
  { slug: "next-upgrade", categoryId: "nextjs-react", shortDescription: "Next.js version migration" },
  { slug: "next-forge", categoryId: "nextjs-react", shortDescription: "next-forge SaaS template" },
  { slug: "vercel-react-best-practices", categoryId: "nextjs-react", shortDescription: "React performance optimization" },
  { slug: "vercel-composition-patterns", categoryId: "nextjs-react", shortDescription: "Scalable React composition" },
  { slug: "cra-to-next-migration", categoryId: "nextjs-react", shortDescription: "CRA to Next.js migration" },
  { slug: "data-fetching", categoryId: "nextjs-react", shortDescription: "Network & data fetching patterns" },

  // Mobile & Expo
  { slug: "building-ui", categoryId: "mobile-expo", shortDescription: "Expo Router app building" },
  { slug: "vercel-react-native-skills", categoryId: "mobile-expo", shortDescription: "React Native best practices" },
  { slug: "tailwind-setup", categoryId: "mobile-expo", shortDescription: "Tailwind CSS in Expo" },
  { slug: "use-dom", categoryId: "mobile-expo", shortDescription: "Expo DOM components" },
  { slug: "dev-client", categoryId: "mobile-expo", shortDescription: "Expo dev client builds" },
  { slug: "upgrading-expo", categoryId: "mobile-expo", shortDescription: "Expo SDK upgrades" },
  { slug: "api-routes", categoryId: "mobile-expo", shortDescription: "Expo Router API routes" },

  // Design & UI Systems
  { slug: "building-components", categoryId: "design-ui", shortDescription: "Composable UI components" },
  { slug: "frontend-design", categoryId: "design-ui", shortDescription: "Production-grade interfaces" },
  { slug: "web-design-guidelines", categoryId: "design-ui", shortDescription: "Web Interface Guidelines audit" },
  { slug: "liquid-glass-design", categoryId: "design-ui", shortDescription: "iOS 26 Liquid Glass" },
  { slug: "axiom-liquid-glass", categoryId: "design-ui", shortDescription: "Liquid Glass implementation" },
  { slug: "streamdown", categoryId: "design-ui", shortDescription: "Streaming Markdown renderer" },

  // JSON-Render Ecosystem
  { slug: "json-render-core", categoryId: "json-render", shortDescription: "Core schemas & catalogs" },
  { slug: "json-render-react", categoryId: "json-render", shortDescription: "React JSON renderer" },
  { slug: "json-render-react-native", categoryId: "json-render", shortDescription: "React Native renderer" },
  { slug: "json-render-shadcn", categoryId: "json-render", shortDescription: "shadcn/ui components" },
  { slug: "json-render-remotion", categoryId: "json-render", shortDescription: "Remotion video renderer" },

  // MCP & Protocol Integration
  { slug: "building-mcp-servers", categoryId: "mcp-protocol", shortDescription: "MCP server development" },
  { slug: "mcp-builder", categoryId: "mcp-protocol", shortDescription: "MCP tool & resource design" },
  { slug: "mcp-integration-expert", categoryId: "mcp-protocol", shortDescription: "MCP integration workflows" },
  { slug: "ucp", categoryId: "mcp-protocol", shortDescription: "Universal Commerce Protocol" },

  // Database & API
  { slug: "using-neon", categoryId: "db-api", shortDescription: "Neon Serverless Postgres" },
  { slug: "api-documentation", categoryId: "db-api", shortDescription: "API documentation practices" },
  { slug: "workflow", categoryId: "db-api", shortDescription: "Durable resumable workflows" },
  { slug: "workflow-init", categoryId: "db-api", shortDescription: "Workflow DevKit setup" },

  // QA & Browser Testing
  { slug: "dogfood", categoryId: "qa-browser", shortDescription: "Exploratory QA & bug hunting" },
  { slug: "gstack", categoryId: "qa-browser", shortDescription: "Headless browser QA" },
  { slug: "agent-browser", categoryId: "qa-browser", shortDescription: "Browser automation CLI" },
  { slug: "before-and-after", categoryId: "qa-browser", shortDescription: "Visual diff screenshots" },
  { slug: "rams", categoryId: "qa-browser", shortDescription: "Accessibility & design review" },

  // CLI & Workflow Tooling
  { slug: "domain-cli", categoryId: "cli-workflow", shortDescription: "CLI tool development" },
  { slug: "turborepo", categoryId: "cli-workflow", shortDescription: "Turborepo monorepo management" },
  { slug: "autoship", categoryId: "cli-workflow", shortDescription: "Automated changeset releases" },
  { slug: "linear-cli", categoryId: "cli-workflow", shortDescription: "Linear issue management" },
  { slug: "gsd", categoryId: "cli-workflow", shortDescription: "Solo dev project management" },
  { slug: "spec-driven-development", categoryId: "cli-workflow", shortDescription: "Spec-driven dev workflow" },

  // Design Tooling
  { slug: "remotion-best-practices", categoryId: "design-tooling", shortDescription: "Remotion video creation" },
  { slug: "ai-elements", categoryId: "design-tooling", shortDescription: "AI chat UI components" },
  { slug: "app-store-optimization", categoryId: "design-tooling", shortDescription: "ASO for mobile apps" },

  // Platform Specialties
  { slug: "rust-best-practices", categoryId: "platform", shortDescription: "Idiomatic Rust patterns" },
  { slug: "local-llm-ops", categoryId: "platform", shortDescription: "Ollama on Apple Silicon" },
  { slug: "garmin-connect", categoryId: "platform", shortDescription: "Garmin health data" },
  { slug: "find-skills", categoryId: "platform", shortDescription: "Skill discovery & install" },
  { slug: "skill-creator", categoryId: "platform", shortDescription: "Custom skill creation" },
  { slug: "alkosto-wait-optimizer", categoryId: "platform", shortDescription: "Promotion wait optimization" },
  { slug: "ralph-loop", categoryId: "platform", shortDescription: "Ralph Loop plugin" },
  { slug: "loop", categoryId: "platform", shortDescription: "Recurring task runner" },

  // Simulation & Optimization
  { slug: "openrocket-sim", categoryId: "simulation", shortDescription: "Headless rocket simulation & EGRI" },
];

// Derived aggregates
export const totalSkills = skills.length;
export const totalCategories = categories.length;
export const skillsByCategory = categories.map((cat) => ({
  ...cat,
  skills: skills.filter((s) => s.categoryId === cat.id),
  count: skills.filter((s) => s.categoryId === cat.id).length,
}));
