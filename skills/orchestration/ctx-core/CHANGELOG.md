# Changelog: ctx-core

## [0.3.1] - 2026-10-01

- **The fail-open test of a hung ctx module no longer fails on hosted macOS's
  timing** (BRO-2674). It failed at 204-243 ms against a 200 ms wall on two
  `main` commits. Measured on the macOS runner: the 80 ms alarm fires up to
  about 160 ms late (the runner's clamped QoS lets the kernel coalesce timers; at most
  10 ms late in a process a Claude Code session spawns on the owner's machine).
  Start-up plus teardown has a p99 up to 152 ms, and one run reached 589 ms. On
  ubuntu the alarm is under 1 ms late. The test now asserts three things:
  - from the hook's own miss record, that the self-deadline cut the hang, at
    most 320 ms after the budget on macOS and 40 ms elsewhere;
  - that every case, hung or not, exits within 1 s on macOS: the budget, plus
    320 ms of lateness, plus 600 ms of start-up. That is half of the 2 s timeout
    in the registration snippet, which a test now pins. Elsewhere the bound
    stays 200 ms (80 + 40 + 80);
  - that cases that do not hang leave no deadline record, at any stage.

  Four new mutants: an alarm armed 500 ms past the deadline, a bail that hangs
  past the wall, an error path that waits for the deadline, and a budget that
  eats Claude Code's timeout.

## [0.3.0] - 2026-10-01

The System 1 injection gate, System 2 cache, and their evals (workspace#840
§6.2, BRO-2674). Every stage is off by default, and the shipped floors abstain
on everything.

- **System 2** (`ctx-s1 build`): specs, ADRs, KG entities, memory rules, open
  and recent PRs and live board sessions become one-line claims with their
  source ids, keyed by path, directory, branch, PR, ticket and word; person,
  persona, `user` memory, `crm/` and credential-shaped items are excluded at
  the source. BM25 per channel behind a ranker interface; a sharded cache per
  scope, swapped in atomically. A one-hop PPR prototype (`ctx_s2_ppr.py`) fills
  the same interface as an eval arm only.
- **System 1** (`ctx_s1.py`, `ctx-s1-hook.sh`): one decision function at
  eight stages (SessionStart startup and compact, UserPromptSubmit, PreToolUse
  on edits, PostToolUse on reads and Bash, SubagentStart, PostCompact as
  measurement). Floors, budgets, per-event and per-session caps, dedup, no
  offer of the event's own file or of a file already opened, tool stages silent
  inside subagents, reviewer subagents excluded. Fails open; flags checked in
  shell before Python. Every decision logged with its top candidates.
- **E1** (`ctx-s1 eval`): a replay of 14 days of the scope's transcripts with
  counterfactual ground truth (pointer and self-authored masks); arms gate,
  always, never, wrong-key and each stage that can inject alone; separation on
  the test split, on strict hits. The snapshot stays on the owner's machine
  (`~/.local/state/ctx/<scope>/e1/`, refused inside a git checkout); only its
  aggregate report is committed. CI runs E1 on a synthetic fixture.
- **E3** (`ctx-s1 tune`): bounded per-stage coordinate search on strict F0.5
  with a ledger of full parameters, validation acceptance, and the spec's bar
  (strict precision on the test split, which no trial reads) before a floor
  ships. E1 fails the bar today at every stage, so nothing injects.
- **Its own command,** `ctx-s1` (`ctx_s1_cli.py`): `build`, `eval`, `tune`,
  `snapshot`, `follow`. `ctx.py`'s CLI stays the core's (core §5.5).
- **What it never offers:** person, persona and org entities; `user` memory;
  anything under `crm/` and any PR touching it; PRs by anyone outside the repo;
  session and PR claims from a cache older than 6 h / 24 h; the event's own
  file or one already opened; to a reviewer subagent (`Explore` included),
  nothing. A subagent gets only claims its parent received.
- **Hardening from Cross-Review round 1:** session state is replaced whole
  under a lock file (never torn); an injection that misses the deadline is
  decided before anything is recorded; the wrapper execs a loader that exits 0
  if the hook script vanished (no exit 2 from PreToolUse); a hook that raises
  leaves an `error:` breadcrumb; the registration script quotes paths, keeps
  others' hooks in a shared group and the file's mode.
- **From round 2:** the snapshot left the repo and the salt was rotated; a path
  in a nested or another scope's repo is not keyed; `gh -R` and PR URLs key
  their own repo; re-offered session and PR claims age out; the session lock
  is touched on use, checked against its path after locking, and removed by
  housekeeping only while held; the hook prints before it logs.
- **E1 fidelity (fresh round, rounds 1 and 2):** fetched paths resolve with the
  gate's own resolver; the replay carries the cwd and, for Bash, the output;
  after a `cd` an event is the new repo's; parallel calls anchor after their
  message; bare PR numbers are echoes; a fetch made before a later pointer
  stays a hit; date-only creation counts from late that day. Tune starts from
  `--params default`, needs two strict train hits, and never scores a no-op.
- **E2** (skills `scripts/skill_evals/ctx_ablation`): `s1`, `s1-<stage>` and
  `ctx+s1` arms, and rewritten retrieval tasks (`tasks/s1.json`).
- `register_s1_hooks.py`: the owner's registration script (backup, idempotent,
  `--remove`, nothing registered unless a stage is named).
- The live probe of which hook stages can inject: `references/s1-stage-probe.md`.

## [0.2.0] - 2026-09-30

- **`ctx doctor --compare --registered <UTC time>`**, the phase-1 exit
  comparison (core spec §9 as merged in broomva/workspace#842, 007f05a98).
  Board rows that are live against in-scope `claude agents --json --all`
  sessions with a timestamped transcript entry in the window (not the mtime,
  which Claude Code moves with untimestamped records long after a turn),
  matched on the full session id. The pass bar is ≥95% each way on the raw
  sets; each difference gets one reason from the spec's ordered list
  (no-transcript, ended, pre-registration, died, died-then-continued,
  stale-in-turn, no-event, else unexplained), which explains it and removes
  nothing; in-scope transcripts on neither side are listed, uncounted. The
  registration time is passed once and kept in compare.jsonl's first line; a
  later one that disagrees is refused. No evidence fails: an unreadable
  transcript directory, an empty listing (both also written to the file, so
  the latest line never shows an old pass), or an empty side.
- In `scripts/ctx_compare.py`, dispatched from `ctx.py`'s doctor path only; no
  hook imports it. Read-only on the store; it writes only `compare.jsonl`.
- The last entry is read from a tail that widens (128 KiB, 2 MiB, 16 MiB)
  past a large last line. A `compare.jsonl` whose first line is the pre-spec
  prototype's (no `neither` field) is refused, exit 2, with the `mv` that
  moves it aside; a comparison that raises is written as an error line.
- Not done here, left to the core: the hook change that records a miss (with
  the session id) when run_hook returns at the scope stage for lack of time.

## [0.1.0] - 2026-09-29

Phase 1 of the shared context core (broomva/workspace#825, round 7): the
read-only shared board.

- **Structured fields only.** The store holds:
  - ids, paths, the branch, event types and timestamps;
  - the ARC-STATUS keyword (`MERGED`, `CLOSED`, `DONE`, `BLOCKED`, `OTHER`),
    with at most 120 characters of a line of the strict shape
    `^ARC-STATUS: [A-Z]+`;
  - the StopFailure error class.

  No message or error text is read into the store. One linear guard (substring
  finds and a byte scan, no regex) drops any field with a credential-shaped
  token, a `crm/` path, or a run of 32+ alphanumerics. The schema is enforced
  on read.
- **Append-only writes.** A hook holds the `fcntl` lock only for its append.
  It waits at most 40 ms for the lock (StopFailure: the rest of its budget),
  and a skipped append is recorded. `board.json` is a cache: readers fold the
  log since its offset, SessionStart writes it back outside the lock, and `ctx
  board --rebuild` recomputes it. Cache plus tail is byte-identical to a full
  rebuild.
- `ctx.py`: the scope is read from `.git`, `gitdir` and `commondir` the way git
  does, tested to agree with `git rev-parse`. Commands: `ctx board [--json]
  [--rebuild]`, `ctx doctor` and `ctx doctor --unscoped`. `doctor` does four
  things: it tells an idle scope from a dead hook using transcripts, it reads
  the miss log, it reports a broken config from any directory, and it gives
  the board-cap recovery path.
- `ctx_hook.py`, behind `ctx-hook.sh`. The wrapper exits 0 when the script or
  the interpreter is gone, because Python exiting 2 on a missing file would
  keep a Stop hook turning. The hooks are:
  - SessionStart: register, then a factual brief of at most 4,000 chars;
  - Stop: the keyword;
  - StopFailure: `session.died`, the only terminal event.

  Each has an 80 ms self-deadline, exits 0 always, prints nothing on any
  failure, and never parses a board over 2 MiB. Misses go to a machine-wide log
  rotated at 1 MiB. Shipped unregistered; SKILL.md carries the owner's snippet.
- From #825:
  - Round 4: SessionStart never parses the whole log, and nothing reads
    `CLAUDE_CODE_ENTRYPOINT`.
  - Round 7: no retention in phase 1, and the role gate and owner CLI are cut.
    The exit comparator is board live rows vs `list_agents(cwd:"/")`, with a
    6 h transcript window.
