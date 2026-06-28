# X Thread — Products Built on Agent OS

## Thread: 7 Posts

---

### 1/7 — Hook (attach collage screenshot)

We built 5 products on top of our Rust Agent OS stack.

Each one proves a different thesis about how AI applications should be built.

Here's the product lineup and what we learned from each:

🧵

---

### 2/7 — chatOS: The Multi-Model Chat

chatOS is a Turborepo monorepo: Next.js 16 + Vercel AI SDK v6 + Better Auth.

Supports Claude, GPT, Gemini, and Grok with unified streaming. Ships with Slack, Teams, and Discord bots.

The lesson: chat is commodity. The moat is the infrastructure underneath — how you persist conversations, govern agent behavior, and compose tools.

---

### 3/7 — Symphony Cloud: The SaaS Play

Open-source orchestration engine (Symphony) + proprietary cloud layer.

Clerk auth. Stripe billing. Neon PostgreSQL. Drizzle ORM.

The lesson: every serious agent tool needs a managed service. Teams don't want to run daemons. They want a dashboard, billing, and someone to page at 3 AM.

---

### 4/7 — Mission Control: The Desktop Cockpit (attach screenshot)

Tauri 2.0 desktop app with our Liquid Glass UI design.

Terminal multiplexing (PTY per project). Live git integration. Filesystem watching. Dockable layouts.

29 Rust tests. 38 frontend tests.

The lesson: agents need human oversight, and oversight needs a great interface. Terminal + Git + file explorer in one pane, agent status in the next.

---

### 5/7 — Control: The Developer Terminal

Local-first Tauri app. SQLite persistence. Git graph visualization with lane assignment. Agent run recording. Unified timeline.

Exposes a local HTTP API (port 19420) for CLI and MCP tool access.

The lesson: the IDE is not enough. Developers working with agents need a dedicated surface for agent state, timeline, and history.

---

### 6/7 — Arcan Glass: The Design System

Not a product — a visual identity.

4-layer composable glass system. Dark-first with light mode. OKLCh color space with P3 gamut enhancement. Drop-in globals.css.

AI Blue (#0066FF) + Web3 Green (#00CC66).

The lesson: AI tools don't have to look like terminals. The frosted glass aesthetic signals: this is something new. Not another dark mode dashboard.

---

### 7/7 — The Pattern

Every product follows the same pattern:

Rust core: handles state, safety, persistence (the hard problems)
TypeScript shell: handles UI, routing, auth (the solved problems)
Skill layer: handles intelligence, governance, memory (the new problems)

Infrastructure should be invisible. The user sees a chat app, a dashboard, a terminal. Underneath: 37K lines of Rust making sure nothing breaks.

What would you build on this stack?

