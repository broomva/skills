# BroomVA Agent OS Stack — Product Launch Content Package

## Content Inventory

### LinkedIn Posts (5 posts)

| # | File | Topic | Angle |
|---|------|-------|-------|
| 1 | `posts/linkedin-launch-post.md` — Post 1 | Main launch announcement | Full stack overview with numbers |
| 2 | `posts/linkedin-launch-post.md` — Post 2 | Architecture deep dive | 6-layer technical walkthrough |
| 3 | `posts/linkedin-launch-post.md` — Post 3 | Skills layer | 16 skills across 6 layers |
| 4 | `posts/linkedin-launch-post.md` — Post 4 | Why Rust | Systems programming for agents |
| 5 | `posts/linkedin-launch-post.md` — Post 5 | Product showcase | 5 products built on the stack |
| 6 | `posts/linkedin-consciousness-post.md` | Agent consciousness | Three-substrate memory architecture |
| 7 | `posts/linkedin-skills-post.md` — Post 1 | Skills composability | Why skills beat prompts |
| 8 | `posts/linkedin-skills-post.md` — Post 2 | Arcan Glass design system | AI-native visual identity |
| 9 | `posts/linkedin-rust-post.md` | Why Rust for agents | Systems programming argument |

### X Threads (3 threads)

| # | File | Posts | Topic |
|---|------|-------|-------|
| 1 | `posts/x-thread-launch.md` | 12 + 6 reply templates | Main launch thread |
| 2 | `posts/x-thread-technical.md` | 8 | Control theory for AI agents |
| 3 | `posts/x-thread-products.md` | 7 | Products built on Agent OS |

### Video (Remotion)

| File | Duration | Resolution | Content |
|------|----------|------------|---------|
| `video/` | 30s | 1080×1080 | Animated stack walkthrough |

**Scenes:**
1. Intro (4s) — Brand + title + metrics pills
2. 7× Layer scenes (2.5s each, 17.5s) — Kernel → Runtime → Persistence → Regulation → Tools → Orchestration → Consciousness
3. Products (5s) — 5 product cards with slide-in animation
4. Outro (4s) — Tagline + CTA + brand

**Render commands:**
```bash
cd video && bun install
npx remotion studio                          # Preview
npx remotion render BstackLaunch out/bstack-launch.mp4   # H.264
npx remotion render BstackLaunch out/bstack-launch.gif --every-nth-frame=3  # GIF fallback
```

### Reply Templates (in x-thread-launch.md)

| Reply to | Key message |
|----------|-------------|
| "Why not LangChain/CrewAI?" | Framework vs OS — we own persistence, regulation, sandbox, governance |
| "37K LOC is a lot" | Infrastructure should be substantial — apps are tiny because OS handles hard parts |
| "Is this production-ready?" | Phase 0, honest about gaps, 1000 tests, security 4/10 |
| "How does this compare to Cursor/Devin?" | Different layer — product vs infrastructure, complementary |
| "Business model?" | Open core + managed SaaS (Symphony Cloud) |
| "How to contribute?" | DMs open, CLAUDE.md per project, `make smoke` to start |
| "Python interop?" | EGRI skill has Python layer, Praxis executes subprocesses, core stays Rust |

---

## Publishing Schedule (Suggested)

### Day 1: Launch
- **LinkedIn**: Main launch announcement (Post 1)
- **X**: Main launch thread (12 posts) + video attachment on post 1

### Day 2: Architecture
- **LinkedIn**: Architecture deep dive (Post 2)
- **X**: Control theory thread (8 posts)

### Day 3: Products
- **LinkedIn**: Product showcase (Post 5)
- **X**: Products thread (7 posts)

### Day 4: Why Rust
- **LinkedIn**: Why Rust post

### Day 5: Skills
- **LinkedIn**: Skills layer post

### Day 6: Consciousness
- **LinkedIn**: Agent consciousness post

### Day 7: Design
- **LinkedIn**: Arcan Glass design system post

---

## Key Metrics to Reference

| Metric | Value |
|--------|-------|
| Lines of Rust | 37,000 |
| Rust crates | 31 |
| Tests passing | 1,000/1,000 |
| Agent skills | 16 |
| Skill layers | 6 |
| Products shipped | 5 |
| Architecture scorecard — Agent Loop | 9/10 |
| Architecture scorecard — Persistence | 10/10 |
| Architecture scorecard — Tool Harness | 9/10 |
| Architecture scorecard — Memory | 8/10 |
| Architecture scorecard — Observability | 8/10 |
| Architecture scorecard — Security | 4/10 |
| Operating modes | 6 |
| Tick lifecycle phases | 8 |
| Autonomic pillars | 3 |
| Consciousness substrates | 3 |

## Hashtags

**Primary**: #AgentOS #Rust #AI #OpenSource
**Secondary**: #AutonomousAgents #LLM #DeveloperTools #SystemsProgramming
**Topical**: #ControlSystems #AgentArchitecture #DesignSystems #Composability

## Core Messaging

**Tagline**: "LLMs are controllers, not chatbots."

**One-liner**: "37K lines of Rust infrastructure for building autonomous AI agents that actually work in production."

**Elevator pitch**: "BroomVA's Agent OS stack treats LLMs as controllers in feedback loops — with typed state vectors, event-sourced persistence, homeostatic regulation, and a three-substrate consciousness architecture. 31 Rust crates, 16 composable skills, 5 production applications. Open source."

**Contrarian hook**: "Most agent frameworks treat the LLM like a chatbot with tools. We treat it like a controller in a feedback loop. The difference matters."

---

## Asset Inventory (Final)

### Video (Rendered)

| File | Size | Format | Use |
|------|------|--------|-----|
| `video/out/bstack-launch.mp4` | 2.7 MB | H.264 1080x1080 30fps 30s | Primary X/LinkedIn video attachment |
| `video/out/bstack-launch.gif` | 4.1 MB | GIF 1080x1080 | Fallback/preview |
| `assets/skills-showcase.mp4` | 4.5 MB | MP4 | Skills-focused video (X thread 1/12) |
| `assets/skills-showcase.gif` | 6.8 MB | GIF | Skills showcase fallback |
| `assets/symphony-forge-showcase.mp4` | 5.0 MB | MP4 | Symphony Forge demo video |
| `assets/symphony-forge-showcase.gif` | 1.3 MB | GIF | Symphony Forge quick preview |

### Video Frame Stills (1080x1080 PNG)

| File | Scene | Attach to |
|------|-------|-----------|
| `assets/frame-intro.png` | Agent OS title + 5 metrics pills | LinkedIn Post 1, X 1/12 |
| `assets/frame-kernel-fix.png` | KERNEL: aiOS, AgentStateVector, 8-Phase Tick | LinkedIn Post 2, X 3/12 |
| `assets/frame-runtime-fix.png` | RUNTIME: Arcan, Hashline, Multi-Provider | X 3/12 |
| `assets/frame-persistence-fix.png` | PERSISTENCE: Lago, Event Journal, Blob Store | X 4/12 |
| `assets/frame-regulation-fix.png` | REGULATION: Autonomic, Operational/Cognitive/Economic | X 5/12 |
| `assets/frame-tools-fix.png` | TOOLS: Praxis, Blake3, FsPolicy, MCP Bridge | LinkedIn Post 2 |
| `assets/frame-orchestration-fix.png` | ORCHESTRATION: Symphony, Dispatch, Control Gates | X 6/12 |
| `assets/frame-consciousness-fix.png` | CONSCIOUSNESS: Control Metalayer, Knowledge Graph, Episodic Memory | LinkedIn Consciousness post, X 7/12 |
| `assets/frame-products.png` | BUILT ON THE STACK: 5 product cards | LinkedIn Post 5, X 10/12 |
| `assets/frame-outro.png` | "LLMs are controllers. Not chatbots." + CTA | All closing posts |

### Symphony Cloud Assets (from existing project)

| File | Content | Use |
|------|---------|-----|
| `assets/frame-intro-fix.png` | Symphony Forge intro frame | Symphony Cloud posts |
| `assets/frame-install-fix.png` | Installation guide | Technical posts |
| `assets/frame-commands-fix.png` | Command reference | Technical posts |
| `assets/frame-filetree.png` | File tree navigation | Architecture posts |
| `assets/frame-layers.png` | Layer visualization | Architecture diagram |
| `assets/frame-metalayer.png` | Metalayer architecture | Consciousness post |
| `assets/checks-passed.png` | Green checks status | Quality/testing posts |
| `assets/hero-dark.svg` | Dark hero image | Header/banner |
| `assets/symphony-logo-dark.svg` | Symphony logo | Branding |

---

## Post → Asset Mapping

### Day 1: Launch

**LinkedIn Post 1** (Main announcement):
- Attach: `video/out/bstack-launch.mp4` (primary) or `assets/frame-intro.png` (static fallback)
- Carousel option: `frame-intro.png` → `frame-kernel-fix.png` → `frame-products.png` → `frame-outro.png`

**X Thread** (12 posts):
- 1/12: Attach `video/out/bstack-launch.mp4`
- 3/12 (Arcan): Attach `assets/frame-runtime-fix.png`
- 7/12 (Consciousness): Attach `assets/frame-consciousness-fix.png`
- 10/12 (Products): Attach `assets/frame-products.png`

### Day 2: Architecture

**LinkedIn Post 2** (Architecture):
- Carousel: `frame-kernel-fix.png` → `frame-persistence-fix.png` → `frame-regulation-fix.png` → `frame-tools-fix.png` → `frame-orchestration-fix.png`

**X Control Theory Thread**:
- 1/8: Attach `assets/frame-intro.png`
- 4/8 (State Vector): Attach `assets/frame-kernel-fix.png`
- 6/8 (Event Sourcing): Attach `assets/frame-persistence-fix.png`

### Day 3: Products

**LinkedIn Post 5** (Products):
- Attach: `assets/frame-products.png`
- Alt: `assets/symphony-forge-showcase.gif`

**X Products Thread**:
- 1/7: Attach `assets/frame-products.png`
- 4/7 (Mission Control): Attach `assets/frame-metalayer.png`

### Day 4: Why Rust

**LinkedIn Rust Post**:
- Attach: `assets/frame-outro.png` (tagline image)

### Day 5: Skills

**LinkedIn Skills Post**:
- Attach: `assets/skills-showcase.gif` or `assets/skills-showcase.mp4`

### Day 6: Consciousness

**LinkedIn Consciousness Post**:
- Attach: `assets/frame-consciousness-fix.png`
- Alt carousel: `frame-metalayer.png` → `frame-consciousness-fix.png`

### Day 7: Design

**LinkedIn Arcan Glass Post**:
- Attach: `assets/hero-dark.svg` or `assets/frame-intro.png` (brand showcase)
