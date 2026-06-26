# Skills

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![skills.sh](https://img.shields.io/badge/skills.sh-directory-8B5CF6)](https://skills.sh/)
[![Agent Skills spec](https://img.shields.io/badge/spec-agentskills.io-blue)](https://agentskills.io/specification)
[![Monorepo layout](https://img.shields.io/badge/layout-anthropics%2Fskills-orange)](https://github.com/anthropics/skills)

A curated monorepo of [Agent Skills](https://agentskills.io/specification) — 48+ Tier-2 skills + the catalog/showcase. Compatible with Claude Code, Codex, Cursor, Gemini CLI, Goose, Copilot, and any agent that consumes the `SKILL.md` standard.

Layout follows the ecosystem-canonical [`anthropics/skills`](https://github.com/anthropics/skills) shape: **no root `SKILL.md`** (the README is the discovery surface), all skills live under `skills/<name>/SKILL.md`.

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

> **Note:** no `--full-depth` flag is needed — this monorepo has no root `SKILL.md`, so the CLI's default search descends into `skills/<name>/` automatically. (Earlier versions of this README required `--full-depth`; the [2026-05-27 restructure](https://github.com/broomva/skills/pull/11) removed the root `SKILL.md` to align with [`anthropics/skills`](https://github.com/anthropics/skills) and eliminate the footgun.)

## Repository layout

| Path | Purpose |
|---|---|
| [`skills/`](skills/) | **The monorepo.** One directory per skill, each with `SKILL.md` + optional `references/`/`scripts/`/`assets/` per the [agentskills.io spec](https://agentskills.io/specification). Includes the catalog skill at [`skills/skills-catalog/`](skills/skills-catalog/). |
| [`references/skills-inventory.md`](references/skills-inventory.md) | Full categorized inventory across all 15 domains (companion to the catalog skill) |
| [`skills-showcase/`](skills-showcase/) | Remotion video + X thread renderer for the inventory |
| [`.github/workflows/`](.github/workflows/) | CI: SKILL.md frontmatter lint (validates `name` matches parent dir + required fields present per agentskills.io spec) |
| `_shared/` | (reserved) shared utilities used by multiple Tier-2 skills |

## Tier-2 skills (vendored in this monorepo)

### Catalog & discovery

| Skill | Path | What it does |
|---|---|---|
| [`skills-catalog`](skills/skills-catalog/) | `skills/skills-catalog/SKILL.md` | The discovery surface — the agent uses this skill to browse [`references/skills-inventory.md`](references/skills-inventory.md), find skills by domain, and surface relevant tools. Install with `npx skills add broomva/skills --skill skills-catalog`. Renamed from root `skills` skill 2026-05-27 (restructure to drop root `SKILL.md`). |

### Workflow & lifecycle

| Skill | Path | What it does |
|---|---|---|
| [`handoff`](skills/handoff/) | `skills/handoff/SKILL.md` | Fresh-session handoff doc drafting — compress a substantive arc into a single resumable doc for the next agent context |
| [`make-spec`](skills/make-spec/) | `skills/make-spec/SKILL.md` | Native-HTML design-doc scaffolding (spec / plan / ADR / report / pr-explainer) using the canonical Broomva dark theme — implements P18 (Format-Follows-Audience) for Category-C artifacts |

### Content & media

> Migrated 2026-05-25 from standalone `broomva/<name>` repos (Phase 4a: blog-post + brand-icons + seo-llmeo; Phase 4b: the 6 below). All originals are deprecated with redirect-stubs (6-month window until 2026-11-25).

| Skill | Path | What it does |
|---|---|---|
| [`blog-post`](skills/blog-post/) | `skills/blog-post/SKILL.md` | Full-stack blog post production — research → angle → draft → multi-platform distribution (X, LinkedIn, Instagram, Substack); ships SKILL.md + templates/ + examples/ + `scripts/publish.sh` |
| [`brand-icons`](skills/brand-icons/) | `skills/brand-icons/SKILL.md` | Brand icon and visual identity asset generation — favicons, app icons, OG images, social avatars from brand sources |
| [`seo-llmeo`](skills/seo-llmeo/) | `skills/seo-llmeo/SKILL.md` | SEO and LLM Engine Optimization — audits, meta tags, structured data (JSON-LD), `llms.txt` generation |
| [`content-creation`](skills/content-creation/) | `skills/content-creation/SKILL.md` | Full-stack content pipeline — research → narrative → visual assets → video → social → deploy; ships SKILL.md + bstack-launch/ + open-source-stack/ example campaigns with rendered video/GIF outputs |
| [`content-engine`](skills/content-engine/) | `skills/content-engine/SKILL.md` | Full-stack AI content studio — visual DNA compiler, cinematic generation, browser autopilot, content loop. Bundles 4 sub-skills (`content-engine-autopilot`, `content-engine-cinema`, `content-engine-dna`, `content-engine-loop`) under `skills/content-engine/skills/` |
| [`launch-video`](skills/launch-video/) | `skills/launch-video/SKILL.md` | Liquid Glass product launch video — dark void aesthetic, 3D floating panels, spring animations via Remotion |
| [`ltx-video`](skills/ltx-video/) | `skills/ltx-video/SKILL.md` | LTX-2.3 video generation — setup, inference, prompting, ComfyUI integration for Lightricks 22B DiT audio-video model |
| [`creative-review`](skills/creative-review/) | `skills/creative-review/SKILL.md` | Meta creative review skill — style adherence scoring, feedback loops, self-improving creative pipeline |
| [`brainrot-for-good`](skills/brainrot-for-good/) | `skills/brainrot-for-good/SKILL.md` | High-retention video production using dopamine-aware editing for genuinely valuable content |
| [`revenuecast`](skills/revenuecast/) | `skills/revenuecast/SKILL.md` | Turn a real-world capability into a self-demonstrating gen-AI **revenue engine** ("/skillify for revenue" — the *Kleos* method). Composition skill over `content-engine`; ships the deterministic `revenuecast_check.py` gate (own-the-audience · real moat ≠ leakable prompts · compliance pillar [FTC v. Air AI / EU AI Act Art.50] · Ritual-vs-Substance) + 23 tests + self-contained `references/` (the L1 Kleos playbook, L2 agentic-dev wedge, L3 runtime spec). Install: `npx skills add broomva/skills --skill revenuecast` |

### Research & intelligence

> Migrated 2026-05-25 (Phase 4c) from standalone `broomva/<name>` repos. 3 entries renamed during migration to drop the `-skill` suffix (ecosystem norm).

| Skill | Path | What it does |
|---|---|---|
| [`deep-dive-research-orchestrator`](skills/deep-dive-research-orchestrator/) | `skills/deep-dive-research-orchestrator/SKILL.md` | Multi-dimensional research with coordinated AI specialists; 10+ source synthesis with citations. (Renamed from `broomva/deep-dive-research-skill`.) |
| [`social-intelligence`](skills/social-intelligence/) | `skills/social-intelligence/SKILL.md` | Autonomous social engagement + knowledge extraction loop for Moltbook and X — compounds with `blog-post` and `content-creation` |
| [`harness-engineering-playbook`](skills/harness-engineering-playbook/) | `skills/harness-engineering-playbook/SKILL.md` | Agent-first workflow patterns — AGENTS.md, smoke/test/lint/typecheck harness, entropy control. (Renamed from `broomva/harness-engineering-skill`.) |
| [`checkit`](skills/checkit/) | `skills/checkit/SKILL.md` | Ingest-and-integrate an artifact shared with a terse, under-articulated directive ("check this out", "lets research this", + a URL/repo/paper/file). Infers the real ask without bouncing a question back, then contextualizes → researches (verifying sources) → connects → documents → suggests ranked next steps. Composition skill; pairs with the `checkit` role/x lens in a bstack workspace. |
| [`skillify`](skills/skillify/) | `skills/skillify/SKILL.md` | Skillify-as-a-verb — distill a working session into a permanent, **tested, registered, installable** skill ("skillify it"). Composition skill (look-back → CreateSkill → tests → resolver-eval → `bstack skills audit --require-tests` → P20 → bookkeeping → publish + skills.sh install-dogfood) with one deterministic core, `scripts/skillify_check.py`, the 10-step gate that makes "a feature that doesn't pass all ten is not a skill" exit-codeable (syntax-checks scripts, AST-validates tests, `--skills-sh` install-verify). Install: `npx skills add broomva/skills --skill skillify`. |
| [`agentic-vps`](skills/agentic-vps/) | `skills/agentic-vps/SKILL.md` | Provision & harden a fresh Linux VPS into an **autonomous-agent dev host** using the *capability-preserving* model — the box IS the sandbox: full agent autonomy inside it (non-root sudo user, open egress, any toolchain), contained by **isolation** (non-root + VPN-only access + snapshot + no-long-lived-secrets), not by leashing the agent. Deterministic cores: `provision.sh` (idempotent), `staging_check.py` (lockout-safe firewall/VPN ordering), `verify.py` (fail-closed invariant gate) + 30 tests. Install: `npx skills add broomva/skills --skill agentic-vps`. |

### Finance & investment

> Migrated 2026-05-25 (Phase 4c) from standalone `broomva/<name>` repos. `haima` renamed during migration to drop `-skill` suffix; runtime crate stays at `broomva/haima`.

| Skill | Path | What it does |
|---|---|---|
| [`investment-management`](skills/investment-management/) | `skills/investment-management/SKILL.md` | Portfolio construction, factor models, backtesting, multi-platform execution (Alpaca, Coinbase, Polymarket) |
| [`wealth-management`](skills/wealth-management/) | `skills/wealth-management/SKILL.md` | Wealth planning + Monte Carlo + tax-optimized allocation + net worth forecasting |
| [`haima`](skills/haima/) | `skills/haima/SKILL.md` | Agent guide for x402 machine-to-machine payments, secp256k1 wallets, per-task billing, on-chain USDC settlement. (Renamed from `broomva/haima-skill`; runtime crate remains at `broomva/haima`.) |

### Hardware, robotics & physical systems

> Migrated 2026-05-26 (Phase 4d) from standalone `broomva/<name>` repos.

| Skill | Path | What it does |
|---|---|---|
| [`capx-agentic-robotics`](skills/capx-agentic-robotics/) | `skills/capx-agentic-robotics/SKILL.md` | CaP-X LLM-driven robot manipulation via code generation — CaP-Gym (187 tasks), CaP-Bench, CaP-Agent0, CaP-RL, sim-to-real |
| [`orcahand`](skills/orcahand/) | `skills/orcahand/SKILL.md` | Full-stack skill for the ORCA Hand — 17-DOF tendon-driven robotic hand. Plant interface, safety shields, MuJoCo simulation, RL training, teleoperation, sim-to-real, EGRI improvement. (Migrated 2026-05-26 — Phase 4f; deduplicated `broomva/orcahand` + `broomva/orcahand-skill`, both archived.) |
| [`openrocket-sim`](skills/openrocket-sim/) | `skills/openrocket-sim/SKILL.md` | Headless rocket design, simulation, and EGRI optimization using OpenRocket |
| [`sdr-satellite`](skills/sdr-satellite/) | `skills/sdr-satellite/SKILL.md` | Software-defined radio + satellite reception toolkit — what to install, what you can hear, how to compose the stack |
| [`ocean-genomics`](skills/ocean-genomics/) | `skills/ocean-genomics/SKILL.md` | Deep-ocean genomics research — eDNA metabarcoding, AlphaFold, ESMFold, Evo 2, marine biodiversity, agentic bioinformatics workflows |
| [`microgrid-agent`](skills/microgrid-agent/) | `skills/microgrid-agent/SKILL.md` | Open-source edge AI agent for autonomous renewable energy microgrid management on Raspberry Pi |
| [`bitnet`](skills/bitnet/) | `skills/bitnet/SKILL.md` | Microsoft BitNet — 1-bit LLM setup, model download, inference, and benchmarking on CPU |

### Compute & remote infrastructure

> Migrated 2026-05-26 (Phase 4d).

| Skill | Path | What it does |
|---|---|---|
| [`colab-remote`](skills/colab-remote/) | `skills/colab-remote/SKILL.md` | Colab Remote — SSH-operated GPU training on Google Colab |
| [`remote-gpu`](skills/remote-gpu/) | `skills/remote-gpu/SKILL.md` | Remote GPU orchestrator — manage headless GPU servers, submit jobs, run remote Claude Code sessions over SSH/HTTP |
| [`claude-code-channels`](skills/claude-code-channels/) | `skills/claude-code-channels/SKILL.md` | Telegram + Discord messaging bots for Claude Code with per-channel access control |
| [`claude-remote-sessions`](skills/claude-remote-sessions/) | `skills/claude-remote-sessions/SKILL.md` | Per-channel Discord + Telegram sessions for Claude Code — isolated tmux sessions, auto-discovery watchdog, thread-context injection, launchd persistence |

### Audio, voice, media tooling

> Migrated 2026-05-26 (Phase 4d). 2 entries renamed during migration (drop `-skill` suffix).

| Skill | Path | What it does |
|---|---|---|
| [`omnivoice`](skills/omnivoice/) | `skills/omnivoice/SKILL.md` | OmniVoice Studio agent skill — local TTS, voice cloning, voice design, video dubbing in 646 languages. (Renamed from `broomva/omnivoice-skill`.) |
| [`livecoding`](skills/livecoding/) | `skills/livecoding/SKILL.md` | Algorave-grade livecoded music workflow — TidalCycles patterns + Hydra visuals |

### Advisory, consulting & decision tooling

> Migrated 2026-05-26 (Phase 4d). 1 entry renamed during migration (drop `-skill` suffix).

| Skill | Path | What it does |
|---|---|---|
| [`phronesis`](skills/phronesis/) | `skills/phronesis/SKILL.md` | AI-native advisory practice — top-firm consulting methodology (Three Horizons, MIT CISR, JTBD, RICE, QuantumBlack ML, Wardley) as runnable typed primitives |
| [`procurer`](skills/procurer/) | `skills/procurer/SKILL.md` | Grounded procurement research — turn any real-world need into a decision-shaped report with cited alternatives, price bands, recommendation |
| [`alkosto-wait-optimizer`](skills/alkosto-wait-optimizer/) | `skills/alkosto-wait-optimizer/SKILL.md` | Probability-based decision tool for optimal waiting times on Alkosto promotions — Bayesian estimation with uncertainty. (Renamed from `broomva/alkosto-wait-optimizer-skill`.) |

### Health & body

> Migrated 2026-05-26 (Phase 4d). Joins yesterday's `health` and `founder-mode-oncology` graduates into a unified health/body category.

| Skill | Path | What it does |
|---|---|---|
| [`health`](skills/health/) | `skills/health/SKILL.md` | Personal health knowledge graph — local-first ingest of Garmin/Apple/Whoop/Oura traces into SQLite, projected to Obsidian daily-note frontmatter (hex architecture). Graduated 2026-05-23 via standalone repo; consolidated to monorepo 2026-05-26 |
| [`founder-mode-oncology`](skills/founder-mode-oncology/) | `skills/founder-mode-oncology/SKILL.md` | Personalized cancer-treatment navigation — Sid Sijbrandij founder-mode framework with AlphaFold integration |

### Neuroscience & BCI (TRIBE v2 family)

> Migrated 2026-05-26 (Phase 4e) from standalone `broomva/<name>` repos. The 3 skills have **disjoint reference sets** — no `_shared/tribe-v2/` directory was created because there is no shared content to extract (the `_shared/` pattern is demand-driven, not speculative).

| Skill | Path | What it does |
|---|---|---|
| [`tribe-v2-agent-alignment`](skills/tribe-v2-agent-alignment/) | `skills/tribe-v2-agent-alignment/SKILL.md` | Cortical alignment benchmarking for AI encoders using Meta's TRIBE v2 — neuro-informed model selection for the Life/Arcan agent OS stack |
| [`tribe-v2-bci-applied`](skills/tribe-v2-bci-applied/) | `skills/tribe-v2-bci-applied/SKILL.md` | Applied BCI research + neuro-informed content optimization using Meta's TRIBE v2 — predict neural responses to media/UI/content |
| [`tribe-v2-neuroscience`](skills/tribe-v2-neuroscience/) | `skills/tribe-v2-neuroscience/SKILL.md` | In-silico neuroscience experiments using Meta's TRIBE v2 — predict fMRI cortical responses to video, audio & text without brain scanners |

### Strategy & decision intelligence

> Migrated 2026-05-25 from the bundled `broomva/strategy-skills` repo per the Tier-2 monorepo plan. Each sub-skill is now individually installable.

| Skill | Path | What it does |
|---|---|---|
| [`pre-mortem`](skills/pre-mortem/) | `skills/pre-mortem/SKILL.md` | Structured failure-mode analysis (4-category scoring, mitigation plan) before a project launches |
| [`premortem`](skills/premortem/) | `skills/premortem/SKILL.md` | Klein/Kahneman premortem with parallel sub-agent deep-dives + HTML report |
| [`braindump`](skills/braindump/) | `skills/braindump/SKILL.md` | Capture raw thoughts → Obsidian vault with auto-categorization and backlinks |
| [`morning-briefing`](skills/morning-briefing/) | `skills/morning-briefing/SKILL.md` | Generate a focused daily brief from vault priorities and action items |
| [`drift-check`](skills/drift-check/) | `skills/drift-check/SKILL.md` | Compare stated priorities vs actual effort (git log + vault) — strategy drift report |
| [`strategy-critique`](skills/strategy-critique/) | `skills/strategy-critique/SKILL.md` | Red-team critique of strategy documents with gaps, risks, and missing assumptions |
| [`stakeholder-update`](skills/stakeholder-update/) | `skills/stakeholder-update/SKILL.md` | Take one set of facts → generate 3 versions (technical, business, customer-facing) |
| [`decision-log`](skills/decision-log/) | `skills/decision-log/SKILL.md` | Structured decision capture with context, alternatives, rationale → vault links |
| [`weekly-review`](skills/weekly-review/) | `skills/weekly-review/SKILL.md` | Scan vault for weekly changes; surface what changed; flag what needs attention |

More Tier-2 graduations land here per the [migration plan](https://github.com/broomva/workspace/blob/main/docs/specs/2026-05-25-skills-packaging-strategy.html). See [CONTRIBUTING.md](CONTRIBUTING.md#tier-2-skill-graduation-flow) for the graduation flow.

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
