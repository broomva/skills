---
tags:
  - broomva
  - control-kernel
  - architecture
  - governance
type: architecture
status: active
area: consciousness
created: 2026-03-17
---

# Consciousness Stack

Persistent cross-session context for autonomous agents. Synthesizes three substrates
into a self-evolving memory architecture.

## The Problem

Each agent session starts blank. Yet the codebase carries sedimented decisions from
hundreds of prior sessions. Without cross-session memory:
- Agents repeat solved problems
- Agents contradict prior decisions
- Agents lose momentum on multi-session work
- Agents violate invisible constraints

## Solution: Structured Forgetting with Selective Recall

Everything is captured and indexed, but recall is on-demand — not overwhelming
the context window.

## The Three Substrates

### 1. Control Metalayer (Behavioral Governance)

**Source skill**: control-metalayer-loop

What it provides:
- Setpoints with explicit metrics and thresholds
- Policy gates (hard/soft) that block or warn
- Profiles (baseline → governed → autonomous)
- `.control/` directory: machine-readable policy, commands, topology, state

**Control primitive → Memory function**:
- Setpoints = "what good looks like" (persistent goals)
- Gates = "what must never happen" (crystallized lessons)
- State.json = "where we are now" (live snapshot)

### 2. Knowledge Graph (Declarative Memory)

**Source skill**: knowledge-graph-memory (Obsidian bridge)

What it provides:
- Per-session conversation docs with full reasoning chains
- Map of Content (MOC) for navigation
- YAML frontmatter taxonomy (tags, related, type, status)
- Wikilinks for cross-referencing across sessions

**Knowledge graph → Memory function**:
- Session docs = episodic memory (what happened when)
- MOC = semantic index (find relevant sessions)
- Wikilinks = associative memory (connect related decisions)
- Tags = categorical memory (group by topic/branch)

### 3. Conversation Logs (Episodic Memory)

**Source skill**: knowledge-graph-memory (conversation_history.py)

What it provides:
- Dual-source parsing (Entire event logs + Claude Code transcripts)
- Noise filtering (system messages, tool IDs, internal paths)
- Obsidian callout formatting (user quotes, assistant info, tool examples)
- Incremental generation (skip existing, merge into MOC)

## The Consciousness Stack (Ephemeral → Permanent)

| Layer | Lifetime | Location | Update trigger |
|-------|----------|----------|----------------|
| Working memory | Single session | Context window | Every message |
| Auto-memory | Cross-session | `~/.claude/.../memory/` | Learning events |
| Conversation logs | Permanent | `docs/conversations/` | Pre-push hook |
| Knowledge graph | Permanent | `docs/` | Architecture changes |
| Policy rules | Permanent | `.control/policy.yaml` | New failure modes |
| Invariants | Permanent | `CLAUDE.md` | Rarely (foundational) |

## How Lessons Graduate

```
Agent encounters failure mode → fix applied
  (working memory)
    │
    ▼
User corrects agent behavior → feedback memory saved
  (auto-memory)
    │
    ▼
Session captured with full reasoning chain
  (conversation log)
    │
    ▼
Pattern recurs across multiple sessions → documented in architecture
  (knowledge graph)
    │
    ▼
Pattern is enforceable → added as gate
  (.control/policy.yaml)
    │
    ▼
Pattern is foundational → added to invariants
  (CLAUDE.md)
```

## Agent Session Protocol

### On Session Start
1. Read `CLAUDE.md` (invariants), `AGENTS.md` (tools), `METALAYER.md` (control loop)
2. Check `PLANS.md` (active plan to continue?)
3. Check `.control/state.json` (current metrics)
4. Scan `docs/conversations/Conversations.md` for prior sessions on current branch
5. `git status` + `git log` for recent changes

### Before Making Changes
- Search conversation history: `grep -rl "keyword" docs/conversations/`
- Traverse knowledge graph via MOC and wikilinks
- Check if prior sessions already addressed the problem

### On Task Completion
1. Run `make smoke` (validate gates pass)
2. Update docs per doc-update policy
3. Pre-push hook auto-regenerates conversation history

## Integration with Control Kernel

The consciousness stack is the **memory substrate** for the control kernel:

- **Belief state** (b_t) includes not just plant observations but prior session context
- **Control directives** (θ_t) are informed by historical traces and graduated lessons
- **Evaluator** can reference historical performance from the ledger
- **Policy gates** are the crystallized form of cross-session learning

```
Consciousness Stack ──context──▶ LLM Agent ──θ_t──▶ Control Kernel ──u_t──▶ Plant
       ▲                                                    │
       └────────────────trace + lessons────────────────────┘
```
