# X Thread — BroomVA Agent OS Stack Launch

## Thread: 12 Posts

---

### 1/12 — Hook (attach video)

We just open-sourced our Agent OS stack.

37K lines of Rust. 31 crates. 1,000 tests. 16 agent skills. 5 production apps.

One unified architecture for building autonomous AI agents that actually work.

Here's the full breakdown:

🧵

---

### 2/12 — The Core Insight

Most agent frameworks treat LLMs like chatbots with tools.

We treat them like controllers in a feedback loop.

The agent has a typed state vector. Six operating modes. An 8-phase tick lifecycle. Every state transition has provenance.

This isn't a wrapper around an API. It's an operating system.

---

### 3/12 — Arcan: The Runtime (attach architecture diagram)

Arcan is the agent's brain.

Strict loop: reconstruct state → call provider → execute tools → stream results.

File edits are content-addressed (Blake3). The agent can't blindly overwrite your code.

Multi-provider: Claude, GPT, Gemini. Unified streaming. Fully replayable sessions.

---

### 4/12 — Lago: The Memory

Lago is Git for agent state.

Append-only event journal on redb. Content-addressed blob storage (SHA-256 + zstd). Branching filesystem for parallel explorations.

Every action is an event. Every session is replayable. Nothing is lost.

---

### 5/12 — Autonomic: The Self-Regulator

Agents need homeostasis.

Autonomic monitors three pillars:
- Operational: is the agent healthy?
- Cognitive: is it making progress?
- Economic: is it spending wisely?

HysteresisGate prevents mode-flapping. Advisory model — the runtime consults but can't be blocked.

---

### 6/12 — Symphony: The Orchestrator

One agent is useful. Multiple coordinated agents are transformative.

Symphony: poll/dispatch/worker/reconcile daemon.

Assigns issues to agents. Tracks workspace state. Enforces control gates. Real-time monitoring.

Symphony Cloud: the managed SaaS so teams don't run their own infra.

---

### 7/12 — The Consciousness Stack (attach diagram)

Agents need memory that persists across sessions.

We built three substrates:

1. Control Metalayer — behavioral governance (setpoints, sensors, gates)
2. Knowledge Graph — declarative memory (Obsidian wikilinks)
3. Episodic Memory — conversation logs bridged to searchable docs

Together: persistent, governable agent consciousness.

---

### 8/12 — 16 Skills, 6 Layers

Skills are composable units of agent intelligence.

Foundation: safety shields, control loops, harness engineering
Memory: consciousness architecture, knowledge graphs, prompt library
Orchestration: Symphony, scaffolding, EGRI self-improvement
Research: multi-dimensional investigation, discovery
Design: Arcan Glass (frosted glass UI), Next.js templates
Specialty: decision optimization, content pipelines

---

### 9/12 — Why Rust

Agents aren't scripts. They're daemons.

They run for hours. Manage thousands of events. Execute untrusted tools. Need restarts without state loss. Coordinate over networks.

Rust gives us: memory safety without GC, fearless concurrency, predictable latency, type-driven invalid-state prevention, single-binary deployment.

---

### 10/12 — The Products (attach screenshots)

Built on the stack:

- chatOS: multi-model AI chat (Next.js 16, AI SDK v6)
- Symphony Cloud: managed agent orchestration SaaS
- Mission Control: Tauri desktop with Liquid Glass UI
- Control: local-first developer cockpit
- Arcan Glass: AI-native design system

Rust core + TypeScript interfaces + skill intelligence.

---

### 11/12 — The Architecture Scorecard

Where we stand today:

Agent Loop: 9/10
Persistence: 10/10
Tool Harness: 9/10
Memory: 8/10
Observability: 8/10
Security: 4/10 (OS-level sandbox planned)

Honest about gaps. Shipping anyway. The roadmap has 7 phases — we're on Phase 0 (stabilization).

---

### 12/12 — CTA

We're building the infrastructure layer for the agent era.

If you believe LLMs are controllers — not chatbots — and agents need real operating system primitives, we'd love your eyes on this.

Install the skill stack: `npx skills add broomva/bstack`

What would you build on this?

---

## Reply Templates

### Reply to "Why not just use LangChain/CrewAI/AutoGen?"

Those are orchestration frameworks. We're building an operating system.

The difference: we own the persistence layer (Lago), the regulation layer (Autonomic), the tool sandbox (Praxis), and the governance layer (Control Kernel).

When your agent corrupts its state at 3 AM, do you want a framework or an OS?

### Reply to "37K LOC seems like a lot for agents"

Linux kernel: 30M LOC. PostgreSQL: 1.4M LOC. Tokio: 70K LOC.

Infrastructure is supposed to be substantial. The whole point is that application developers write less code because the OS handles the hard parts.

chatOS (our chat app) is tiny. Because Arcan, Lago, and Autonomic handle state, persistence, and regulation.

### Reply to "Is this production-ready?"

Phase 0 (stabilization). 1,000 tests passing. Core loop functional. Multi-provider support working.

Known gaps: OS-level sandbox not enforced yet (security 4/10), branching not exposed in API, network isolation declared but not implemented.

We're honest about what works and what doesn't. That's the point of open-sourcing early.

### Reply to "How does this compare to Claude Code / Cursor / Devin?"

Those are products. This is infrastructure.

Claude Code is an excellent coding agent. Arcan is the runtime you'd build Claude Code on top of.

Different layer of the stack. Complementary, not competitive.

### Reply to "What's the business model?"

Symphony Cloud is the managed SaaS (Stripe billing, Neon PostgreSQL). Open-source engine, proprietary cloud.

Same model as GitLab, Supabase, Neon. Open core with managed service.

### Reply to interest in contributing

DMs open. The repo has CLAUDE.md files in every project directory with full context.

Start with `make smoke` — if all checks pass, you're ready. The harness engineering playbook skill documents the development workflow.

### Reply to "What about Python interop?"

The Autoany EGRI kernel has a Python skill layer. Praxis (tool engine) can execute any subprocess.

But the core infrastructure — the event journal, the agent loop, the homeostasis controller — those stay in Rust. Performance and safety guarantees matter at the infrastructure layer.

TypeScript handles web UIs. Python handles ML/data tasks. Rust handles everything that needs to be reliable.

