# Skills Inventory

> 75 skills across 22 category buckets, mirroring the `skills/<category>/` directory layout. Regenerated from the README discovery surface (canonical). Last updated: 2026-07-16.

## Governance & control — `skills/governance/` (6)

| Skill | What it does |
|---|---|
| `agentic-control-kernel` | Unifying control-systems metalayer for LLM-as-controller agent development |
| `architecture-design-principles` | Distilled architecture & design principles for building self-service developer platforms, control-plane / data-plane separation, and edge-centralized cross-cutting |
| `bstack` | bstack primer — the agent-readable contract for the Broomva Stack's twenty automation primitives (P1–P20) that turn an agent-driven workspace into a self-operating system (the primer skill; the bstack CLI is a separate clone + bootstrap product) |
| `cross-review` | bstack P20 — Cross-Model Adversarial Review Gate |
| `dogfood` | Per-bstack-P11 reflex 7+16 — explicitly trigger the Dogfood Plan + per-stack cookbook + Dogfood Receipt sequence |
| `harness-engineering-playbook` | Implement OpenAI Harness Engineering practices in any repository — AGENTS.md, PLANS.md, deterministic smoke/test/lint harness commands, strict architecture |

## Orchestration & autonomy — `skills/orchestration/` (7)

| Skill | What it does |
|---|---|
| `autonomous` | Use when the user has agreed on a plan or selected from suggested options and wants the agent to execute the work autonomously without further instruction |
| `eve-forge` | Forge a personalized eve agent for a business end-to-end — absorb the business's artifacts, author the `agent/` dir, validate, and deploy |
| `governed-autonomy-loop` | Turn any work-queue + enforcement pipeline into a self-driving, self-healing, human-minimal autonomy loop with a control-systems safety envelope — a metacognitive governor that drives isolated arcs and never performs the irreversible act itself |
| `handoff` | Fresh-session handoff doc drafting |
| `p9` | P9 — Broomva productive-wait primitive (the wait optimizer) |
| `persist` | bstack P12 — Persistent Loop Discipline |
| `role-x` | bstack P17 — Lens-Routed Request Articulation |

## Skill & prompt tooling — `skills/tooling/` (5)

| Skill | What it does |
|---|---|
| `broomva-cli` | CLI for broomva.tech — manage prompts, skills, and context from the terminal |
| `make-spec` | Scaffold a substantive human-readable design doc (spec / plan / ADR / report / PR explainer) as native HTML using the workspace's canonical Broomva dark theme |
| `prompt-library` | Manage and retrieve reusable prompts from broomva.tech or any compatible prompt repository |
| `skillify` | Skillify-as-a-verb — distill a working session (or a pointed-at chat history) into a permanent, TESTED, registered skill at the end of a workflow |
| `skills-catalog` | Canonical reference inventory of the 75 skills across 22 category buckets, with a Remotion video showcase generator and X thread copy |

## Knowledge & memory — `skills/knowledge/` (4)

| Skill | What it does |
|---|---|
| `bookkeeping` | Universal knowledge engine — scores, promotes, and compounds knowledge across all sources into a permanent, query-able entity graph |
| `braindump` | Takes raw unstructured thoughts, voice transcript dumps, or stream-of-consciousness text and auto-files them into the right Obsidian vault folders with tags, |
| `colombia-conflict` | Knowledge engine over the Colombian Truth Commission report *Hay Futuro Si Hay Verdad* (2022) — findings, statistics, actor responsibilities, differential harms, lexicon, and the 67-recommendation non-repetición roadmap, with a kg/LLM-wiki retrieval engine and an `align` policy-vs-roadmap scorer |
| `kg` | Load relevant entities from the bstack knowledge graph (research/entities/) for a given topic |

## Research — `skills/research/` (2)

| Skill | What it does |
|---|---|
| `checkit` | Ingest-and-integrate an artifact someone points at with a terse, deliberately under-articulated directive — "check this out", "lets research this", "look into this", |
| `deep-dive-research-orchestrator` | Conduct comprehensive multi-dimensional research on any subject using coordinated AI research specialists |

## Strategy & decisions — `skills/strategy/` (5)

| Skill | What it does |
|---|---|
| `decision-log` | Captures a decision with context, alternatives considered, and rationale, then links it to the relevant project doc in the vault |
| `phronesis` | AI-native advisory practice for the Broomva ecosystem |
| `pre-mortem` | Assumes a project has already failed, works backward to identify the top causes, scores them by likelihood and impact, and outputs a mitigation plan |
| `premortem` | Run a premortem on any plan, launch, product, hire, strategy, or decision |
| `strategy-critique` | Reads a strategy doc and writes a red-team critique with gaps, risks, and missing assumptions |

## Operating cadence — `skills/cadence/` (4)

| Skill | What it does |
|---|---|
| `drift-check` | Compares stated priorities against where time and effort actually went, and produces a strategy drift report |
| `morning-briefing` | Reads open action items, this week's priorities, and recent vault updates, then produces a focused "start your day" brief |
| `stakeholder-update` | Takes one set of project facts and generates three versions: technical for engineering, business-impact for leadership, and customer-facing for success teams |
| `weekly-review` | Scans the vault for updates from the past week, surfaces what changed, and flags what needs attention |

## Publishing & growth — `skills/publishing/` (5)

| Skill | What it does |
|---|---|
| `blog-post` | Full-stack blog post production — turns a topic, idea, or brief into a complete publishing package across written, social, and multimedia surfaces |
| `content-creation` | Full-stack content creation pipeline: idea or reference to published blog post, audio narration, video, and social media distribution |
| `revenuecast` | revenuecast — turn a real-world capability into a self-demonstrating, high-throughput generative-AI revenue engine (the "Kleos" method) |
| `seo-llmeo` | SEO and LLM Engine Optimization (LLMEO) skill for BroomVA content |
| `social-intelligence` | Autonomous social engagement + knowledge extraction loop for Moltbook and X/Twitter |

## Video & multimedia — `skills/video/` (6)

| Skill | What it does |
|---|---|
| `brainrot-for-good` | Produce high-retention, dopamine-aware video content using brainrot editing techniques — fast cuts, word-by-word captions, sound design, visual velocity, pattern |
| `content-engine` | Full-stack AI content studio — orchestrates visual DNA compilation, cinematic generation (via Higgsfield CLI or MCP), browser-automated tool execution, and |
| `creative-review` | Meta-review skill for validating generated creative assets (videos, images, designs) against a reference style brief |
| `launch-video` | Produce polished product launch videos using the Liquid Glass aesthetic — dark void backgrounds, 3D perspective floating UI panels, particle effects, spring |
| `ltx-video` | Set up, configure, and run LTX-2/LTX-2.3 (Lightricks) for AI video and audio generation |
| `video-cut` | Edit raw footage into a finished cut by conversation, fully local |

## Audio & music — `skills/audio/` (2)

| Skill | What it does |
|---|---|
| `livecoding` | Algorave-grade livecoded music workflow — TidalCycles patterns (Haskell DSL driving SuperDirt over OSC) + Hydra-synth visuals (browser or VS Code Simple Browser via a |
| `omnivoice` | Local TTS, voice cloning, voice design, and video dubbing via the OmniVoice Studio MCP server (open-source ElevenLabs alternative; nothing leaves the machine, runs on |

## Design & brand — `skills/design/` (4)

| Skill | What it does |
|---|---|
| `arcan-glass` | BroomVA trademark web styling system — Arcan Glass design language for Next.js + Tailwind v4 + shadcn/ui projects |
| `brand-icons` | Brand icon and visual identity management for BroomVA projects |
| `design-engineering` | Premium design engineering skill for agentic workflows — produces high-end, distinctive UI designs using DESIGN.md as the portable contract across Pencil MCP (in-IDE |
| `tekton` | Tekton — the shared architecture-intent substrate for co-designing systems with the agent |

## Finance & payments — `skills/finance/` (4)

| Skill | What it does |
|---|---|
| `finance-substrate` | Personal finance and tax management substrate for Colombian residents |
| `haima` | Agentic finance engine for the Agent OS — x402 machine-to-machine payments, on-chain settlement, per-task revenue billing, and wallet management |
| `investment-management` | Investment management skill — portfolio construction, analysis, and execution |
| `wealth-management` | Wealth management, financial planning, and investment analytics skill |

## Compute infrastructure — `skills/compute/` (3)

| Skill | What it does |
|---|---|
| `agentic-vps` | Provision and harden a fresh Linux VPS into an autonomous-agent dev host using the capability-preserving model — the box IS the sandbox: full agent autonomy inside it |
| `colab-remote` | Orchestrate Google Colab Pro/Pro+ GPU instances as remote training backends via SSH |
| `remote-gpu` | Orchestrate a headless GPU server (NUC, cloud VM, or any SSH-accessible machine) from a local Mac or workstation |

## Model runtimes — `skills/models/` (2)

| Skill | What it does |
|---|---|
| `bitnet` | Microsoft BitNet — 1-bit LLM setup, inference, and benchmarking on CPU |
| `heretic-abliteration` | Heretic — fully automatic LLM censorship removal (abliteration) and serving the result via Ollama |

## Messaging channels — `skills/messaging/` (2)

| Skill | What it does |
|---|---|
| `claude-code-channels` | Set up Claude Code messaging channels for Telegram and Discord — bot creation, plugin installation, token configuration, access control (pairing, allowlists, guild |
| `claude-remote-sessions` | Per-channel remote sessions for Claude Code via Discord and Telegram — each channel, thread, or chat gets its own isolated Claude Code session via tmux, with |

## Robotics — `skills/robotics/` (2)

| Skill | What it does |
|---|---|
| `capx-agentic-robotics` | Agentic robotics with CaP-X — LLM-driven robot manipulation via code generation |
| `orcahand` | Full-stack skill for the ORCA Hand — 17-DOF tendon-driven robotic hand (ETH Zurich) |

## Aerospace & RF — `skills/aerospace/` (2)

| Skill | What it does |
|---|---|
| `openrocket-sim` | Headless rocket design, simulation, and optimization using OpenRocket's Java core engine |
| `sdr-satellite` | Software-defined radio (SDR) and satellite reception toolkit — what to install, what you can hear from space, and how to compose the open-source stack (SatDump, |

## Neuroscience & BCI — `skills/neuroscience/` (3)

| Skill | What it does |
|---|---|
| `tribe-v2-agent-alignment` | Use Meta's TRIBE v2 brain encoder to validate cortical alignment of AI model representations (LLaMA, V-JEPA2, Wav2Vec, or any encoder) and inform model selection in |
| `tribe-v2-bci-applied` | Applied BCI research and neuro-informed content optimization using Meta's TRIBE v2 brain encoder |
| `tribe-v2-neuroscience` | In-silico neuroscience experiments using Meta's TRIBE v2 (TRansformer for In-silico Brain Experiments) |

## Healthcare — `skills/healthcare/` (2)

| Skill | What it does |
|---|---|
| `founder-mode-oncology` | Personalized cancer treatment navigation — maximal diagnostics, parallel therapy, therapeutic development, structure-based protein design |
| `health` | Personal health knowledge graph — local-first ingest of Garmin (Apple Health, Whoop, Oura, CGM in v2+) traces into SQLite, projected to Obsidian daily-note |

## Science — `skills/science/` (1)

| Skill | What it does |
|---|---|
| `ocean-genomics` | Comprehensive bioinformatics and ocean genomics skill for eDNA metabarcoding, metagenomics, protein structure prediction, and marine biodiversity analysis |

## Commerce & procurement — `skills/commerce/` (2)

| Skill | What it does |
|---|---|
| `procurer` | Grounded procurement research for any real-world need |
| `swapit` | Stateful, local-first household toxics inventory + swap engine |

## Everyday utilities — `skills/utilities/` (2)

| Skill | What it does |
|---|---|
| `gasgo` | Find the cheapest fuel/GNCV near a Colombian location — engine over live per-station open data (SICOM GNCV via datos.gov.co) with an explicit freshness verdict and honest coordinate resolution (municipal-centroid distances shown approximate) |
| `alkosto-wait-optimizer` | Estimate optimal waiting time for Alkosto's "every 25/50 customers" promotion using either checkout-flow observations or winner announcement timestamps |

---

## Aggregates

- **Total skills**: 75
- **Total category buckets**: 22
- **Largest bucket**: Orchestration & autonomy (7)
- **Smallest buckets** (1): Science
- Taxonomy = the 22 `skills/<category>/` directory buckets. Install any skill path-independently: `npx skills add broomva/skills --skill <name>`.
