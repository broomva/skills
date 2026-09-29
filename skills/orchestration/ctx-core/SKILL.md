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
  `ctx doctor` checks the config, store and hooks, and `ctx doctor --unscoped`
  lists repos that have sessions but no scope. Coordination only; not a
  security boundary. USE WHEN setting up or checking the shared board, asking
  "which sessions are on this branch", "what is every session doing", "is
  anyone else working here", reading or debugging the ctx store, registering
  the ctx hooks, or adding a repo to a scope. NOT FOR messaging a session or
  waking an idle one (phase 2, not built), enforcing what a session may do (no
  local hook is a boundary), or waiting on CI (use p9).
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

It is read and publish only. There is no mailbox, no wake-up, and no
retention.

## What it does

| Piece | Does |
|---|---|
| `scripts/ctx.py` | The single writer and reader: scope resolution, redaction, the locked append, the board fold, and the CLI |
| `scripts/ctx_hook.py` | The hook entry for `session-start`, `stop` and `stop-failure`. It owns the deadline, the output guard, the deadline-miss record, and exit 0 |
| `~/.config/ctx/scopes.yaml` | Scope id → repos, written by the owner. The key is the realpath of the repo's git common dir, so every worktree of a repo lands in its main checkout's scope |
| `~/.local/state/ctx/<scope>/events.jsonl` | Append-only, one JSON object per line. Schema: [`references/event-schema.md`](references/event-schema.md) |
| `~/.local/state/ctx/<scope>/board.json` | The log folded, as compact JSON. Derived, never edited by hand |
| `~/.local/state/ctx/hook-misses.jsonl` | One line per hook that ran out of time or had to skip work (a busy lock, a board over its cap): event, stage, ms, with no path. Machine-wide. Written only when `scopes.yaml` exists, and rotated to `.1` at 1 MiB |

| Hook | Publishes | Prints |
|---|---|---|
| SessionStart | `session.start`: source, model, `FLEET_ROLE` if set, `PASEO_AGENT_ID` if set | A brief of at most 4,000 chars in `hookSpecificOutput.additionalContext`, or nothing when no other session is relevant |
| Stop | `session.stop` plus the last `ARC-STATUS:` line of `last_assistant_message`. Every stop is also a heartbeat | Nothing |
| StopFailure | `session.died`, the one terminal event, with the error class and the redacted error text. Both are on the board row as `died_reason` and `died_error`, so a usage-limit message is readable from the board. Claude Code 2.1.280 sends `{error: <class>, error_details}`; the hooks reference documents `{error_type, error}`; both are read. Phase 1 keeps a single died event: the died/failed split and reset-time extraction are phase 2. Limit and API-error deaths never fire Stop | Nothing (the output is ignored) |

**How it finds the repo.** A hook reads `.git`, the `gitdir:` file of a
worktree or submodule, and `commondir` itself, which is the rule `git
rev-parse --git-common-dir` follows. So a hook spawns no process. A test checks
that the resolver agrees with git on each of these layouts:
- a main checkout and its subdirectories;
- a linked worktree;
- a nested repo (sri inside broomva);
- a submodule;
- a `.git` directory, a bare repo, and a non-repo, each of which gives no repo.

git itself runs only when `GIT_DIR`, `GIT_WORK_TREE` or `GIT_COMMON_DIR`
redirect it, or to read a reftable repo's branch. It is then bounded and
killed.

Invariants, each pinned by a test:

- **A repo with no scope is a silent no-op.** Every hook and every command
  exits 0 with no output. The same holds for a cwd outside git and for a repo
  listed in two scopes; the ambiguous repo has no scope, and the other repos
  are unaffected. A malformed `scopes.yaml` disables every scope. `ctx doctor`
  reports that from any directory and exits 1.
- **Scopes never cross.** The `sri` and `broomva` stores are separate
  directories. A test audits every `open()`, `io.open()` (what pathlib uses)
  and `os.open()` that an sri session makes, and finds none under broomva's
  store.
- **Secrets are redacted, as far as a denylist can.** The redaction pass runs
  over every string before it is written, and before any clipping. It covers:
  - vendor token shapes: GitHub, Anthropic, OpenAI, Stripe, Slack (including
    `xapp-` tokens and webhook URLs), AWS, Google (including `ya29.`), JWT, npm,
    GitLab, Linear, SendGrid, Telegram, Supabase and Groq;
  - `Authorization` and `Cookie` headers, and `Bearer` values;
  - `key=value` and `key: value` pairs whose key names a secret, camelCase
    keys included;
  - `--password`/`--token` flags and `curl -u user:pass`;
  - URL credentials and credential query parameters;
  - private-key blocks;
  - a credential named in prose ("token 1a2b…", "the password is …");
  - any unbroken run of 32 or more letters and digits that mixes upper case,
    lower case and at least four digits.

  Paths under `crm/`, or with a secret-shaped segment (`.env*`, `.ssh`, `.aws`,
  `*.pem`, `id_*`, `credentials`, `secrets`), become `[excluded-path]`, and a
  session whose cwd is such a path writes nothing. Only the payload is free
  text and redacted. The identifiers (cwd, repo, branch) come from git and the
  filesystem, so they are validated and flattened rather than redacted. That
  way a branch like `fix/credentials` still matches its peers. The pre-cap that
  bounds regex time also drops a partial word at the cut, so it cannot leave a
  token prefix behind. **This is still a denylist.**
  A secret in a shape it doesn't know gets written. The narrow surface limits
  the exposure: only an ARC-STATUS line, an error string and metadata are
  written, to files with mode 0600.
- **A hook never blocks a session:**
  - Hooks wait on the `fcntl.flock(LOCK_EX | LOCK_NB)` lock for at most 40 ms.
    StopFailure waits for what is left of its budget, because `session.died`
    is the one terminal event and a burst of limit deaths contends. After that
    the append is skipped, and the skip is recorded as a miss. The CLI retries
    the lock for up to 2 s.
  - The hook has a hard self-deadline of 80 ms inside the interpreter, and 200
    ms of wall time measured from outside (it runs as `python3 -I -S`). The alarm cannot interrupt one long
    C call. The only such call that grows is parsing `board.json`, so a hook
    will not parse a board over 2 MiB (about 3,000 sessions). It appends its
    event, skips the fold and the brief, records a `board-cap` miss, and
    `ctx doctor` reports a PROBLEM. With no retention in phase 1, a busy scope
    reaches that cap in weeks.
  - Every hook exits 0, including on SIGTERM.
  - Tracebacks and stray prints go to `/dev/null`.
  - A half-written board temp file is removed at the deadline.
- **Injection fails open, and the failure is recorded.** A hook that runs out
  of time, or skips its append or fold, injects nothing. It leaves one line in
  `hook-misses.jsonl`, so `ctx doctor` can tell "too slow under load" from
  "not registered".
- **SessionStart never parses the log.** It renders from the cached
  `board.json`:
  - The writer that appends folds only the bytes the board hasn't seen, under
    the same lock, and a hook folds at most 64 KiB.
  - `ctx board --rebuild` refolds the log from byte 0 outside the lock, and the
    two paths give byte-identical boards.
  - The brief is one pass over the rows, and rows are rendered only until the
    4,000-char cap.
- **The brief is factual statements only.** The phase-0 spike found models
  treat imperative text in hook output as prompt injection. So the brief has no
  imperatives and no second person, and every field is flattened to one line.
  A newline in `FLEET_ROLE` or in a status line cannot start a sentence of its
  own. Free text from other sessions (the status line, the error text,
  `FLEET_ROLE`) appears only as a labelled quote, such as `status line, quoted:
  "..."`. Branch and cwd are identifiers, flattened to one line. The branch is
  checked against git's refname rules.

## What it does NOT do

**It is not a security boundary.** The owner decided on 2026-09-29 that the
core is coordination only. Hooks and `disallowedTools` guard against
accidents. The boundary is the GitHub rulesets and the server-side merge gate.
The phase-0 spike (`~/.config/broomva/fleet/ctx-spike-20260929/SPIKE-REPORT.md`)
is why:

- **P4:** `disallowedTools` removes a tool from the model's surface, even under
  bypassPermissions. But any session with Bash can still:
  - write files, so it can append anything to `events.jsonl` or hand-edit
    `board.json` (`ctx doctor` detects a hand edit, but nothing prevents one);
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
  it. Liveness here comes only from the core's own events. A session is *live*
  when it has no `session.died` and an event in the last 6 hours. The only
  **terminal** event is `session.died`. Stop fires at the end of every turn, so
  `session.stop` is a heartbeat, not an end. Nothing marks a session ended
  (SessionEnd is not hooked), so a closed session stays live for up to 6 hours.
- **Not built in phase 1:**
  - **Retention.** The log and `board.json` only grow. `ctx doctor` says so and
    reports their size. Retention and compaction are phase 2 of the design
    (#825 round 7).
  - The mailbox, deltas on each prompt, and asyncRewake (phase 2).
  - The role gate and the owner CLI. The design cut them; no phase will build
    them.

## Commands

```bash
CTX="python3 -I ~/broomva/skills/skills/orchestration/ctx-core/scripts/ctx.py"
$CTX board              # bring board.json up to date; print a table, newest first, with the live count
$CTX board --json       # board.json itself
$CTX board --rebuild    # refold the log from scratch; says whether the cached board matched
$CTX doctor             # config, store, board-vs-rebuild, hook activity, deadline misses, retention
$CTX doctor --unscoped  # from anywhere: repos with Claude Code sessions (last 14 days) but no scope
$CTX -C <dir> board     # as if run in <dir>
```

In a repo with no scope, `board` prints nothing and exits 0, and so does
`doctor` unless the config itself is broken or ambiguous, which it reports
from any directory. `doctor` exits 1 in any of these cases:
- the config is broken (reported from any directory);
- a repo is listed in two scopes;
- `board.json` differs from a rebuild of what it claims to have folded;
- the board has fallen more than 64 KiB behind the log, which no hook can
  close;
- `board.json` is over the 2 MiB a hook will parse (it warns at half);
- Claude Code sessions ran in the scope in the last 24 h (judged from their
  transcripts) and no hook recorded any of them. That is the BRO-2019
  silent-dead-hook case. Doctor attributes it to misses when there are any,
  and otherwise to registration. Misses carry no path, so they are reported as
  machine-wide.

An idle scope is not a problem.

## Registration (owner step; an agent does not apply it)

Registering hooks is human-gated. No agent edits `~/.claude/settings.json`,
`~/broomva/.claude/settings.json` or any `hooks.json`. The owner applies these
three steps.

**1. Scopes.** Write `~/.config/ctx/scopes.yaml`. The grammar is a strict
subset of YAML: two-space indents, one path per `- ` item, and `#` comments.
List a repo by its main checkout, its `.git`, or any of its worktrees:

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
        "command": "/opt/homebrew/bin/python3 -I -S /Users/broomva/broomva/skills/skills/orchestration/ctx-core/scripts/ctx_hook.py session-start" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "timeout": 2,
        "command": "/opt/homebrew/bin/python3 -I -S /Users/broomva/broomva/skills/skills/orchestration/ctx-core/scripts/ctx_hook.py stop" } ] }
    ],
    "StopFailure": [
      { "hooks": [ { "type": "command", "timeout": 2,
        "command": "/opt/homebrew/bin/python3 -I -S /Users/broomva/broomva/skills/skills/orchestration/ctx-core/scripts/ctx_hook.py stop-failure" } ] }
    ]
  }
}
```

The path assumes the `~/broomva/skills` checkout is on `main`. If the skill is
installed with `npx skills add broomva/skills --skill ctx-core`, use the
installed copy's `scripts/ctx_hook.py` instead. `timeout: 2` is Claude Code's
outer bound. The hook's own deadline is 80 ms. `-I` keeps a module planted in
the session's cwd from being imported; `-S` skips `site`, which is a third of
interpreter start-up, and everything here is stdlib.

**3. Verify.** Open a new session in a scoped repo and end one turn. Then run
`ctx doctor` in that repo. `SessionStart` and `Stop` should report a last
event, and `misses` should be absent or small.

**Phase-1 exit comparator** (#825 round 7):
- One side is the board's live rows: rows with an event inside the 6 h window
  (`LIVE_WINDOW_S`) and no `session.died`. `ctx board` prints the live count
  and a LIVE column.
- The other side is the `list_agents(cwd: "/")` agents in scope whose
  transcript was modified in the same 6 h.
- Phase 1 passes when at least 95% of each set appears in the other, and every
  difference is listed with its reason.
- Expected reasons for a difference:
  - a single turn longer than 6 h (Stop has not fired, so the row aged out);
  - a session closed within the window (nothing marks a session ended);
  - a session not launched by Paseo (`claude -p`, a terminal session), which
    has no `paseo_agent_id`. `ctx board` counts live rows with a Paseo agent
    separately;
  - a hook that ran out of time or skipped its append (`ctx doctor` lists the
    misses, by stage);
  - a session in an unscoped repo.

**Rollback:** delete the three entries from `settings.json`. The store under
`~/.local/state/ctx/` is inert without them.

## Tests

```bash
cd skills/orchestration/ctx-core
python3 -m pip install -r tests/requirements-dev.txt
python3 -m pytest tests/ -q
python3 tests/mutation_check.py   # 23 protections removed in turn; the test pinning each must fail
```

| File | Pins |
|---|---|
| `test_scope_isolation.py` | Unscoped is a silent no-op. A worktree shares its main checkout's scope. The filesystem resolver agrees with `git rev-parse` on every layout. sri never reads broomva (`open()` audit). Per-repo ambiguity. Malformed configs. crm/ cwds. `doctor --unscoped` |
| `test_lock_contention.py` | A held lock: the hook returns under 200 ms, skips the append, and records the skip. Two concurrent writers: neither blocks, and no line tears |
| `test_rebuild_determinism.py` | The board kept on write equals a full rebuild. Any split of the log folds the same. A torn line is healed. A hand edit is detected and replaced. A replaced log is detected. SessionStart never reads the log. A board past the fold cap is a doctor problem |
| `test_fail_open.py` | A ctx module that fails to import, raises, prints, hangs, gets SIGTERM or exits non-zero: exit 0 and no output every time. Hostile stdin. An unwritable store. The deadline-miss breadcrumb |
| `test_redaction.py` | Every token shape, header, flag and key=value, the paths, no over-redaction, idempotence, end to end through the hooks, a token straddling the clip or the pre-cap, and no quadratic pattern |
| `test_hook_deadline.py` | The normal path, git never run (or bounded and killed on the `GIT_DIR` path), an 11 MB log, and a board over the cap (not parsed, the cut-off recorded, the events still appended): each under 200 ms of wall time |
| `test_hooks.py` | What each hook publishes, including both StopFailure shapes. The brief's relevance, cap, one-line fields, linear cost and factual register. The CLI. Doctor tells idle from dead, and reports a broken config from anywhere |
