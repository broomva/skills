---
name: ccr
description: >-
  ccr — reversible payload compression: shrink any blob (tool output, log, RAG
  chunk, file) BEFORE it enters an LLM's context, while caching the full
  original locally so it can be expanded byte-for-byte on demand. The
  payload-axis counterpart to a knowledge-graph loader (the retrieval axis):
  the model sees a compact lossy view + a handle (ccr://<sha256>), and calls
  retrieve(handle) only when it needs the bytes back. Content-routed
  deterministic compactors (json skeleton / code outline / text head-tail);
  stdlib-only, no ML. Lifted from the CCR component of github.com/chopratejas/headroom.
  USE WHEN — a tool output / log / RAG chunk / file is too large for context and
  you want to compress it reversibly; "compress this payload", "shrink this
  before the model", "reversible compression", "cache the original and give me a
  handle". NOT FOR — loading knowledge-graph entities (that's the kg loader,
  the retrieval axis); lossless whole-file compression (use gzip); semantic
  summarization that does not need byte-exact recovery.
---

# ccr — reversible payload compression (the payload axis)

`ccr compress <file|->` · `ccr retrieve <handle>` · `ccr stats`

Shrink any blob — a tool output, a log, a RAG chunk, a file — **before** it
enters context, while keeping the original recoverable. The **payload-axis**
counterpart to a knowledge-graph loader (the **retrieval axis**): kg shrinks
*which* entities reach the model; ccr shrinks *each blob* that does.

Lifted from the **CCR / reversible-compression** component of
[Headroom](https://github.com/chopratejas/headroom) (28.5k★, Apache-2.0). We
lifted the *pattern*, not the dependency. Anchor: **BRO-1521**.

## The one idea

> Compression is reversible because the **full original is cached locally**,
> keyed by content hash. The model sees a compact lossy *view* + a handle
> (`ccr://<sha256>`); it calls `retrieve(handle)` only when it needs the bytes.

So the view can be aggressively lossy without losing information — the loss is
recoverable on demand. Same shape a KG loader uses on the other axis: a lossy
catalog projection that expands to the full entity body on load.

## Mechanism

Dispatch by detected content type (a file-extension hint beats the content
heuristic, which beats nothing):

| Type | Compact view | Reversible? |
|---|---|---|
| `json` | type/shape skeleton (keys + value types + collection sizes; **no leaf data**) | yes (cache) |
| `code` | structural outline (imports + `def`/`class`/`fn` signatures w/ line numbers; **bodies elided**) | yes (cache) |
| `text` | head + tail with an elision marker | yes (cache) |

Deterministic, **stdlib-only, no ML** — the value is the reversible-cache
architecture, not the compression ratio. Identical payloads are
content-addressed (idempotent: one handle, one record). The view is never
emitted larger than the original (tiny inputs fall back to the payload).

## Usage

```bash
python3 scripts/ccr.py compress path/to/big.json          # view on stdout, savings on stderr
cat huge.log | python3 scripts/ccr.py compress - --type text --head 30 --tail 10
python3 scripts/ccr.py retrieve ccr://<sha256>            # byte-exact original (full handle or unique prefix)
python3 scripts/ccr.py stats --json                       # cache size + cumulative savings
```

As a library:

```python
import ccr
r = ccr.compress(payload, filename="server.ts")   # auto-detects code
context_blob = r["view"]                            # feed this to the model
original = ccr.retrieve(r["handle"])                # expand on demand
```

`BROOMVA_CCR_HOME` relocates the content-addressed cache (default
`~/.cache/broomva/ccr/`) for CI runners and non-standard layouts.

## Tests

```bash
python3 -m pytest skills/ccr/tests/ -q     # 18 tests
python3 skills/ccr/tests/test_ccr.py       # no pytest needed
```

Core invariant under test: the view is lossy, but `retrieve(handle)` returns the
original **byte-for-byte** for every content type — verified across empty /
unicode / lone-surrogate / bare-scalar-JSON inputs, plus path-traversal
rejection and a ReDoS guard.

## Install

```bash
npx skills add broomva/skills --skill ccr
```

## Provenance

- Origin: `/checkit github.com/chopratejas/headroom` → entity `tool/headroom`
- Pattern sibling: the `kg` loader (retrieval axis) / `llm-as-index-architecture`
- Ticket: BRO-1521
