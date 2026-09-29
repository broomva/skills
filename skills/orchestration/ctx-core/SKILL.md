---
name: ctx-core
tier: D
primitive: null
category: orchestration
version: 0.1.0
description: |
  The shared context core, phase 1: a read-only shared board for every Claude
  Code session in a workspace scope. Hooks publish each session's start, its
  ARC-STATUS line at every Stop, and its death on StopFailure to one
  append-only log per scope. A SessionStart hook injects a short factual brief
  of the board rows for the session's branch and cwd, including other live
  sessions on the same branch. Sessions in different worktrees therefore see
  each other without anyone reading a transcript. `ctx board` shows the board,
  `ctx doctor` checks the store and the hooks, and `ctx doctor --unscoped`
  lists repos that have sessions but no scope. Coordination only; not a
  security boundary. USE WHEN setting up or checking the shared board, asking
  "which sessions are on this branch", "what is every session doing", "is
  anyone else working here", reading or debugging the ctx store, registering
  the ctx hooks, or adding a repo to a scope. NOT FOR messaging a session or
  waking an idle one (phase 2, not built), enforcing what a session may do
  (phase 3, and no local hook is a boundary), or waiting on CI (use p9).
when_to_use: |
  Triggers on "ctx board", "ctx doctor", "shared board", "shared context core",
  "who else is on this branch", "which sessions are live", "register the ctx
  hooks", "add a scope", "unscoped repos", "board.json", "events.jsonl".
---

# ctx-core: the shared board (phase 1)

In the 09-26 → 09-29 run, coordination state lived in the coordinator's
context window. Compaction kept dropping it, and no worker session could see
another. Phase 1 of the shared context core
([design](https://github.com/broomva/workspace/pull/825),
`docs/specs/2026-09-29-shared-context-core.html`) puts the minimum of that
state on disk: which sessions exist in a scope, where they are (cwd, branch),
their last ARC-STATUS line, and whether they died. Every session gets the
relevant slice of it at start.

It is read and publish only. There is no mailbox, no role gate and no wake-up.

## What it does

| Piece | Does |
|---|---|
| `scripts/ctx.py` | The single writer and reader: scope resolution, redaction, the locked append, the board fold, the CLI |
| `scripts/ctx_hook.py` | The hook entry for `session-start`, `stop` and `stop-failure`. It owns the deadline, the output guard and exit 0 |
| `~/.config/ctx/scopes.yaml` | Scope id → repos. The owner writes it. The key is the realpath of `git rev-parse --git-common-dir`, so every worktree of a repo lands in its main checkout's scope |
| `~/.local/state/ctx/<scope>/events.jsonl` | Append-only, one JSON object per line. Schema: [`references/event-schema.md`](references/event-schema.md) |
| `~/.local/state/ctx/<scope>/board.json` | The log folded. Derived, never edited by hand |

| Hook | Publishes | Prints |
|---|---|---|
| SessionStart | `session.start`: source, model, `FLEET_ROLE` if set, `PASEO_AGENT_ID` if set | A brief of at most 4,000 chars in `hookSpecificOutput.additionalContext`, or nothing when no other session is relevant |
| Stop | `session.stop` plus the last `ARC-STATUS:` line of `last_assistant_message`. Every stop is also a heartbeat | Nothing |
| StopFailure | `session.died` with `error_type`. Limit and API-error deaths never fire Stop | Nothing (the output is ignored) |

Invariants, each pinned by a test:

- **A repo with no scope is a silent no-op.** Every hook and command exits 0
  with no output. The same holds for a cwd outside git, a missing or malformed
  config, and a repo listed in two scopes (ambiguous means none).
- **Scopes never cross.** The `sri` and `broomva` stores are separate
  directories. A test audits every `open()` an sri session makes and finds none
  under broomva's store.
- **Nothing secret-shaped is written.** A redaction pass runs over every string
  before the write, and before any clipping:
  - tokens (GitHub, Anthropic, OpenAI, Stripe, Slack, AWS, Google, JWT, npm,
    GitLab, Linear);
  - `Authorization` and `Cookie` headers and `Bearer` values;
  - `key=value` / `key: value` pairs whose key names a secret;
  - URL credentials and credential query parameters;
  - private-key blocks.

  Any path under `crm/`, or with a secret-shaped segment (`.env*`, `.ssh`,
  `.aws`, `*.pem`, `id_*`, `credentials`, `secrets`), becomes
  `[excluded-path]`. A session whose cwd is such a path writes nothing.
- **A hook never blocks a session:**
  - The lock is `fcntl.flock(LOCK_EX | LOCK_NB)`, retried for at most 150 ms,
    then the append is skipped.
  - The hook has a hard self-deadline of 120 ms inside the interpreter, and 200
    ms of wall time measured from outside.
  - A git that hangs is killed.
  - Every hook exits 0. SIGTERM also exits 0.
  - Tracebacks and stray prints go to `/dev/null`.
- **Injection fails open.** A failed, slow or broken hook injects nothing, and
  the session carries on.
- **SessionStart never parses the log.** It renders from the cached
  `board.json`. The writer that appends folds only the bytes the board has not
  seen, under the same lock, and a hook folds at most 64 KiB. `ctx board
  --rebuild` refolds from byte 0, and the two paths are byte-identical.
- **The brief is factual statements only.** The phase-0 spike found models
  treat imperative text in hook output as prompt injection. The brief has no
  imperatives and no second person. Other sessions' words appear only as a
  labelled quote: `status line, quoted: "..."`.

## What it does NOT do

**It is not a security boundary.** The owner decided on 2026-09-29 that the
core is coordination only. Hooks and `disallowedTools` guard against
accidents. The boundary is the GitHub rulesets and the server-side merge gate.
The phase-0 spike (`~/.config/broomva/fleet/ctx-spike-20260929/SPIKE-REPORT.md`)
is why:

- **P4:** `disallowedTools` removes a tool from the model's surface, even under
  bypassPermissions. But any session with Bash can still:
  - write files, so it can append anything to `events.jsonl` or hand-edit
    `board.json`;
  - `curl` the Paseo MCP endpoint with the bearer token in its own argv. The
    token is shared by every session, and `callerAgentId` is spoofable.

  The board is what sessions *say*, not an attestation.
- **P6:** a hook that crashes (exit 1) or overruns its timeout fails open. The
  tool runs, and the model never sees the failure. That is the right polarity
  for injection, which is all phase 1 does, and it is why no deny rule may rest
  on these hooks.
- **P7:** a `create_agent` with a plain `claude/*` provider yields a session
  with `FLEET_ROLE` unset. The board records a role only when one was set.
  Absence means "unknown", not "owner".
- **P1/P2:** asyncRewake wakes an idle session, but models ignore imperatives
  in its payload, and a lapsed watcher strands mail. Phase 1 arms no watcher.
  It also makes no headless-vs-interactive call. `CLAUDE_CODE_ENTRYPOINT` is
  `sdk-cli` for Paseo sessions too (#825 round 4), so nothing reads it.
- **P8:** Paseo's `lastActivityAt` is its `updatedAt`, so a label write resets
  it. Liveness here comes only from the core's own events. The brief calls a
  session *live* when it has no died event and an event in the last 6 hours.
- **Not built in phase 1:**
  - the mailbox, deltas on each prompt and asyncRewake (phase 2);
  - the role gate, holds and the owner CLI (phase 3);
  - retention. `board.json` grows with the number of distinct sessions, and
    `ctx doctor` reports its size.

## Commands

```bash
CTX="python3 -I ~/broomva/skills/skills/orchestration/ctx-core/scripts/ctx.py"
$CTX board              # bring board.json up to date, print a table (newest first)
$CTX board --json       # board.json itself
$CTX board --rebuild    # fold the whole log from scratch; says whether the cached board matched
$CTX doctor             # store, lock, board-vs-rebuild, and when each hook last fired
$CTX doctor --unscoped  # from anywhere: repos with Claude Code sessions (last 14 days) but no scope
$CTX -C <dir> board     # as if run in <dir>
```

In a repo with no scope, `board` and `doctor` print nothing and exit 0.
`doctor` exits 1 when a hook has never fired or has been silent for 24 h (the
BRO-2019 silent-dead-hook check), or when `board.json` differs from a rebuild.

## Registration (owner step; an agent does not apply it)

Registering hooks is human-gated. No agent edits `~/.claude/settings.json`,
`~/broomva/.claude/settings.json` or any `hooks.json`. The owner applies these
three steps.

**1. Scopes.** Write `~/.config/ctx/scopes.yaml`. The grammar is a strict
subset of YAML: two-space indents, one path per `- ` item, and `#` comments.
List a repo by its main checkout or its `.git`, never by a worktree:

```yaml
version: 1
scopes:
  broomva:
    - ~/broomva              # broomva/workspace
    - ~/broomva/skills       # broomva/skills
    - ~/broomva/bstack       # broomva/bstack
    - ~/broomva/broomva.tech
  sri:
    - ~/broomva/work/stimulus/sri
```

`ctx doctor --unscoped` then lists every repo that has sessions and is not in
the file.

**2. Hooks.** Merge these entries into the `hooks` object of
`~/.claude/settings.json` (user scope, so the hooks fire in every repo,
including Paseo worktrees and `claude -p`). If `SessionStart`, `Stop` or
`StopFailure` already has entries, **append** to its array; do not replace
it. The interpreter path is pinned so that the hook shell's `PATH` cannot
swap in a slower Python:

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command", "timeout": 2,
        "command": "/opt/homebrew/bin/python3 -I /Users/broomva/broomva/skills/skills/orchestration/ctx-core/scripts/ctx_hook.py session-start" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "timeout": 2,
        "command": "/opt/homebrew/bin/python3 -I /Users/broomva/broomva/skills/skills/orchestration/ctx-core/scripts/ctx_hook.py stop" } ] }
    ],
    "StopFailure": [
      { "hooks": [ { "type": "command", "timeout": 2,
        "command": "/opt/homebrew/bin/python3 -I /Users/broomva/broomva/skills/skills/orchestration/ctx-core/scripts/ctx_hook.py stop-failure" } ] }
    ]
  }
}
```

The path assumes the `~/broomva/skills` checkout is on `main`. If the skill is
installed with `npx skills add broomva/skills --skill ctx-core`, use the
installed copy's `scripts/ctx_hook.py` instead. `timeout: 2` is Claude Code's
outer bound. The hook's own deadline is 120 ms.

**3. Verify.** Open a new session in a scoped repo and end one turn. Then run
`ctx doctor` in that repo: `SessionStart` and `Stop` should report a last
event. The phase-1 exit criterion (from the design) is that for 3 days, every
session in scope appears on the board with its status.

**Rollback:** delete the three entries from `settings.json`. The store under
`~/.local/state/ctx/` is inert without them.

## Tests

```bash
cd skills/orchestration/ctx-core
python3 -m pip install -r tests/requirements-dev.txt
python3 -m pytest tests/ -q
python3 tests/mutation_check.py   # each protection removed in turn; every mutant must be killed
```

| File | Pins |
|---|---|
| `test_scope_isolation.py` | Unscoped is a silent no-op. A worktree shares its main checkout's scope. sri never reads broomva (open() audit). Ambiguous and malformed configs. crm/ cwds. `doctor --unscoped` |
| `test_lock_contention.py` | A held lock: the hook returns under 200 ms and skips the append. Two concurrent writers: neither blocks over 200 ms, and no line tears |
| `test_rebuild_determinism.py` | The board kept on write equals a full rebuild. Any split of the log folds the same. A torn line is healed. A hand edit is replaced. A replaced log is detected. SessionStart never reads the log |
| `test_fail_open.py` | A ctx module that fails to import, raises, prints, hangs, gets SIGTERM or exits non-zero: exit 0 and no output every time. Hostile stdin. An unwritable store |
| `test_redaction.py` | Every token shape, header and key=value. crm/ and secret-shaped paths. No over-redaction. Idempotent. End to end through the hooks. A token straddling the clip |
| `test_hook_deadline.py` | The normal path, a hanging git, an 11 MB log and a 10 MB board: each under 200 ms of wall time |
| `test_hooks.py` | What each hook publishes. The brief's relevance, cap and factual register. The CLI |
