# Changelog — ccr

## 0.1.2 — 2026-07-26

The three LOW residuals left open by 0.1.1's P20 round-2 verification
(BRO-1992). Each was reproduced first; each fix is mutation-proven.

- **`--line-budget 0` did not disable the char budget for multi-line input.**
  `len(ln) <= 0` is false for every non-empty line, so *disabling* the budget
  routed the payload down the join path it was meant to avoid:
  `compact_text("a\r\nb\r\n", line_budget=0)` returned `"a\nb"` — trailing
  newline dropped, CRLF normalised, `saved_pct: 50.0`, nothing marked elided.
  `line_budget <= 0` now reaches the verbatim fast path. Only the *character*
  budget is disabled; `--head`/`--tail` keep eliding, so the two budgets are
  independently controllable as documented.
- **A hard kill mid-publish orphaned a `.ccr-tmp-*.part` file forever.**
  `_write_record` cleans up a *failed* publish, but SIGKILL runs no handler and
  nothing else in the store looks at `.part` names. Stale temp files are now
  reaped at cache open. **Age** gates the delete (6h TTL, mtime-based), not an
  exclusivity check: mtime advances while a live publish writes, so an
  hours-stale temp cannot belong to one. The window is measured, not borrowed —
  instrumenting `os.replace` across 640 concurrent publishes puts the longest a
  `.part` was ever live at **15ms** (median 0.1ms), so 6h carries ~10⁶× margin
  on its own evidence. (The *shape* of the rule matches git's `gc.pruneExpire`;
  the magnitude does not — git ships two weeks.) The scan runs once per process
  per cache dir (a full directory scan costs 4.7ms on a 5,000-record cache, 26×
  a cache-hit `compress`). Held under concurrency by a committed test — 4
  writer processes plus a continuously-reaping 5th, ~0.15s — which asserts the
  reaper collected *nothing*; an ad-hoc 16-writer run of the same shape gave
  640 records, 0 publish failures, 0 corrupt.

  Scope limit, stated: age does not cover a forward clock step larger than the
  TTL (VM snapshot restore, an RTC that NTP then corrects). Forced via `ttl=0`
  against 640 concurrent publishes, that fails publishes **loudly** with
  `FileNotFoundError` (6.2% on one run, 12.7% on an independent reviewer's) and
  corrupted **0** records in both — availability, not integrity.
- **`stats()` did not digest-verify**, contradicting "*every* read recomputes
  the sha256". It now reads through `_read_record` like every other path.
  Verification alone was not enough: the sha256 covers only `original`, so the
  ticket's own repro — editing `original_chars` to `1e9` — kept the digest
  valid and reported `cumulative_saved_pct: 100.0`. The rollup is therefore
  *derived* from the verified field, and `compact_chars` (not recomputable, the
  view is not stored) is accepted only within `0 ≤ compact ≤ original`, which
  every record satisfies by construction. Excluded entries are reported with
  **the reason that excluded them** (`unusable_reasons`, a per-reason count),
  so `entries` cannot quietly disagree with the file count *and* the CLI cannot
  narrate a cause nobody checked: a lump sum invited "digest mismatch —
  re-compress to heal", which is false for a stray `hello.json`, a dangling
  symlink or a directory named `adir.json`. Cost: +47% on a scan that was
  already linear in cached bytes (545ms → 802ms on a 5,000-record / 20MB cache)
  — `stats` is a diagnostic command, and a rollup inflatable by editing one
  integer is worse than a slower one.

Tests: 49 → **55**.

## 0.1.1 — 2026-07-26

Pre-merge hardening pass. A cross-model adversarial review (P20) blocked 0.1.0
at 4/10 with executed evidence; every finding below was reproduced before it was
fixed, and every fix is mutation-proven (revert the fix, the named test fails).
**Several 0.1.0 claims were simply false — they are true now.**

Security

- **Arbitrary file read via the 64-char handle fast path.** `_resolve_sha`
  returned any 64-char token whose `cache_dir / token` existed, without checking
  it was hex — and `Path.__truediv__` *discards* the cache dir for an absolute
  token and keeps `..` for a relative one. Proven escapes: a 64-char
  `../././…/leak` token, an absolute path token, and a symlink planted in the
  cache dir. Handles now validate against `[0-9a-f]{8,64}` **before** any
  filesystem access, and the resolved record must be a real (non-symlink) file
  inside the cache dir. The 0.1.0 test only exercised tokens of length != 64,
  i.e. only the branch that was never vulnerable.
- **Cache is no longer world-readable**: dir `0700`, records `0600`.

Correctness

- **Byte-exactness was false via `ccr compress <file>`.** `Path.read_text`
  applies universal-newline translation, so `\r\n` and lone `\r` became `\n`
  *before* the payload was hashed and cached — the original bytes were gone and
  `retrieve` could never return them. Now reads bytes (`surrogateescape`) and
  writes through `stdout.buffer`. Non-UTF-8 input is accepted instead of
  rejected, and lone-surrogate payloads are retrievable via the CLI.
- **Cache was neither atomic nor verified.** Records are published by temp-file
  + `os.replace` (235 torn reads were observed by a concurrent reader during one
  60MB write; now 0); every read recomputes the sha256 and refuses a mismatch;
  an unparsable *or* mis-digested record is treated as absent, so `compress`
  self-heals instead of cementing corruption behind an `exists()` check.
- **ReDoS in `_IMPORT_RE`.** `^\s*` — `\s` matches `\n` — ran to EOF and
  backtracked at every line start: 32KB of blank lines took 5.6s, 64KB took 26s,
  quadratic, and reachable from `--type auto`. Now line-bounded, ~1ms.
- **0% compression on single-line blobs.** `compact_text` was purely
  line-oriented, so a 2MB one-line payload and a 1.27MB truncated JSON blob
  returned in full as the "compact view". Adds a per-line **character** budget
  (`--line-budget`, default 2000, `0` disables); both now compress >99%.
- `RecursionError` no longer escapes `compress()` on deeply nested JSON
  (`_shape`'s list branch had no depth cap); past the parser's own limit
  `--type auto` degrades to text and explicit `--type json` exits 1, not 2.
- `--tail 0` no longer silently disables compression (`lines[-0:]` is the whole
  list); negative `--head`/`--tail` are clamped rather than producing a view
  *larger* than the original with a misreported elision count.
- A UTF-8 BOM no longer defeats JSON auto-detection (stripped in both
  `detect_type` and `compact_json`).
- `--json` is now a pure-ASCII machine envelope, so it stays pipeable for
  payloads carrying bytes no JSON reader could decode. Found while fixing the
  above: accepting non-UTF-8 input put lone surrogates into the *view*, and
  `print()` encodes stdout strictly.

Tests: 18 → **49**. The suite now drives the real CLI over a byte-level fixture
matrix (`\r\n`, lone `\r`, no trailing newline, NUL, BOM, 4-byte UTF-8, lone
surrogate, raw non-UTF-8) — 0.1.0 contained no `\r` anywhere and never invoked
the CLI. Three 0.1.0 tests were green for reasons unrelated to their names and
were rewritten to assert at the layer that can actually break.

Handle compatibility: unchanged for LF-only, valid-UTF-8 inputs and for all
Python-API `str` callers. Handles **do** change for CRLF/CR files read through
the CLI — that is the bug being fixed (they were previously the handle of a
newline-translated copy). Existing cache records stay valid and verify fine.

## 0.1.0 — 2026-06-15

Initial release. Reversible payload-compression primitive lifted from the CCR
component of [Headroom](https://github.com/chopratejas/headroom) via `/checkit`
(BRO-1521).

- `compress(payload, content_type=auto, filename=hint)` → compact view +
  `ccr://<sha256>` handle; content-addressed local cache of the original.
- `retrieve(handle)` → byte-exact original (full handle or unique prefix).
- `stats()` → cache size + cumulative savings.
- Content-routed compactors: JSON skeleton / code outline / text head-tail.
- 18 unit tests; surrogate-safe storage; view never larger than the original.
  (The ReDoS guard covered only one of the two code regexes and the traversal
  guard missed the 64-char handle path — both corrected in 0.1.1 below.)
- Graduated into the `broomva/skills` monorepo (the portable tier), sibling to
  the workspace-local `kg` loader (the retrieval axis).
