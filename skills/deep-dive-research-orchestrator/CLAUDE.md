# CLAUDE.md

## Project

Deep-Dive Research Orchestrator - a Claude Code skill for comprehensive multi-dimensional research using coordinated AI specialist agents, each following specific skill methodologies.

## Key Files

- [SKILL.md](SKILL.md) - Skill specification and frontmatter
- [AGENTS.md](AGENTS.md) - Full agent context for consumers AND builders
- [METHODOLOGY.md](METHODOLOGY.md) - Research workflow documentation
- [PLANS.md](PLANS.md) - Execution plans for multi-step work
- [.claude/agents/](.claude/agents/) - Agent definitions

## Agents

| Agent | Model | Skill Dependency | What It Actually Does |
|---|---|---|---|
| research-orchestrator | opus | all | 5-phase workflow: plan → deploy specialists → cross-reference → synthesize → verify |
| financial-researcher | sonnet | financial-deep-research | 8-phase pipeline (Scope→Package), 4-tier source credibility, anti-hallucination protocol |
| competitive-analyst | sonnet | competitor-intel | 6-category mandatory web search, zero-tolerance metrics, 3 leverage strategies |
| market-product-analyst | sonnet | app-store-optimization | ASO toolkit (6 capabilities), platform-specific limits, 8 analysis scripts |
| governance-auditor | haiku | agent-control-metalayer-skill | Quality checklist, source verification, compliance validation, 1-10 scoring |

## Commands

```bash
make smoke          # Verify agents and dependencies exist
make check          # Validate frontmatter, YAML, agent-skill alignment
make test           # Full verification (smoke + check + alignment)
make research-audit # Validate research output quality
make control-audit  # Governance and compliance check
make ci             # All of the above
```

## Rules

- Every major claim requires 3+ independent sources with URLs
- All metrics must include source attribution and dates
- Financial claims use anti-hallucination protocol: cite [N] immediately, distinguish facts vs analysis
- Competitive metrics: verified with source OR "Not publicly available" (zero-tolerance for estimation)
- Information gaps must be explicitly documented
- Never bypass quality gates without escalation
- Update AGENTS.md when workflow behavior changes
- Keep agent definitions in sync with upstream skill changes

## Dependencies

### Required (core research)
- `financial-deep-research` - 8-phase financial pipeline with source tiering
- `competitor-intel` - 6-category web research with zero-tolerance metrics
- `app-store-optimization` - ASO toolkit with platform-specific analysis

### Optional (governance and reliability)
- `agent-control-metalayer-skill` - Control policy, escalation rules, audit trails
- `harness-engineering-skill` - Harness commands, AGENTS.md standard, entropy management

## Sync Rule

When a dependency skill updates, its corresponding agent in `.claude/agents/` must also be updated. Run `make check` to verify alignment.
