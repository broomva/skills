# LinkedIn Launch Post — BroomVA Agent OS Stack

## Post 1: Main Launch Announcement

---

We just open-sourced the Agent OS stack we've been building for the past year.

37,000 lines of Rust. 31 crates. 1,000 tests passing. One unified architecture for building autonomous AI agents that actually work in production.

Here's what's inside:

- **Arcan** — an agent runtime daemon with typed streaming events, content-addressed file edits, and fully replayable sessions
- **Lago** — append-only event journal with content-addressed blob storage (think Git for agent state)
- **Autonomic** — three-pillar homeostatic controller that keeps agents stable (operational, cognitive, economic regulation)
- **Praxis** — sandboxed tool execution engine with workspace isolation
- **Symphony** — orchestration daemon that coordinates multiple coding agents across repositories
- **Spaces** — SpacetimeDB-powered communication fabric for distributed agents

The core insight: an agent's message history IS its application state. Every action produces an immutable event. Every session can be replayed from its journal. No hidden state. No surprises.

On top of this, we built 5 production applications:
- chatOS (multi-model AI chat, Next.js 16 + AI SDK v6)
- Symphony Cloud (managed SaaS for agent orchestration)
- Mission Control (Tauri desktop app for terminal + agent management)
- Control (local-first developer cockpit with Git graph visualization)
- Arcan Glass (our design system — frosted glass UI for the AI era)

And 16 agent skills across 6 layers — from safety shields to episodic memory to self-improving EGRI loops.

The fundamental bet: LLMs are controllers, not chatbots. They need plant interfaces, safety shields, typed state vectors, and feedback loops — the same primitives that run industrial control systems.

We're calling it the bstack. It's how we think agents should be built.

Link in comments.

#AgentOS #Rust #AI #OpenSource #AutonomousAgents #LLM #DeveloperTools

---

## Post 2: Technical Deep Dive — Architecture

---

Most AI agent frameworks treat the LLM like a chatbot with tools.

We treat it like a controller in a feedback loop.

The difference matters. Here's the architecture behind our Agent OS stack:

**Layer 1: Kernel Contract (aiOS)**
Every agent has an AgentStateVector — a typed struct tracking homeostasis. Six operating modes: Explore, Execute, Verify, Recover, AskHuman, Sleep. An 8-phase tick lifecycle with provenance tracking on every state transition.

**Layer 2: Runtime (Arcan)**
The agent loop is strict: reconstruct state from event journal → call provider → execute tools → stream results. File edits are content-addressed (Blake3 hashes) — the agent can't blindly overwrite files. Multi-provider support (Claude, GPT, Gemini) with unified streaming.

**Layer 3: Persistence (Lago)**
Append-only event journal on redb. Content-addressed blob storage with SHA-256 + zstd compression. Branching filesystem for parallel explorations. RBAC policy enforcement. Everything is an event. Nothing is lost.

**Layer 4: Regulation (Autonomic)**
Three pillars: operational (is the agent healthy?), cognitive (is it making progress?), economic (is it spending wisely?). HysteresisGate prevents mode-flapping. Advisory model — Arcan consults; failures are non-fatal.

**Layer 5: Orchestration (Symphony)**
Poll/dispatch/worker/reconcile pattern for coordinating multiple agents. Control gates prevent unauthorized mutations. Real-time status monitoring via dashboard.

**Layer 6: Consciousness Stack**
Control metalayer (governance) + knowledge graph (Obsidian) + episodic memory (conversation logs). Three substrates that give agents persistent context across sessions.

The architecture scorecard: Agent Loop 9/10, Persistence 10/10, Tool Harness 9/10, Memory 8/10, Observability 8/10.

This isn't theory. It's running. 37K LOC of Rust, 1000 tests passing.

#SystemsEngineering #AgentArchitecture #Rust #ControlSystems #AI

---

## Post 3: The Skills Layer — Why 16 Skills Beat 1,000 Prompts

---

We stopped writing prompts and started writing skills.

A skill is a versioned, composable unit of agent capability — with its own context, tools, and evaluation criteria. Think of it as a microservice for agent intelligence.

Here are the 16 skills in the bstack, organized by layer:

**Foundation (3 skills)**
- Agentic Control Kernel — safety shields, typed plant interfaces, governance
- Control Metalayer Loop — setpoints, sensors, gates, feedback
- Harness Engineering Playbook — deterministic testing, smoke checks, CI gates

**Memory & Consciousness (3 skills)**
- Agent Consciousness — three-substrate persistent context architecture
- Knowledge Graph Memory — conversation logs → Obsidian wikilinks
- Prompt Library — reusable, versioned agent directives

**Orchestration (3 skills)**
- Symphony — multi-agent dispatch and coordination
- Symphony Forge — project scaffolding with built-in governance
- Autoany — Evaluator-Governed Recursive Improvement (EGRI)

**Research & Intelligence (3 skills)**
- Deep Dive Research Orchestrator — multi-dimensional investigation
- Skills catalog — inventory and discovery
- Skills Showcase — presentation and communication

**Design & Implementation (2 skills)**
- Arcan Glass — AI-native design system (frosted glass, OKLCh colors, P3 gamut)
- Next Forge — production-grade Next.js SaaS template

**Platform Specialties (2 skills)**
- Alkosto Wait Optimizer — probabilistic decision optimization
- Content Creation — research-to-publishing pipeline

The key principle: skills compose. An agent using Symphony can invoke Autoany to self-improve, consult the Control Kernel for safety, persist findings to the Knowledge Graph, and present results via Content Creation.

Install the full stack: `npx skills add broomva/bstack`

#AgentSkills #AI #DeveloperExperience #Composability

---

## Post 4: Why Rust for Agent Infrastructure

---

"Why Rust for AI agents? Isn't Python the obvious choice?"

We get this question a lot. Here's our answer:

Agents aren't scripts. They're daemons.

They run for hours. They manage state across thousands of events. They execute untrusted tool calls. They need to be restarted without losing context. They coordinate with other agents over networks.

This is systems programming. And Rust is the systems programming language.

Concrete benefits we've seen:

**1. Memory safety without GC pauses**
Our event journal (Lago) handles append-only writes with zero-copy reads. No GC pause spikes during critical agent decisions.

**2. Fearless concurrency**
Symphony coordinates multiple agents with shared state. Rust's ownership model catches data races at compile time — not at 3 AM in production.

**3. Predictable performance**
Autonomic (our homeostasis controller) makes real-time regulation decisions. Consistent sub-millisecond latency, not "usually fast but sometimes 100ms GC."

**4. Type-driven design**
Our 8-phase tick lifecycle and 6 operating modes are encoded in the type system. Invalid state transitions don't compile. The compiler is our first safety shield.

**5. Binary deployment**
One `arcand` binary. No dependency hell. No `pip install` nightmares. Ships to any Linux box.

We still use TypeScript where it makes sense — chatOS, Symphony Cloud, Mission Control frontends. But the agent brain, the persistence layer, the orchestrator core — those are Rust.

37K lines. 31 crates. 1,000 tests. Zero segfaults.

The agent OS should be as reliable as a real OS. That means Rust.

#Rust #SystemsProgramming #AI #AgentInfrastructure #Performance

---

## Post 5: Product Showcase — What You Can Build

---

Infrastructure is only as good as what you build on it.

Here are 5 products we've shipped on the Agent OS stack:

**chatOS — Multi-Model AI Chat**
Turborepo monorepo with Next.js 16, Vercel AI SDK v6, Better Auth. Supports Claude, GPT, Gemini, and Grok with unified streaming. Multi-platform bots (Slack, Teams, Discord). Full agent-native architecture with control metalayer governance.

**Symphony Cloud — Managed Agent Orchestration**
The SaaS layer on top of our open-source Symphony daemon. Next-forge template, Clerk auth, Stripe billing, Neon PostgreSQL. Lets teams deploy and manage coding agents without running infrastructure.

**Mission Control — Desktop Agent Cockpit**
Tauri 2.0 desktop app with Liquid Glass UI. Terminal multiplexing with per-project PTY sessions. Live git integration (status, commit log, diff viewer). Filesystem watching. Dockable layout persistence. 29 Rust tests, 38 frontend tests.

**Control — Local-First Developer Terminal**
Another Tauri app, focused on the individual developer. SQLite persistence, Git graph visualization with lane assignment, agent run recording, unified timeline. Local HTTP API on port 19420 for CLI and MCP access.

**Arcan Glass — AI-Native Design System**
Not a product you use — a product everything else looks like. 4-layer composable glass system, dark-first with light mode, OKLCh color space with P3 gamut enhancement. Drop-in globals.css for any Next.js + Tailwind v4 + shadcn/ui project.

The pattern: Rust core handles the hard problems (state, safety, persistence). TypeScript handles the interfaces (web, desktop, mobile). Skills handle the intelligence (governance, memory, orchestration).

Everything composes. Everything is governed. Everything is observable.

#ProductDevelopment #FullStack #AI #Tauri #NextJS #DesignSystems

