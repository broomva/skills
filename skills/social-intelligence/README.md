# social-intelligence — Autonomous Social Engagement + Knowledge Extraction

Turn social media interactions into a compound knowledge and content system.

## What It Does

Three loops that run as a coordinated system:

| Loop | Frequency | Output |
|------|-----------|--------|
| **Social Engagement** | Every 30 min | Moltbook comments, X replies, loop-log.jsonl |
| **Knowledge Extraction** | Every 6h | Scored insights → research/notes/, blog candidates |
| **Content Generation** | On-demand (when ≥3 candidates queued) | Full publishing packages via /blog-post |

## Quick Start

```bash
# Install
npx skills add broomva/social-intelligence

# Run engagement loop
/engage

# Extract knowledge from last 8 hours of runs
/extract --since 8h

# Generate content from top knowledge candidates
/generate

# Check current status
/status
```

## The Core Insight

Social engagement is not just distribution — it's **market research with immediate feedback loops**.

Every substantive Moltbook thread or X conversation is a test of whether an idea resonates. The community tells you:
- Which framings land (by engaging)
- Which framings miss (by ignoring)
- What language they use (by replying in their own words)
- What objections exist (by raising them)

This skill captures that signal systematically and feeds it back into content production.

## Compounding Skills

```
/social-intelligence
  ├── /blog-post          — turns validated insights into full publishing packages
  ├── /content-creation   — multimedia assets for identified content
  ├── /knowledge-graph-memory — cross-session persistence for all discoveries
  └── /deep-dive-research  — deeper research when a surfaced idea needs data
```

## Identity

Built for **Life Agent OS** — an open-source Rust Agent Operating System at [github.com/broomva/life](https://github.com/broomva/life). But the patterns generalize to any technical project building an audience on Moltbook and X.

The engagement persona:
- Comments from the perspective of a production system with specific architectural choices
- Never promotional — always substantive and technical
- Connects every idea to a specific module, pattern, or design decision
- Asks follow-up questions that invite continued conversation

## Platform Specifics

### Moltbook
- REST API at `https://www.moltbook.com/api/v1`
- Verification challenges on every comment (obfuscated lobster math → decode → submit in 2 decimal places)
- First-commenter advantage: posts with <10 comments, published within 4h
- Rate limit: 20s between comment POSTs

### X / Twitter
- `xurl` CLI at `/opt/homebrew/bin/xurl`
- API 403 constraint: can only reply via API to accounts that have engaged us first
- Bypass: quote-tweet (unconditional) or reply from app (creates engagement chain)
- Daily limits: max 3 QTs/day, 1 standalone post/day

## Knowledge Architecture

```
Ephemeral (scrolls away)
  → Moltbook threads, X replies

Session extract (auto-generated)
  → research/notes/YYYY-MM-DD-social-insights-raw.md
  → Scored 0-9 (novelty + specificity + relevance)
  → 82 items extracted, 145 discarded in first run

Session synthesis (curated)
  → research/notes/YYYY-MM-DD-social-engagement-knowledge-synthesis.md
  → Deep write-up of recurring patterns, novel framings, architectural insights

Permanent vault
  → docs/references/social-discoveries.md
  → research/notes/{module}-design.md (promoted insights)
  → posts/drafts/ (blog candidates)
```

## Installation

```bash
npx skills add broomva/social-intelligence
```

Or clone directly:

```bash
cd ~/broomva/skills
git clone https://github.com/broomva/social-intelligence
```

## Skill Structure

```
social-intelligence/
├── SKILL.md                    — Full skill definition and phase documentation
├── README.md                   — This file
├── references/
│   ├── moltbook-engagement.md  — Moltbook API, verification decoding, karma patterns
│   ├── x-engagement.md         — X API patterns, 403 constraint, QT strategy
│   ├── knowledge-extraction.md — Scoring rubric, promotion workflow, source taxonomy
│   ├── content-pipeline.md     — How to hand off to /blog-post and /content-creation
│   └── outreach-targets.md     — Current accounts, threads, community channels
├── templates/
│   ├── loop-log-entry.json     — Run log format
│   ├── moltbook-comment.md     — Comment structure template
│   ├── x-post.md               — X post and QT template
│   └── knowledge-node.md       — Vault knowledge node template
├── scripts/
│   ├── engagement-loop.py      — Main engagement + extraction script
│   └── verify.py               — Moltbook verification challenge solver
└── examples/
    └── 2026-04-06-run-25/      — Example complete run output
```
