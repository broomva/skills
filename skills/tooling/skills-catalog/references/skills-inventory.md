# Skills Inventory

> 95 skills across 23 category buckets, mirroring the `skills/<category>/` directory layout. Regenerated from the README discovery surface (canonical). Last updated: 2026-08-23.

## Governance & control — `skills/governance/` (8)

| Skill | What it does |
|---|---|
| `agentic-control-kernel` | Unifying control-systems metalayer for LLM-as-controller agent development |
| `architecture-design-principles` | Distilled architecture & design principles for building self-service developer platforms, control-plane / data-plane separation, and edge-centralized cross-cutting |
| `bstack` | bstack primer — the agent-readable contract for the Broomva Stack's twenty automation primitives (P1–P20) that turn an agent-driven workspace into a self-operating system (the primer skill; the bstack CLI is a separate clone + bootstrap product) |
| `cross-review` | bstack P20 — Cross-Model Adversarial Review Gate |
| `dogfood` | Per-bstack-P11 reflex 7+16 — explicitly trigger the Dogfood Plan + per-stack cookbook + Dogfood Receipt sequence |
| `harness-engineering-playbook` | Implement OpenAI Harness Engineering practices in any repository — AGENTS.md, PLANS.md, deterministic smoke/test/lint harness commands, strict architecture |
| `keel` | Measures whether a codebase's verification is grounded in independent, real-world signals rather than circular self-checks |
| `unhobble` | Audit and rightsize a context surface against machine-enforced mechanisms, duplication, contradiction, and token-budget pressure |

## Orchestration & autonomy — `skills/orchestration/` (8)

| Skill | What it does |
|---|---|
| `autonomous` | Use when the user has agreed on a plan or selected from suggested options and wants the agent to execute the work autonomously without further instruction |
| `eve-forge` | Forge a personalized eve agent for a business end-to-end — absorb the business's artifacts, author the `agent/` dir, validate, and deploy |
| `governed-autonomy-loop` | Turn any work-queue + enforcement pipeline into a self-driving, self-healing, human-minimal autonomy loop with a control-systems safety envelope — a metacognitive governor that drives isolated arcs and never performs the irreversible act itself |
| `handback` | Terminal-message contract for an autonomous arc that has run out of agent-executable work and genuinely needs a human — a work order of imperative asks, each carrying a default so silence is never fatal |
| `handoff` | Fresh-session handoff doc drafting |
| `p9` | Something is running and you are stuck waiting on it — CI checks on a pushed PR, a deploy going out, a build, a slow migration or reindex |
| `persist` | bstack P12 — Persistent Loop Discipline |
| `role-x` | bstack P17 — Lens-Routed Request Articulation |

## Skill & prompt tooling — `skills/tooling/` (9)

| Skill | What it does |
|---|---|
| `audit-harness-usage` | Audit Codex, Claude, Gemini, and Cursor token/cost traces plus Antigravity quotas; emit JSON/CSV/text or a self-contained HTML insights dashboard—no CodexBar runtime dependency |
| `broomva-cli` | CLI for broomva.tech — manage prompts, skills, and context from the terminal |
| `disambiguate` | Rewrite a requirement so it can only be read one way, with a deterministic ambiguity checker for the mechanical layer |
| `make-spec` | Scaffold a substantive human-readable design doc (spec / plan / ADR / report / PR explainer) as native HTML using the workspace's canonical Broomva dark theme |
| `prompt-library` | Manage and retrieve reusable prompts from broomva.tech or any compatible prompt repository |
| `prove-the-negative` | Verify a claim whose evidence is an ABSENCE — pairs every denial with a positive control that must succeed, because "everything is denied" and "nothing ran at all" are the same observation; returns INVALID rather than PASS when the controls did not fire |
| `attempt-audit` | Find absence-assertions that carry no attempt-record — code returning the same empty value whether the work ran and found nothing or was skipped entirely |
| `skillify` | Skillify-as-a-verb — distill a working session (or a pointed-at chat history) into a permanent, TESTED, registered skill at the end of a workflow |
| `skills-catalog` | Canonical reference inventory of the 95 skills across 23 category buckets, with a Remotion video showcase generator and X thread copy |

## Knowledge & memory — `skills/knowledge/` (8)

| Skill | What it does |
|---|---|
| `bookkeeping` | Universal knowledge engine — scores, promotes, and compounds knowledge across all sources into a permanent, query-able entity graph |
| `braindump` | Takes raw unstructured thoughts, voice transcript dumps, or stream-of-consciousness text and auto-files them into the right Obsidian vault folders with tags, |
| `ccr` | Reversible payload compression — shrink any blob before it enters context, while caching the original locally for byte-exact `retrieve(handle)` on demand; the payload-axis counterpart to `kg`'s retrieval axis |
| `colombia-conflict` | Knowledge engine over the Colombian Truth Commission report *Hay Futuro Si Hay Verdad* (2022) — findings, statistics, actor responsibilities, differential harms, lexicon, and the 67-recommendation non-repetición roadmap, with a kg/LLM-wiki retrieval engine and an `align` policy-vs-roadmap scorer |
| `comprehend` | Agent→human teach-to-mastery loop — stage-gated, active-recall driven, goal-bounded; the session does not end until your understanding is verified |
| `goodies` | Ingest, contextualize, and index curated resources into a public GitHub Pages vault with dynamic taxonomy and Knowledge Graph integration |
| `kg` | Load relevant entities from the bstack knowledge graph (research/entities/) for a given topic |
| `what` | Explain the *concepts* a session used, at the operator's register — ranked by what blocks understanding, anchored to where each term appeared, grounded in the knowledge graph; degrades to a re-pitch when the slice is short |

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

## Publishing & growth — `skills/publishing/` (7)

| Skill | What it does |
|---|---|
| `blog-post` | Full-stack blog post production — turns a topic, idea, or brief into a complete publishing package across written, social, and multimedia surfaces |
| `citable` | Make authored content survive both selection surfaces — human engagement and LLM retrieval for citation — with a linter encoding measured effect sizes |
| `content-creation` | Full-stack content creation pipeline: idea or reference to published blog post, audio narration, video, and social media distribution |
| `format-first` | Decide what SHAPE of content to make; refuses platform folklore with a linter encoding six claims traced to primary sources |
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

## Audio & music — `skills/audio/` (3)

| Skill | What it does |
|---|---|
| `livecoding` | Algorave-grade livecoded music workflow — TidalCycles patterns (Haskell DSL driving SuperDirt over OSC) + Hydra-synth visuals (browser or VS Code Simple Browser via a |
| `omnivoice` | Local TTS, voice cloning, voice design, and video dubbing via the OmniVoice Studio MCP server (open-source ElevenLabs alternative; nothing leaves the machine, runs on |
| `talkback` | Speak an explanation out loud while working in any project — tiered text-to-speech with a pluggable backend (ElevenLabs by default and quota-guarded, macOS `say` via `--fast` for free instant local… |

## Design & brand — `skills/design/` (7)

| Skill | What it does |
|---|---|
| `arcan-glass` | BroomVA trademark web styling system — Arcan Glass design language for Next.js + Tailwind v4 + shadcn/ui projects |
| `brand-icons` | Brand icon and visual identity management for BroomVA projects |
| `broomva-design` | Applies Broomva's platform-neutral blue-axis foundation across digital products, with general web primitives and an optional agentic-work extension |
| `design-distill` | Distill a visual style from reference sites/products into a validated dual-mode design system and a ready-to-run Claude Design handoff — a composition skill, not a reimplementation |
| `design-engineering` | Premium design engineering skill for agentic workflows — produces high-end, distinctive UI designs using DESIGN.md as the portable contract across Pencil MCP (in-IDE |
| `tekton` | Tekton — the shared architecture-intent substrate for co-designing systems with the agent |
| `unslop` | Remove the vibecoded / AI-slop look from any frontend codebase at the root, autonomously — full-repo survey with root-cause attribution, substance tells, and a deterministic crafted-floor gate; composes the impeccable detector |

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

## Simulation — `skills/simulation/` (2)

| Skill | What it does |
|---|---|
| `data-provider` | Turn a question about the world into a table Parallax can accept, with every field typed observed or simulated at the moment it is written. Records findings against the artifact they were read from, hashes it, judges each column by rule, and emits the exact `parallax propose` invocation |
| `parallax` | Drive Parallax — the ontology simulation layer: propose an ontology from a context, a human accepts it before anything runs, then roll it forward with every answer typed observed or simulated. Ships the runtime it drives at `runtime/`, so installing the skill installs the layer |

## Commerce & procurement — `skills/commerce/` (3)

| Skill | What it does |
|---|---|
| `d1-cli` | Shop Tiendas D1 (Colombia) from the command line — search, resolve your nearest store, price a basket against its real stock, quote delivery; builds carts but never pays |
| `procurer` | Grounded procurement research for any real-world need |
| `swapit` | Stateful, local-first household toxics inventory + swap engine |

## Everyday utilities — `skills/utilities/` (2)

| Skill | What it does |
|---|---|
| `gasgo` | Find the cheapest fuel/GNCV near a Colombian location — engine over live per-station open data (SICOM GNCV via datos.gov.co) with an explicit freshness verdict and honest coordinate resolution (municipal-centroid distances shown approximate) |
| `alkosto-wait-optimizer` | Estimate optimal waiting time for Alkosto's "every 25/50 customers" promotion using either checkout-flow observations or winner announcement timestamps |

---

## Aggregates

- **Total skills**: 95
- **Total category buckets**: 23
- **Largest bucket**: Skill & prompt tooling (9)
- **Smallest buckets** (1): Science
- Taxonomy = the 23 `skills/<category>/` directory buckets. Install any skill path-independently: `npx skills add broomva/skills --skill <name>`.
