# Changelog — ccr

## 0.1.0 — 2026-06-15

Initial release. Reversible payload-compression primitive lifted from the CCR
component of [Headroom](https://github.com/chopratejas/headroom) via `/checkit`
(BRO-1521).

- `compress(payload, content_type=auto, filename=hint)` → compact view +
  `ccr://<sha256>` handle; content-addressed local cache of the original.
- `retrieve(handle)` → byte-exact original (full handle or unique prefix).
- `stats()` → cache size + cumulative savings.
- Content-routed compactors: JSON skeleton / code outline / text head-tail.
- 18 unit tests; ReDoS-guarded code regex; surrogate-safe storage;
  path-traversal-rejecting retrieve; view never larger than the original.
- Graduated into the `broomva/skills` monorepo (the portable tier), sibling to
  the workspace-local `kg` loader (the retrieval axis).
