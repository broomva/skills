# AGENTS.md

This document serves two audiences:
1. **Consuming agents** that execute research workflows using this skill
2. **Builder agents** that maintain, improve, and extend this skill

## Project Overview

- Project: `deep-dive-research-skill`
- Primary runtime(s): Claude Code agents (Explore, general-purpose)
- Main entrypoint(s): `SKILL.md`, `.claude/agents/research-orchestrator.md`
- Dependency skills: `financial-deep-research`, `competitor-intel`, `app-store-optimization`
- Governance skills: `agent-control-metalayer-skill`, `harness-engineering-skill`

---

## Agent Roster

| Agent | Model | Role | Skill Dependency | Max Turns |
|---|---|---|---|---|
| `research-orchestrator` | opus | Coordinates full workflow, deploys specialists, synthesizes | all | 50 |
| `financial-researcher` | sonnet | 8-phase financial pipeline with source tiering | financial-deep-research | 30 |
| `competitive-analyst` | sonnet | 6-category mandatory web research, zero-tolerance metrics | competitor-intel | 30 |
| `market-product-analyst` | sonnet | ASO toolkit, platform-specific analysis, 8 scripts | app-store-optimization | 30 |
| `governance-auditor` | haiku | Quality gates, source verification, compliance | agent-control-metalayer-skill | 10 |

---

## Part 1: Consuming Agent Context

### Harness Commands

| Goal | Command |
|---|---|
| Fast sanity check | `make smoke` |
| Static quality gates | `make check` |
| Full verification | `make test` |
| Research output audit | `make research-audit` |
| Governance audit | `make control-audit` |
| CI-equivalent local run | `make ci` |

### Execution Flow

```
User Research Request
  ↓
research-orchestrator (opus)
  ├── Phase 1: Parse request → scope, mode, questions
  ├── Phase 2: Deploy in parallel via Task tool:
  │     ├── financial-researcher (sonnet)
  │     │     └── 8-phase pipeline: Scope→Plan→Retrieve→Triangulate→
  │     │         Synthesize→Critique→Refine→Package
  │     │         Mode: quick(2-5min) / standard(5-10min) / deep(10-20min) / ultradeep(20-45min)
  │     │         Sources: 4-tier credibility (SEC EDGAR > Bloomberg > WSJ > CNBC)
  │     │         Searches: 8+ parallel (fundamentals, earnings, industry, competitive,
  │     │                   regulatory, analyst ratings, risk factors, news)
  │     │
  │     ├── competitive-analyst (sonnet)
  │     │     └── 6-category mandatory web research:
  │     │         1. Business Metrics (Crunchbase, LinkedIn)
  │     │         2. Traffic & SEO (Similarweb, Ahrefs, Semrush, Google Trends, BuiltWith)
  │     │         3. Technical/Product (GitHub, APIs)
  │     │         4. Advertising (Meta Ads Library)
  │     │         5. Weakness & Sentiment (G2, Capterra, Trustpilot)
  │     │         6. Signals (hiring, launches, partnerships)
  │     │         Rule: unverified metrics = "Not publicly available", NEVER estimated
  │     │
  │     └── market-product-analyst (sonnet)
  │           └── ASO toolkit (6 capabilities):
  │               Research, Metadata, Conversion, Reviews, Launch, Analytics
  │               Platform limits: Apple(30-char title, 100-char keywords)
  │                                Google(50-char title, 80-char short desc)
  │               Scripts: keyword_analyzer, metadata_optimizer, competitor_analyzer,
  │                        aso_scorer, ab_test_planner, localization_helper,
  │                        review_analyzer, launch_checklist
  │
  ├── Phase 3: Cross-reference findings, resolve contradictions
  ├── Phase 4: Synthesize → executive summary + cross-dimensional insights
  └── Phase 5: Generate reports → deploy governance-auditor for validation
        └── governance-auditor (haiku)
              └── Checklist: sources(3+/claim), URLs valid, data freshness,
                  estimates marked, gaps identified, no placeholders, formatting
```

### Key Skill Workflows (What Each Skill Actually Does)

#### financial-deep-research
- **Pipeline**: 8 phases with mode-dependent execution
- **Anti-hallucination protocol**: Every claim needs [N] citation, facts vs analysis clearly separated
- **Search decomposition**: 8+ concurrent WebSearch calls per research run
- **Source tiers**: Tier 1 (SEC, Fed) → Tier 2 (Bloomberg, Reuters) → Tier 3 (WSJ, FT) → Tier 4 (CNBC, Yahoo)
- **Output**: 2,000-50,000+ words depending on mode, with full bibliography
- **Quality gates**: 10+ sources, 3+/claim, no placeholders, no uncited financial claims

#### competitor-intel
- **Research**: 6 mandatory web search categories with specific query patterns
- **Zero-tolerance rule**: No estimated metrics. "Not publicly available" or verified with source.
- **Output structure**: Verified Metrics Table → 3 Leverage Strategies (with action steps) → 2-3 Predicted Next Moves (with confidence) → Information Gaps
- **Self-verification**: 5-section quality checklist must pass before finalizing
- **Source rules**: Primary > Secondary > News (must cite primary). No unverified social media.

#### app-store-optimization
- **Capabilities**: 6 areas (Research, Metadata, Conversion, Reviews, Launch, Analytics)
- **Platform awareness**: Enforces Apple vs Google character limits and field differences
- **Analysis scripts**: 8 Python scripts for keyword, metadata, competitor, ASO score, A/B test, localization, review, and launch analysis
- **ASO Score**: 0-100 across 4 dimensions (Metadata 0-25, Ratings 0-25, Keywords 0-25, Conversion 0-25)
- **Limitations**: Volume estimates approximate, store algorithms proprietary, does not cover paid UA

### Constraints and Guardrails

- Every major claim requires 3+ independent sources with URLs
- All metrics must include source attribution and dates
- Information gaps must be explicitly documented
- Estimates must be clearly marked as estimates ("This suggests..." not "Data shows...")
- Financial precision required: specific numbers, dates, currency always
- Zero-tolerance for fabricated citations or hallucinated metrics
- Never bypass quality gates without explicit escalation
- Update AGENTS.md and PLANS.md when workflow behavior changes

### Architecture Boundaries

| Boundary | Input | Output | Owner |
|---|---|---|---|
| Request Parsing | User prompt | Research charter (subject, scope, mode, questions) | research-orchestrator |
| Financial Research | Research charter | Financial report (revenue, valuation, risk) with bibliography | financial-researcher |
| Competitive Research | Research charter | Verified metrics, 3 strategies, 2-3 predictions, gaps | competitive-analyst |
| Market/Product Research | Research charter | Product metrics, ASO score, market sizing, sentiment | market-product-analyst |
| Synthesis | 3 agent reports | Executive summary + cross-dimensional insights | research-orchestrator |
| Quality Audit | Final reports | Pass/fail checklist, quality score 1-10, issues | governance-auditor |

### Observability

| Event | When | Fields |
|---|---|---|
| `research.start` | Research initiated | subject, scope, mode, focus_areas |
| `research.agent.deploy` | Specialist launched | agent_name, skill_used, mode |
| `research.agent.complete` | Specialist finished | agent_name, source_count, word_count, source_tier_distribution |
| `research.cross_reference` | Contradiction found | agents_involved, metric, values, resolution |
| `research.synthesis.start` | Synthesis begins | agent_count, total_sources, contradiction_count |
| `research.audit.result` | Governance audit done | pass_fail, quality_score, issues_by_severity |
| `research.complete` | All reports delivered | total_words, total_sources, total_files, confidence_level |

### Control Policy

**Gate sequence:** smoke → check → test → research-audit → control-audit

**Retry budget:**
- Per-agent research: 2 retries before escalation
- Source verification: 3 retries per source
- Full workflow: 1 retry before human escalation

**Escalation conditions:**
- Agent fails after retry budget exhausted
- Source count below minimum threshold (3 per claim)
- Contradictory data across agents without resolution
- Quality score below 7/10 on governance audit
- Financial data could not be verified from any Tier 1-2 source

---

## Part 2: Builder Agent Context

This section is for agents that maintain, improve, and extend this skill.

### Repository Structure

```
deep-dive-research-skill/
├── SKILL.md                    # Skill specification (frontmatter + content)
├── AGENTS.md                   # This file (agent ops + builder guide)
├── CLAUDE.md                   # Quick reference for agents working in this repo
├── PLANS.md                    # Execution plans for multi-step changes
├── Makefile                    # Harness commands (smoke/check/test/audit/ci)
├── README.md                   # User-facing documentation
├── METHODOLOGY.md              # Research workflow documentation
├── INSTALLATION.md             # Dependency installation guide
├── CONTRIBUTING.md             # Contribution guidelines
├── skills.lock                 # Dependency lock file
├── package.json                # NPM metadata
├── LICENSE                     # MIT License
├── .gitignore                  # Git ignore rules
├── .claude/
│   └── agents/                 # Agent definitions (YAML frontmatter + markdown)
│       ├── research-orchestrator.md
│       ├── financial-researcher.md
│       ├── competitive-analyst.md
│       ├── market-product-analyst.md
│       └── governance-auditor.md
└── examples/
    └── RESEARCH_REQUESTS.md    # Sample research scenarios
```

### Dependency Map

```
deep-dive-research-skill (this skill)
├── [required] financial-deep-research (eng0ai/eng0-template-skills)
│     └── Provides: 8-phase pipeline, source tiering, anti-hallucination
├── [required] competitor-intel (ognjengt/founder-skills)
│     └── Provides: 6-category web research, zero-tolerance metrics, leverage strategies
├── [required] app-store-optimization (sickn33/antigravity-awesome-skills)
│     └── Provides: ASO toolkit, platform requirements, 8 analysis scripts
├── [optional] agent-control-metalayer-skill (broomva/agent-control-metalayer-skill)
│     └── Provides: governance framework, control policy, escalation rules, audit trails
└── [optional] harness-engineering-skill (broomva/harness-engineering-skill)
      └── Provides: harness commands, AGENTS.md standard, deterministic workflows, entropy management
```

### Keeping Agents in Sync with Skills

When a dependency skill updates, the corresponding agent definition must be updated:

| If this skill updates... | Update this agent... | Check for... |
|---|---|---|
| financial-deep-research | `.claude/agents/financial-researcher.md` | New phases, changed source tiers, updated quality gates |
| competitor-intel | `.claude/agents/competitive-analyst.md` | New search categories, changed output format, new query patterns |
| app-store-optimization | `.claude/agents/market-product-analyst.md` | New scripts, changed platform limits, new capabilities |
| agent-control-metalayer-skill | `.claude/agents/governance-auditor.md` | New control primitives, changed escalation rules |
| Any agent change | `AGENTS.md` Part 1 | Execution flow, skill workflows, boundaries |

**Sync verification command:** `make check` validates agent-skill alignment.

### Making Changes

1. For tasks > 30 minutes, update `PLANS.md` before coding
2. Run `make smoke` after structural changes (new/removed files)
3. Run `make check` after modifying agent definitions or SKILL.md frontmatter
4. Run `make test` after modifying agent-skill alignment
5. Run `make ci` before committing
6. Update this file (AGENTS.md) when workflow behavior changes
7. Update CLAUDE.md when agent roster or commands change

### Quality Standards for Contributions

- Agent definitions must reference specific workflows from their skill dependency
- Generic instructions ("research the topic") are insufficient; include the skill's actual methodology
- Every agent must have: name, description, tools, model, maxTurns, skills in frontmatter
- SKILL.md frontmatter must list all dependencies (required and optional)
- skills.lock must match SKILL.md dependencies
- Makefile checks must cover any new agents or dependencies
- README.md must reflect current agent roster and dependency table

### Entropy Management

- Remove stale research templates and outdated examples
- Keep agent definitions in sync with upstream skill changes
- Run `make ci` periodically to catch drift
- If a dependency skill is deprecated, update agent + skills.lock + INSTALLATION.md
- Keep PLANS.md clean: archive completed plans, remove stale ones

### Versioning Contract

- Patch (1.1.x): Fix agent definitions, update documentation, fix Makefile
- Minor (1.x.0): Add new agents, add new dependencies, change execution flow
- Major (x.0.0): Breaking changes to output format, remove agents, restructure repo

---

## Execution Plans

- For tasks > 30 minutes, update `PLANS.md` before coding.
- Track scope, constraints, milestones, and verification steps.
- Update status checkpoints during execution and after major decisions.
