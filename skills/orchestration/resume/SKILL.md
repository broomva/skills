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

Regenerate every figure below with `scripts/resume_corpus_stats.py`. Nothing
here is from recall, and the generator ships with the skill — a number stated
in prose and a number produced by a sweep render identically, so the claim is
worth exactly as much as the script that reproduces it.

Over **3,869 transcripts**, **91** resume-class turns (**59** of them a bare
`resume`, across 10 distinct surface forms):

| | | |
|---|---|---|
| Preceded by an API error | 48 | 53% |
| Preceded by a user interrupt | 7 | 8% |
| Had a worker **in flight** when the session died | 22 | 24% |
| Re-spawned a worker afterwards | 15 | 16% |
| **Queried the workers that were already running** | **2** | **2%** |
| **Produced no tool calls at all** — a text-only wrap-up | **37** | **41%** |
| Acknowledged a death **and did not restore it** | 9 | vs 6 restored |
| `resume` typed **again** — the first one didn't take | 16 | 18% |

The dominant failure is not that the agent forgets what it was doing. It is
that it treats `resume` as *"deliver what survived"*. Transcripts say it in the
agent's own words — **"three follow-on sub-agents died on the session limit;
I'll note the gap"** — while those agents' complete transcripts sat on disk,
unread.

## The mechanisms you will otherwise get wrong

**1. A dead agent leaves no orphaned tool call.** The intuitive detector —
a `tool_use` with no `tool_result` — finds nothing. Measured **zero** orphans
in a session that demonstrably lost eight agents. Workers launch
**asynchronously**: the spawn's result is *always* `Async agent launched
successfully` (it attests to *launching*), and completion arrives later as a
separate `<task-notification>`. **A spawn whose id never appears in a
completion is what died.**

**2. Completion notices arrive in more than one record shape.** They appear on
`queue-operation`, `attachment` and `user` records — in one production session
23 / 7 / 7. Reading only the `user` shape missed **37%** of completions and
reported finished agents as dead.

**3. The obvious output path is the one the crash deletes.** The launch
receipt's `output_file:` points into `/private/tmp/...`, wiped by exactly the
reboot this skill is about — **92%** of unreported spawns had no file there.
The harness also writes a durable copy at
`<project>/<session-id>/subagents/agent-<id>.jsonl`. The scan prefers it.

**4. Only a background shell can outlive the parent.** `Agent`/`Task`/
`Workflow` run in-process and die with it; a `run_in_background` shell is a
separate OS process. Liveness is therefore a property of the **spawn kind**
first and the file's mtime second.

**5. Recovered transcripts reach ~1.5 MB** and contain credentials.
See *Privacy* below. Never `cat`, `Read` or `tail` one.

## Procedure

### 1. Scan before you say anything

The script lives beside this file, not in your working directory:

```bash
SKILL_DIR=~/.claude/skills/resume        # or the base directory printed above

python3 "$SKILL_DIR/scripts/resume_scan.py"                    # newest session for cwd
python3 "$SKILL_DIR/scripts/resume_scan.py" --previous         # the session BEFORE it
python3 "$SKILL_DIR/scripts/resume_scan.py" --list-sessions    # choose explicitly
python3 "$SKILL_DIR/scripts/resume_scan.py" --session <path.jsonl>
```

**If the crash dropped you into a FRESH session, the newest transcript is the
one you are sitting in — not the one that died.** The scan says so when it
sees no workers and other sessions exist; `--previous` is then the answer.
This was a real defect: auto-selection returned the live, near-empty session
and reported "nothing died mid-flight".

### 2. Check the surface that killed you is actually back

Clear it *before* re-spawning, or you will re-die and the operator will type
`resume` again — which happened in **18%** of measured cases.

| Cause | Clear it with |
|---|---|
| `auth_expired` | `/login`; check `gh auth status`, `railway whoami` |
| `usage_limit` | note the reset time; do not fan out into the ceiling |
| `rate_limited` | back off; one call before many |
| `api_overload` / `api_5xx` | retry one call before spawning ten |
| `network` | one cheap real call, not an assumption |
| `user_interrupt` | ask what the operator wanted changed before continuing |
| `api_error_unclassified` | an error the scan does not recognise — **read the evidence line**; do not treat it as clean |
| `clean_or_unknown` | no termination evidence in the window; the session may have ended normally, or the record may be gone |

### 3. Re-snapshot the tree (P15) — an edit may have died half-written

A worker that died *during* an edit leaves a partial file. `git status`,
`git diff`, branch, ahead/behind, open PRs, CI. Confirm the tree is coherent
before building on it.

### 4. Triage each worker — three outcomes, not one

| Finding | Action |
|---|---|
| Digest shows the work **finished**, only the report was lost | Fold it into the arc. **Do not re-spawn.** |
| Digest shows **partial** progress | Re-spawn scoped to *the remainder*, handing over what its predecessor established. |
| No digest — died early, or nothing survived | Re-spawn from the original prompt, which the scan prints complete. |
| **REPORTED FAILURE** | It came back, and came back broken. Read its summary; a failed worker is not a finished one. |
| `liveness: possibly-live` | **A separate process that wrote after the session died.** Check before re-running: re-running a live deploy or migration is worse than waiting. |
| `liveness: unknown-no-output-file` | Liveness cannot be determined. Verify before re-running anything with side effects. |

### 5. Continue the arc

Pick up where the plan stopped. If a `/loop`, `/autonomous` or workflow was
driving, **restart the driver** — the arc is not over because its engine died.

### 6. Report restoration, not conclusion

What died, what was recovered from disk, what was re-spawned, what you are
doing now. One short paragraph.

## Privacy — read before pasting any of this anywhere

Recovered text is other sessions' output. On the machine this was written on,
**22 of 671** surviving worker files contained secret-shaped strings
(`sk-ant-`, `ghp_`, `github_pat_`, `AKIA…`, `xoxb-`).

The scan masks those patterns in everything it prints and names what it
masked. **This is a blunt instrument and does not make the output safe to
publish**: it matches shapes, not secrets, so an unusual credential format,
customer data, or private source passes straight through. Treat scan output as
sensitive, keep it in the session, and do not paste it into a PR, an issue, or
a chat channel without reading it first.

## Anti-rationalization

| Excuse | Reality |
|---|---|
| "I'll summarize where things stand." | That is the measured failure — 41% produced no tool calls at all. `resume` asks you to *act*. |
| "The workers are gone, I'll note the gap." | Their transcripts are on disk, and the durable copy survives the crash. "Noting the gap" discards recoverable work. |
| "I'll re-spawn everything to be safe." | Two of three outcomes are *not* re-spawn, and a live background process can be re-run into a double deploy. |
| "The scan says nothing died." | Check WHICH session it read. If you are in a fresh one, use `--previous`. |
| "It reported, so it's fine." | A worker can report **failed** or **killed**. Reported ≠ succeeded. |
| "The user typed one word, so they want something small." | They typed one word because they expect the arc intact. Scope is the arc. |
| "CI was green when it died, so it's done." | The last thing you *observed* is not the last thing that *happened*. |

## Composition

- **P15 Snapshot** — step 3 is the standard snapshot, not a lighter one.
- **P9 Wait** — a watcher killed with the session is not watching; restart it.
- **P5 Fanout** — re-spawned workers follow the same worktree isolation rules.
- **`handoff`** — if the arc genuinely cannot continue, *then* write a handoff.
- **`handback`** — if the block needs a human, end in an ask, never a silent stop.

## Validation

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q
python3 scripts/resume_corpus_stats.py          # regenerates the table above
```

102 unit tests. Coverage is deliberately weighted toward the paths a green
suite hid: notification records in all three shapes, background-shell
detection, liveness in both polarities, failed/killed completions, non-dict
JSON lines (raw stdout crashed the digest on 11% of real files), truncated
tails, zero-record files, directories and FIFOs, and secret redaction.

Both false-positive classes in termination detection are pinned by regression
tests, and the signatures are copied from strings the harness actually emits —
an earlier set was written to satisfy the regex and matched almost nothing in
production.
