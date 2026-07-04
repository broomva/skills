# Changelog

All notable changes to `broomva/eve-forge` are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-07-04

### Added
- Initial release. **8-stage forge pipeline** (absorb → scaffold → author → validate → deploy → smoke → register → evolve) for producing deployed, tenant-scoped **eve** agents from a business's absorption inputs. Distilled from a driven Life-vs-eve benchmark (broomva BRO-1677).
- **Deterministic core** (`scripts/`), 26 unit tests:
  - `deploy_safety.py` — the incident-derived, fail-closed auth-lock gate: never ship a channel with `auth: none()`/`placeholderAuth()`. Wireable as a Claude-Code PreToolUse hook.
  - `validate.py` — `eve info --json` → 0 diagnostics + expected tools registered.
  - `smoke.py` — deployed output vs a ground-truth example (word-boundary matched).
  - `eve_forge.py preflight` — Node ≥ 24 (the `npx eve init` trap).
- **References**: `gotchas.md` (the benchmark's traps) + 4 eve agent templates with channel auth **locked by default**.
- **P20-hardened**: adversarial review round 1 scored the auth gate 3/10 and surfaced 4 fail-OPEN holes (nested option arrays truncating the parse, decoy channels, comment/string masking, non-`.ts` channels) + smoke/validate bugs — all closed and regression-locked (16 → 26 tests; the exact attack strings are now regression tests).
