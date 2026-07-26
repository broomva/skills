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
python3 scripts/ccr.py compress big.json        # view + ccr:// handle
python3 scripts/ccr.py retrieve ccr://<sha>      # byte-exact original
python3 scripts/ccr.py stats
```

See [`SKILL.md`](./SKILL.md) for the full contract.

## Test

```bash
python3 -m pytest tests/ -q        # 18 tests
```
