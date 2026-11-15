---
name: year-in-ai
tier: D
category: knowledge
description: "A Spotify-Wrapped-style retrospective of your year with AI agents, computed from local history across harnesses (Claude Code, Codex, T3, Conductor, Gemini CLI, bridged transcripts, exports). Two layers. (1) A year-round HARVEST folds every turn into a text-free ledger (counts, hashes, who wrote it) and optionally ARCHIVES the transcripts that their own tools prune (Claude Code deletes sessions after ~30 days), because a December extract alone cannot cover a year. (2) The recap: ATTENTION folds the ledger into words you wrote vs words you read (final reply per human turn × a stated read share, 60-70% by default), separating human prompts from agent-dispatched ones per each store's own author flags; EXTRACT/RENDER build the story deck. USE WHEN year in ai, your year in ai, ai wrapped, wrapped for my agents, year in review of my ai usage, how much have I written to agents, how much have I read, words written and read, harvest agent history, archive agent transcripts, set up the year-in-ai harvest. NOT FOR billing or token cost (use the provider's usage tools), single-session search (use session-search), or health/sleep recaps."
argument-hint: "[harvest|attention|run] [--year YYYY]"
effort: medium
---

# year-in-ai

A Wrapped-style recap of a year spent working with agents, built from the
history already on this machine. Nothing leaves the machine.

## Why there are two layers

Local transcript stores decay. Claude Code prunes sessions after about 30
days, and a harness migration can lose a whole window, so the recap cannot be
computed in December from the stores alone. The skill therefore has:

1. **Harvest (all year).** `harvest` reads every store it can find and folds
   each turn into a ledger row: timestamps, word and character counts, content
   hashes and author flags. **Rows never hold message text.** `--archive-to`
   also copies the stores that prune themselves to a larger disk. Nothing
   archived is ever lost: a file is replaced only by one that extends it byte
   for byte; a rewritten or truncated source opens a numbered revision,
   `<name>.rev-<n>.jsonl`, which later growth extends in place. A file its
   tool rewrites wholesale every week would add one revision per rewrite;
   none of the archived stores does that, and `harvest` prints the revision
   count so growth is visible. Revisions are kept for quoting and are **never
   ledger input**: the harvest skips every `*.rev-<n>.jsonl` file. Turns that
   exist only in a revision (a transcript rewritten and then pruned at its
   source) are preserved on disk but not counted. A transcript whose own name
   ends in `.rev-<n>.jsonl` would be skipped too; Claude Code and Codex name
   sessions by UUID.
2. **Recap (once a year).** `attention` folds the ledger into what you wrote
   and read. `extract` and `render` build the story deck from transcripts.

## Commands

Run from `scripts/` with Python 3.9 or later. No third-party packages.

```bash
# First run: read everything still on disk.
python3 year_in_ai.py harvest --backfill --archive-to /Volumes/Archive/agent-traces

# Scheduled run (weekly is safe: the shortest store retention is ~30 days).
python3 year_in_ai.py harvest --days 45 --archive-to /Volumes/Archive/agent-traces

# Words written and read for a year, from the ledger.
python3 year_in_ai.py attention --year 2026 --out attention.json

# The story deck.
python3 year_in_ai.py run --year 2026 --outdir ./year-in-ai-out
```

## Stores and how each says who wrote a turn

| Store | Default location | Author signal |
|---|---|---|
| T3 | `~/.t3/userdata/statev2.sqlite` | `createdBy` user/agent per message; subagent threads skipped |
| Claude Code | `~/.claude/projects` | `entrypoint`: `cli` is a person, `sdk-cli` is `claude -p`, `sdk-ts` is an app (not counted) |
| Claude prompt history | `~/.claude/history.jsonl` | typed in the CLI; usage probes dropped |
| Codex | `~/.codex/sessions` (`.jsonl`, `.jsonl.zst`) | `originator`/`source`: `codex_exec` is a script |
| Codex prompt history | `~/.codex/history.jsonl` | typed in the TUI |
| Conductor | `~/Library/Application Support/com.conductor.app/conductor.db` | user role |
| Gemini CLI | `~/.gemini/tmp/*/chats` | user role |
| Paseo | `~/.paseo/agents` | its Claude sessions count as orchestrator traffic |
| Bridged markdown | config `bridged` | none: filtered, then used only before exact coverage |
| Exports | config `exports` | none: filtered |

Add archive copies and extra stores in `~/.config/year-in-ai/config.json`. If
that file is absent the config is empty; a `--config` that does not exist, or
any config that cannot be read or is not a JSON object, stops the run with
status 2 instead of silently dropping its stores:

```json
{
  "roots": {
    "claude_projects": ["/Volumes/Archive/agent-traces/claude-projects"],
    "codex_sessions": ["/Volumes/Archive/agent-traces/codex-sessions"],
    "bridged": ["~/workspace/docs/conversations"],
    "exports": ["~/exports/conversations.jsonl"]
  },
  "archive_to": "/Volumes/Archive/agent-traces",
  "text_only_until": "2026-10-18",
  "utc_offset_hours": -5
}
```

## Identity: occurrences first, turns second

Every row a reader emits has an **occurrence** identity: the store's own
message id where it has one (T3, Conductor, Claude Code, Gemini), otherwise
the session, timestamp, role, text hash and a count of earlier identical
occurrences. The occurrence id is stable across harvests and carries no text.
A **row** is one revision of an occurrence: its id is the occurrence plus the
hash of its text, so an unchanged message harvested twice is one row, an
edited one adds a row for the same occurrence, and two occurrences never share
a row. The ledger stamps each row with a harvest sequence; the fold keeps each
occurrence's latest revision by that sequence, and a message that returns to
earlier text gets a new row (`revision_identity`). Pruning or inserting
records moves no other occurrence id. `tests/test_reader_contract.py` runs these cases against every reader in
`sources.REGISTRY` and fails when a reader has no fixture. Whether two
occurrences are the same *turn* is a separate, evidence-based decision in the
fold.

## Requirements

Python 3.9 or later, nothing else, except **zstd** for compressed Codex
transcripts (`*.jsonl.zst`). It is looked for on `PATH`, then in
`/opt/homebrew/bin`, `/usr/local/bin` and `/usr/bin`, so a launchd job with a
minimal `PATH` still finds a Homebrew install.

**No file is ever skipped silently.** Readers find files only through
`list_files` and read them only through `read_lines` and `read_text` (a test
fails otherwise), and these report every failure: a directory that cannot be
listed, zstd missing, a corrupt or truncated archive, a file that cannot be
opened or read, a malformed Gemini chat, an unreadable T3 or Conductor
database, and a store that exists but cannot be reached (permission denied on
it or on a directory above it). Only a store that does not exist is absent.
Symlinked directories inside a store are followed. A failure counts as
`skipped` on its source, never as an empty store; `harvest` prints a warning naming the cause and exits with status 4.
That is what a scheduled job without disk access looks like, so treat exit 4
from launchd as "grant access", not as a quiet week.

## Live stores and their archives

A store and its archive copy hold the same files under the same names, and
`harvest` reads one copy of each: the newest write, with ties going to the
live store. For transcripts that only grow (Claude Code, Codex), an older
copy wins instead when its content, decompressed, extends the newest one byte
for byte, because the newest was truncated. Size alone is never taken as
freshness, since an edit can shorten a file.

## How "written" and "read" are counted

- **Written:** prompts a person wrote, counted as turns. Each store's author
  signal (table above) decides who wrote a prompt, and a prompt marked as an
  agent's never counts. Only T3's per-message `createdBy` is exact enough to
  stand alone. Every other store's human prompts also pass three filters,
  because a script can drive those harnesses the way a person does (see the
  known limit below): no automation opening, no exact text repeated across
  three sessions, no opening repeated across four. Prompts from stores with no
  author at all (bridged markdown, exports) must also be 1,500 characters or
  shorter: longer unflagged prompts were dispatched briefs far more often than
  writing. A turn recorded by two stores counts once (the closest
  same-text turn within 36 hours, 20 minutes under 80 characters). A resumed
  or forked session's copy counts once, but only on evidence: the store's own
  message id, a T3 fork's creation time, or, for markdown and exports, a run
  of matching neighbouring turns. Anything else typed twice counts twice.
- A ledger written by an older schema version is never mixed in: `harvest`
  refuses to append to it and `attention` ignores its rows. Rebuild with
  `harvest --backfill` into a fresh ledger directory.
- **Read:** the final reply to each counted prompt, times the read share
  (`--read-low`/`--read-high`, default 0.60–0.70). Prompts from stores that never kept
  replies get an estimated reply from measured replies of the same harness
  family (a CLI prompt from CLI replies), reported separately. A family with
  no measured replies is never estimated from another family; its prompts are
  reported as `unestimated_prompts`.
- **The ratio** is words read over *authored* words written: pasted blocks,
  paste placeholders and fenced code blocks are removed, and what remains is
  capped at 4,000 characters per prompt (a longer one is a paste, whatever its
  markup).
- **Known limits.**
  - An agent that drives the interactive `claude` CLI through a terminal looks
    exactly like a person to every store. Only the scripted-prompt filters
    (repeated text, repeated openings, automation markers) catch it, and a
    person who types the same long prompt into three sessions is filtered too.
  - Stores without message ids (Codex rollouts, the Claude and Codex prompt
    histories, bridged markdown, exports) identify a turn by its text. A turn
    whose text changes there is a second turn. In practice these stores do
    not edit history: rollouts and histories only append, and bridged
    markdown is a generated rendering, used only before `text_only_until`.
  - Identical prompts in a store without message ids (same session, time and
    text) are told apart by order, so pruning one can relabel the others;
    their count in the ledger stays right.
- **The agents' own year:** replies to agent-written prompts are reported on
  their own, never added to what you read.
- Set `text_only_until` to the date a store with exact authors starts covering
  you. Measured on one machine, only ~18% of bridged "user" turns after that
  date matched a human-typed prompt.

## Privacy

- The ledger holds no message text. Session ids are stored as hashes, and
  attribution fields accept only known values (anything else becomes
  `other`). Tests fail the build if a fixture phrase reaches a ledger file or
  metadata carries free text.
- Text hashes of very short prompts ("yes", "go") can be guessed by
  dictionary. Keep the ledger as private as the transcripts.
- `extract --share` redacts client and CRM paths and verbatim prompts before
  anything is shared.

## Scheduling on macOS

A launchd job that reads an external or encrypted volume needs Full Disk
Access. Run the harvest through `/bin/bash` (grant it access) and the system
`/usr/bin/python3`. Homebrew's Python hangs on the privacy prompt instead of
failing.

## Tests

```bash
python3 -m pytest tests/ -q
```
