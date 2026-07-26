# Changelog — ccr

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
