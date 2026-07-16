# Skills

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![skills.sh](https://img.shields.io/badge/skills.sh-directory-8B5CF6)](https://skills.sh/)
[![Agent Skills spec](https://img.shields.io/badge/spec-agentskills.io-blue)](https://agentskills.io/specification)
[![Monorepo layout](https://img.shields.io/badge/layout-anthropics%2Fskills-orange)](https://github.com/anthropics/skills)

A curated monorepo of [Agent Skills](https://agentskills.io/specification) — 68 Tier-2 skills + the catalog/showcase. Compatible with Claude Code, Codex, Cursor, Gemini CLI, Goose, Copilot, and any agent that consumes the `SKILL.md` standard.

Layout: **no root `SKILL.md`** (the README is the discovery surface). Skills are bucketed by single-noun **category** at `skills/<category>/<name>/SKILL.md` (depth-2). skills.sh discovers depth-2 by default — **requires CLI ≥ v1.5.8** — and `--skill <name>` resolves path-independently, so install commands don't reference the category.

## Quick install

```bash
# List everything in the monorepo
npx skills add broomva/skills --list

# Install a specific Tier-2 skill
npx skills add broomva/skills --skill handoff
npx skills add broomva/skills --skill make-spec

# The catalog skill itself (browse-the-inventory surface)
npx skills add broomva/skills --skill skills-catalog

# Install everything (use sparingly — large prompt-budget footprint)
npx skills add broomva/skills --skill '*'
```

> **Note:** **requires skills.sh CLI ≥ v1.5.8** (PR #1272), which discovers category buckets `skills/<category>/<name>/SKILL.md` at depth-2 by default — on both the local and remote/blob install paths. No `--full-depth` flag is needed (that's only for depth-3+); buckets are exactly one level. On older CLIs the bucketed skills are not found — run `npx skills@latest …` or upgrade. `--skill <name>` resolves by frontmatter `name`, so it is path-independent (the category never appears in the install command).

## Repository layout

| Path | Purpose |
|---|---|
| [`skills/`](skills/) | **The monorepo.** Skills bucketed by single-noun category at `skills/<category>/<name>/` (depth-2), each with `SKILL.md` + optional `references/`/`scripts/`/`assets/` per the [agentskills.io spec](https://agentskills.io/specification). Includes the catalog skill at [`skills/tooling/skills-catalog/`](skills/tooling/skills-catalog/). |
| [`references/skills-inventory.md`](references/skills-inventory.md) | Full categorized inventory across all 15 domains (companion to the catalog skill) |
| [`skills-showcase/`](skills-showcase/) | Remotion video + X thread renderer for the inventory |
| [`.github/workflows/`](.github/workflows/) | CI: SKILL.md frontmatter lint (validates `name` matches parent dir + required fields present per agentskills.io spec) |
| `_shared/` | (reserved) shared utilities used by multiple Tier-2 skills |

## Tier-2 skills (vendored in this monorepo)

**75 skills** organized into **22 single-noun category buckets** at `skills/<category>/<name>/` (depth-2; requires skills.sh CLI ≥ v1.5.8). Install any skill path-independently: `npx skills add broomva/skills --skill <name>`.

### Governance & control — `skills/governance/`

| Skill | What it does |
|---|---|
| [`agentic-control-kernel`](skills/governance/agentic-control-kernel/) | Unifying control-systems metalayer for LLM-as-controller agent development |
| [`architecture-design-principles`](skills/governance/architecture-design-principles/) | Distilled architecture & design principles for building self-service developer platforms, control-plane / data-plane separation, and edge-centralized cross-cutting… |
| [`bstack`](skills/governance/bstack/) | bstack primer — the agent-readable contract for the Broomva Stack's twenty automation primitives (P1–P20) that turn an agent-driven workspace into a self-operating system (the primer skill; the bstack CLI is a separate clone + bootstrap product) |
| [`cross-review`](skills/governance/cross-review/) | bstack P20 — Cross-Model Adversarial Review Gate |
| [`dogfood`](skills/governance/dogfood/) | Per-bstack-P11 reflex 7+16 — explicitly trigger the Dogfood Plan + per-stack cookbook + Dogfood Receipt sequence |
| [`harness-engineering-playbook`](skills/governance/harness-engineering-playbook/) | Implement OpenAI Harness Engineering practices in any repository — AGENTS.md, PLANS.md, deterministic smoke/test/lint harness commands, strict architecture… |

### Orchestration & autonomy — `skills/orchestration/`

| Skill | What it does |
|---|---|
| [`autonomous`](skills/orchestration/autonomous/) | Use when the user has agreed on a plan or selected from suggested options and wants the agent to execute the work autonomously without further instruction |
| [`eve-forge`](skills/orchestration/eve-forge/) | Forge a personalized eve agent for a business end-to-end — absorb the business's artifacts, author the `agent/` dir, validate, and deploy |
| [`governed-autonomy-loop`](skills/orchestration/governed-autonomy-loop/) | Turn any work-queue + enforcement pipeline into a self-driving, self-healing, human-minimal autonomy loop with a control-systems safety envelope — a metacognitive governor that drives isolated arcs and never performs the irreversible act itself |
| [`handoff`](skills/orchestration/handoff/) | Fresh-session handoff doc drafting |
| [`p9`](skills/orchestration/p9/) | P9 — Broomva productive-wait primitive (the wait optimizer) |
| [`persist`](skills/orchestration/persist/) | bstack P12 — Persistent Loop Discipline |
| [`role-x`](skills/orchestration/role-x/) | bstack P17 — Lens-Routed Request Articulation |

### Skill & prompt tooling — `skills/tooling/`

| Skill | What it does |
|---|---|
| [`broomva-cli`](skills/tooling/broomva-cli/) | CLI for broomva.tech — manage prompts, skills, and context from the terminal |
| [`make-spec`](skills/tooling/make-spec/) | Scaffold a substantive human-readable design doc (spec / plan / ADR / report / PR explainer) as native HTML using the workspace's canonical Broomva dark theme |
| [`prompt-library`](skills/tooling/prompt-library/) | Manage and retrieve reusable prompts from broomva.tech or any compatible prompt repository |
| [`skillify`](skills/tooling/skillify/) | Skillify-as-a-verb — distill a working session (or a pointed-at chat history) into a permanent, TESTED, registered skill at the end of a workflow |
| [`skills-catalog`](skills/tooling/skills-catalog/) | Canonical reference inventory of 84 agent skills across 15 domains, with a Remotion video showcase generator and X thread copy |

### Knowledge & memory — `skills/knowledge/`

| Skill | What it does |
|---|---|
| [`bookkeeping`](skills/knowledge/bookkeeping/) | Universal knowledge engine — scores, promotes, and compounds knowledge across all sources into a permanent, query-able entity graph |
| [`braindump`](skills/knowledge/braindump/) | Takes raw unstructured thoughts, voice transcript dumps, or stream-of-consciousness text and auto-files them into the right Obsidian vault folders with tags,… |
| [`colombia-conflict`](skills/knowledge/colombia-conflict/) | Knowledge engine over the Colombian Truth Commission report *Hay Futuro Si Hay Verdad* (2022) — findings, statistics, actor responsibilities, differential harms, lexicon, and the 67-recommendation non-repetición roadmap, with a kg/LLM-wiki retrieval engine and an `align` policy-vs-roadmap scorer |
| [`kg`](skills/knowledge/kg/) | Load relevant entities from the bstack knowledge graph (research/entities/) for a given topic |

### Research — `skills/research/`

| Skill | What it does |
|---|---|
| [`checkit`](skills/research/checkit/) | Ingest-and-integrate an artifact someone points at with a terse, deliberately under-articulated directive — "check this out", "lets research this", "look into this",… |
| [`deep-dive-research-orchestrator`](skills/research/deep-dive-research-orchestrator/) | Conduct comprehensive multi-dimensional research on any subject using coordinated AI research specialists |

### Strategy & decisions — `skills/strategy/`

| Skill | What it does |
|---|---|
| [`decision-log`](skills/strategy/decision-log/) | Captures a decision with context, alternatives considered, and rationale, then links it to the relevant project doc in the vault |
| [`phronesis`](skills/strategy/phronesis/) | AI-native advisory practice for the Broomva ecosystem |
| [`pre-mortem`](skills/strategy/pre-mortem/) | Assumes a project has already failed, works backward to identify the top causes, scores them by likelihood and impact, and outputs a mitigation plan |
| [`premortem`](skills/strategy/premortem/) | Run a premortem on any plan, launch, product, hire, strategy, or decision |
| [`strategy-critique`](skills/strategy/strategy-critique/) | Reads a strategy doc and writes a red-team critique with gaps, risks, and missing assumptions |

### Operating cadence — `skills/cadence/`

| Skill | What it does |
|---|---|
| [`drift-check`](skills/cadence/drift-check/) | Compares stated priorities against where time and effort actually went, and produces a strategy drift report |
| [`morning-briefing`](skills/cadence/morning-briefing/) | Reads open action items, this week's priorities, and recent vault updates, then produces a focused "start your day" brief |
| [`stakeholder-update`](skills/cadence/stakeholder-update/) | Takes one set of project facts and generates three versions: technical for engineering, business-impact for leadership, and customer-facing for success teams |
| [`weekly-review`](skills/cadence/weekly-review/) | Scans the vault for updates from the past week, surfaces what changed, and flags what needs attention |

### Publishing & growth — `skills/publishing/`

| Skill | What it does |
|---|---|
| [`blog-post`](skills/publishing/blog-post/) | Full-stack blog post production — turns a topic, idea, or brief into a complete publishing package across written, social, and multimedia surfaces |
| [`content-creation`](skills/publishing/content-creation/) | Full-stack content creation pipeline: idea or reference to published blog post, audio narration, video, and social media distribution |
| [`revenuecast`](skills/publishing/revenuecast/) | revenuecast — turn a real-world capability into a self-demonstrating, high-throughput generative-AI revenue engine (the "Kleos" method) |
| [`seo-llmeo`](skills/publishing/seo-llmeo/) | SEO and LLM Engine Optimization (LLMEO) skill for BroomVA content |
| [`social-intelligence`](skills/publishing/social-intelligence/) | Autonomous social engagement + knowledge extraction loop for Moltbook and X/Twitter |

### Video & multimedia — `skills/video/`

| Skill | What it does |
|---|---|
| [`brainrot-for-good`](skills/video/brainrot-for-good/) | Produce high-retention, dopamine-aware video content using brainrot editing techniques — fast cuts, word-by-word captions, sound design, visual velocity, pattern… |
| [`content-engine`](skills/video/content-engine/) | Full-stack AI content studio — orchestrates visual DNA compilation, cinematic generation (via Higgsfield CLI or MCP), browser-automated tool execution, and… |
| [`creative-review`](skills/video/creative-review/) | Meta-review skill for validating generated creative assets (videos, images, designs) against a reference style brief |
| [`launch-video`](skills/video/launch-video/) | Produce polished product launch videos using the Liquid Glass aesthetic — dark void backgrounds, 3D perspective floating UI panels, particle effects, spring… |
| [`ltx-video`](skills/video/ltx-video/) | Set up, configure, and run LTX-2/LTX-2.3 (Lightricks) for AI video and audio generation |
| [`video-cut`](skills/video/video-cut/) | Edit raw footage into a finished cut by conversation, fully local |

### Audio & music — `skills/audio/`

| Skill | What it does |
|---|---|
| [`livecoding`](skills/audio/livecoding/) | Algorave-grade livecoded music workflow — TidalCycles patterns (Haskell DSL driving SuperDirt over OSC) + Hydra-synth visuals (browser or VS Code Simple Browser via a… |
| [`omnivoice`](skills/audio/omnivoice/) | Local TTS, voice cloning, voice design, and video dubbing via the OmniVoice Studio MCP server (open-source ElevenLabs alternative; nothing leaves the machine, runs on… |

### Design & brand — `skills/design/`

| Skill | What it does |
|---|---|
| [`arcan-glass`](skills/design/arcan-glass/) | BroomVA trademark web styling system — Arcan Glass design language for Next.js + Tailwind v4 + shadcn/ui projects |
| [`brand-icons`](skills/design/brand-icons/) | Brand icon and visual identity management for BroomVA projects |
| [`design-engineering`](skills/design/design-engineering/) | Premium design engineering skill for agentic workflows — produces high-end, distinctive UI designs using DESIGN.md as the portable contract across Pencil MCP (in-IDE… |
| [`tekton`](skills/design/tekton/) | Tekton — the shared architecture-intent substrate for co-designing systems with the agent |

### Finance & payments — `skills/finance/`

| Skill | What it does |
|---|---|
| [`finance-substrate`](skills/finance/finance-substrate/) | Personal finance and tax management substrate for Colombian residents |
| [`haima`](skills/finance/haima/) | Agentic finance engine for the Agent OS — x402 machine-to-machine payments, on-chain settlement, per-task revenue billing, and wallet management |
| [`investment-management`](skills/finance/investment-management/) | Investment management skill — portfolio construction, analysis, and execution |
| [`wealth-management`](skills/finance/wealth-management/) | Wealth management, financial planning, and investment analytics skill |

### Compute infrastructure — `skills/compute/`

| Skill | What it does |
|---|---|
| [`agentic-vps`](skills/compute/agentic-vps/) | Provision and harden a fresh Linux VPS into an autonomous-agent dev host using the capability-preserving model — the box IS the sandbox: full agent autonomy inside it… |
| [`colab-remote`](skills/compute/colab-remote/) | Orchestrate Google Colab Pro/Pro+ GPU instances as remote training backends via SSH |
| [`remote-gpu`](skills/compute/remote-gpu/) | Orchestrate a headless GPU server (NUC, cloud VM, or any SSH-accessible machine) from a local Mac or workstation |

### Model runtimes — `skills/models/`

| Skill | What it does |
|---|---|
| [`bitnet`](skills/models/bitnet/) | Microsoft BitNet — 1-bit LLM setup, inference, and benchmarking on CPU |
| [`heretic-abliteration`](skills/models/heretic-abliteration/) | Heretic — fully automatic LLM censorship removal (abliteration) and serving the result via Ollama |

### Messaging channels — `skills/messaging/`

| Skill | What it does |
|---|---|
| [`claude-code-channels`](skills/messaging/claude-code-channels/) | Set up Claude Code messaging channels for Telegram and Discord — bot creation, plugin installation, token configuration, access control (pairing, allowlists, guild… |
| [`claude-remote-sessions`](skills/messaging/claude-remote-sessions/) | Per-channel remote sessions for Claude Code via Discord and Telegram — each channel, thread, or chat gets its own isolated Claude Code session via tmux, with… |

### Robotics — `skills/robotics/`

| Skill | What it does |
|---|---|
| [`capx-agentic-robotics`](skills/robotics/capx-agentic-robotics/) | Agentic robotics with CaP-X — LLM-driven robot manipulation via code generation |
| [`orcahand`](skills/robotics/orcahand/) | Full-stack skill for the ORCA Hand — 17-DOF tendon-driven robotic hand (ETH Zurich) |

### Aerospace & RF — `skills/aerospace/`

| Skill | What it does |
|---|---|
| [`openrocket-sim`](skills/aerospace/openrocket-sim/) | Headless rocket design, simulation, and optimization using OpenRocket's Java core engine |
| [`sdr-satellite`](skills/aerospace/sdr-satellite/) | Software-defined radio (SDR) and satellite reception toolkit — what to install, what you can hear from space, and how to compose the open-source stack (SatDump,… |

### Neuroscience & BCI — `skills/neuroscience/`

| Skill | What it does |
|---|---|
| [`tribe-v2-agent-alignment`](skills/neuroscience/tribe-v2-agent-alignment/) | Use Meta's TRIBE v2 brain encoder to validate cortical alignment of AI model representations (LLaMA, V-JEPA2, Wav2Vec, or any encoder) and inform model selection in… |
| [`tribe-v2-bci-applied`](skills/neuroscience/tribe-v2-bci-applied/) | Applied BCI research and neuro-informed content optimization using Meta's TRIBE v2 brain encoder |
| [`tribe-v2-neuroscience`](skills/neuroscience/tribe-v2-neuroscience/) | In-silico neuroscience experiments using Meta's TRIBE v2 (TRansformer for In-silico Brain Experiments) |

### Healthcare — `skills/healthcare/`

| Skill | What it does |
|---|---|
| [`founder-mode-oncology`](skills/healthcare/founder-mode-oncology/) | Personalized cancer treatment navigation — maximal diagnostics, parallel therapy, therapeutic development, structure-based protein design |
| [`health`](skills/healthcare/health/) | Personal health knowledge graph — local-first ingest of Garmin (Apple Health, Whoop, Oura, CGM in v2+) traces into SQLite, projected to Obsidian daily-note… |

### Science — `skills/science/`

| Skill | What it does |
|---|---|
| [`ocean-genomics`](skills/science/ocean-genomics/) | Comprehensive bioinformatics and ocean genomics skill for eDNA metabarcoding, metagenomics, protein structure prediction, and marine biodiversity analysis |

### Commerce & procurement — `skills/commerce/`

| Skill | What it does |
|---|---|
| [`procurer`](skills/commerce/procurer/) | Grounded procurement research for any real-world need |
| [`swapit`](skills/commerce/swapit/) | Stateful, local-first household toxics inventory + swap engine |

### Everyday utilities — `skills/utilities/`

| Skill | What it does |
|---|---|
| [`gasgo`](skills/utilities/gasgo/) | Find the cheapest fuel/GNCV near a Colombian location — engine over live per-station open data (SICOM GNCV via datos.gov.co) with an explicit freshness verdict and honest coordinate resolution (municipal-centroid distances shown approximate) |
| [`alkosto-wait-optimizer`](skills/utilities/alkosto-wait-optimizer/) | Estimate optimal waiting time for Alkosto's "every 25/50 customers" promotion using either checkout-flow observations or winner announcement timestamps |

## Catalog inventory

The inventory covers every layer of the stack:

| Category | Count |
|---|---|
| AI & Agent Systems | 7 |
| Memory & Knowledge | 5 |
| Research & Intelligence | 5 |
| Observability & Debugging | 5 |
| Deployment & Infrastructure | 6 |
| Next.js & React | 8 |
| Mobile & Expo | 7 |
| Design & UI Systems | 6 |
| JSON-Render Ecosystem | 5 |
| MCP & Protocol Integration | 4 |
| Database & API | 4 |
| QA & Browser Testing | 5 |
| CLI & Workflow Tooling | 6 |
| Design Tooling | 3 |
| Platform Specialties | 8 |

Full details with descriptions in [`references/skills-inventory.md`](references/skills-inventory.md).

## Skills showcase

The [`skills-showcase`](skills-showcase/) tool generates a polished Remotion video (1080x1080, 30fps, 48s) and a 7-post X thread from the inventory data.

```bash
cd skills-showcase
npm install
npx remotion studio                    # Preview in browser
npx remotion render SkillsShowcase out/skills-showcase.mp4
npx remotion render SkillsShowcase out/skills-showcase.gif --every-nth-frame=3
```

Pre-rendered outputs are in [`skills-showcase/out/`](skills-showcase/out/).

## Browse & discover

```bash
npx skills find <query>
```

Browse the full ecosystem at [skills.sh](https://skills.sh/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for both flows: the **root-level catalog** flow (adding inventory entries, updating the showcase) and the **Tier-2 monorepo graduation** flow (adding a skill at `skills/<name>/`).

## License

[MIT](LICENSE)
