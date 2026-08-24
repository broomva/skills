---
name: resume
tier: D
category: orchestration
description: |
  Restore an arc that was killed mid-flight by something external — API 529 /
  500, ENOTFOUND, ConnectionRefused, an expired login, a laptop that slept, a
  Ctrl-C. The operator restarts, types `resume`, and means *continue as though
  nothing had stopped you*: same arc, same plan, subagents and workflows that
  died put back on their feet. It does NOT mean "wrap up what you can".
  Nothing was written down in advance — the session did not intend to stop —
  so state is reconstructed forensically from the transcript, from the dead
  agents' surviving output files on disk, and from the tree.
  Distinct from `handoff` (a doc written on purpose for the next agent),
  `handback` (a message written on purpose for the human), and `persist`
  (a loop that restarts contexts by design). All three assume a VOLUNTARY
  stop that left an artifact. `resume` is the involuntary case.
  USE WHEN: "resume", "continue", "keep going", "carry on", "pick up where you
  left off", "as you were", "continue /autonomous", "resume the loop", or any
  session whose previous turn ended in an API error, a connection failure, an
  expired login, or an interrupt.
  NOT FOR: starting new work; a deliberate fresh-session pickup that has a
  handoff doc (read the doc); a finished arc the user is asking about.
---

# resume — continue the arc, do not conclude it

**`resume` is a restoration command, not a summarization command.**

## Why this skill exists

Measured over **4,002 session transcripts**, 98 `resume`-class prompts (65 of
them a bare `resume`):

| | |
|---|---|
| Preceded by an explicit API error | 44 |
| Preceded by a user interrupt | 7 |
| Had a subagent or workflow **in flight** when the session died | 26 |
| Re-spawned an agent/workflow after the resume | 18 |
| Queried the tasks that were already running | **2** |
| Produced **no tool calls at all** — text-only wrap-up | **38** |
| Acknowledged an agent death **and did not restore it** | **14** (vs 8 restored) |
| `resume` typed **again** within 40 records — the resume didn't take | **20 (20%)** |

The dominant failure is not that the agent forgets what it was doing. It is
that it treats `resume` as *"deliver what survived"*. Transcripts say it in
the agent's own words — **"three follow-on sub-agents died on the session
limit; I'll note the gap"** — while those agents' complete transcripts were
sitting on disk, unread.

Regenerate every number above with `scripts/resume_scan.py` over the corpus;
none of them are from recall.

## The mechanism you will otherwise get wrong

The intuitive detector — *a dead agent leaves a `tool_use` with no
`tool_result`* — is **false**. Measured **zero** orphans in a session that
demonstrably lost eight agents. Subagents launch **asynchronously**:

1. The spawn's `tool_result` is *always* `Async agent launched successfully`.
   It means **launched**, never **finished**. It carries `agentId:` and
   `output_file: <session-dir>/tasks/<id>.output`.
2. Completion arrives **later**, as a separate `<task-notification>` record
   carrying `<task-id>` and `<status>`.
3. **A spawn whose id never appears in a completion notification is the thing
   that died.** That is the only correct detector.
4. **The dead agent's full transcript survives on disk.** Its partial work is
   *recoverable* — re-spawning blind throws away work that already exists.
5. Those files reach **1.3 MB**. Never `cat`, `Read`, or `tail` one: the
   harness warns it will overflow your context. `resume_scan.py` digests them
   under a hard character budget instead.

## Procedure

### 1. Scan before you say anything

```bash
python3 scripts/resume_scan.py                 # current cwd's newest session
python3 scripts/resume_scan.py --json          # machine-readable
python3 scripts/resume_scan.py --session <path.jsonl>
```

It reports the termination cause, every async spawn, which ones never
reported, and a bounded digest of what each dead agent had achieved —
its last words, the files it touched, its tool tally, and the original
prompt so it can be re-spawned verbatim.

### 2. Check the surface that killed you is actually back

The scan names the cause. Clear it *before* re-spawning, or you will re-die
and the operator will type `resume` a second time — which happened in **20%**
of the measured cases.

| Cause | Clear it with |
|---|---|
| `auth_expired` | `/login`; check `gh auth status`, `railway whoami` |
| `network` | one cheap real call, not an assumption |
| `usage_limit` | note the reset time; do not fan out into the ceiling |
| `api_overload` / `api_5xx` | retry one call before spawning ten |

### 3. Re-snapshot the tree (P15) — an edit may have died half-written

A subagent that died *during* an edit leaves a partial file. `git status`,
`git diff`, the branch, ahead/behind, open PRs, CI state. Confirm the tree is
coherent before building on it.

### 4. Triage each unreported agent — three outcomes, not one

| Finding | Action |
|---|---|
| Digest shows the work **finished**, only the report was lost | Fold its result into the arc. **Do not re-spawn.** |
| Digest shows **partial** progress | Re-spawn scoped to *the remainder*, handing it what its predecessor established. |
| No digest — died early or output gone | Re-spawn from the original prompt, which the scan prints. |
| Marked `POSSIBLY STILL RUNNING` | **Check before acting.** In-process subagents die with the parent; a `run_in_background` shell is a separate process and may still be alive. Re-running a live deploy or migration is worse than waiting. |

### 5. Continue the arc

Pick up the plan where it stopped. If a `/loop`, `/autonomous`, or workflow
was driving, **restart the driver** — the arc is not over because its engine
was killed.

### 6. Report restoration, not conclusion

State what died, what was recovered from disk, what was re-spawned, and what
you are now doing. One short paragraph.

## Anti-rationalization

| Excuse | Reality |
|---|---|
| "I'll summarize where things stand." | That is the measured failure — 38/98 produced no tool calls at all. `resume` asks you to *act*, not to narrate. |
| "The agents are gone, I'll note the gap." | Their transcripts are on disk. "Noting the gap" discards recoverable work; this is the single most common loss. |
| "I'll just re-spawn everything to be safe." | Two of three outcomes are *not* re-spawn. Blind re-spawning wastes the finished work and can double-execute a live background process. |
| "The user typed one word, so they want something small." | They typed one word because they expect the arc to be intact. Scope is the arc, not the word. |
| "CI was green when it died, so it's done." | The session died; the last thing you *observed* is not the last thing that *happened*. Re-check. |
| "It's cleaner to start the arc over." | Restoration preserves committed work, open PRs, and ticket state. Restarting silently discards them. |

## Composition

- **P15 Snapshot** — step 3 is the standard snapshot, not a lighter version.
- **P9 Wait** — a watcher killed with the session is not watching; restart it.
- **P5 Fanout** — re-spawned agents follow the same worktree isolation rules.
- **`handoff`** — if the arc genuinely cannot continue, *then* write a handoff.
- **`handback`** — if the block needs a human decision, `resume` ends in a
  handback ask, never in a silent stop.

## Validation

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q
```

31 unit tests covering session location (including the worktree fallback where
the mangled path does not exist), async-spawn parsing, spawn↔completion
matching by both agent id and tool-use id, termination classification in both
polarities, and the digest's hard bound.

Two false-positive classes are pinned by regression tests, both measured
rather than imagined: a tool result **echoing** error text, and prose
**discussing** past failures. Detection is anchored on how the harness
*renders* a failure, not on the presence of an error word.
