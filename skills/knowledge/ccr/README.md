# ccr

**Reversible payload compression — the payload axis of context reduction.**

Shrink any blob (tool output, log, RAG chunk, file) *before* it enters an LLM's
context, while caching the full original locally so it can be expanded
byte-for-byte on demand. The model sees a compact lossy view + a handle
(`ccr://<sha256>`) and calls `retrieve(handle)` only when it needs the bytes.

Content-routed deterministic compactors (JSON skeleton / code outline / text
head-tail), stdlib-only, no ML. Lifted from the CCR component of
[Headroom](https://github.com/chopratejas/headroom).

## Install

```bash
npx skills add broomva/skills --skill ccr
```

## Use

```bash
python3 scripts/ccr.py compress big.json          # view + ccr:// handle
python3 scripts/ccr.py retrieve ccr://<sha> > out # byte-exact original
python3 scripts/ccr.py stats
```

## Guarantees

- **Byte-exact.** `retrieve` returns the input's exact bytes — CRLF, lone CR,
  missing trailing newline, NUL, BOM, 4-byte UTF-8, lone surrogates and raw
  non-UTF-8 all survive. (`compress` reads bytes; text-mode reads apply
  universal-newline translation *before hashing*, which destroys the original.)
- **Confined.** A handle is `[0-9a-f]{8,64}` and nothing else, validated before
  it touches the filesystem; the record must be a real file inside the cache
  dir — absolute, `..`-relative and symlinked handles are all refused. Handles
  come back from model output, i.e. the untrusted side.
- **Atomic + verified + self-healing.** Records are published by temp-file +
  `os.replace`, so a concurrent reader never sees a partial record; every read
  — `retrieve`, `compress`'s self-heal check *and* `stats` — recomputes the
  sha256 and refuses a mismatch; an unusable record is treated as absent, so the
  next `compress` rewrites it; a temp file orphaned by a hard kill is collected
  at the next cache open once it is too old to belong to a live publish.
- **Private.** Cache dir `0700`, records `0600` — it holds plaintext originals.

See [`SKILL.md`](./SKILL.md) for the full contract.

## Test

```bash
python3 -m pytest tests/ -q        # 55 tests
python3 tests/test_ccr.py          # no pytest needed
```
