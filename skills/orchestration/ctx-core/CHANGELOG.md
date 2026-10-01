# Changelog: ctx-core

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
