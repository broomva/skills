# Changelog

All notable changes to `broomva/eve-forge` are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] — 2026-07-04

### Fixed — smoke-gate fidelity residuals (BRO-1685)
- **`smoke.py`** now strips HTML comments (`<!-- ... -->`) from the output before matching, so an echoed template/house-style comment can't false-match a required or forbidden term.
- Documented + tested that `truth.json` `forbidden` encodes **case-scoped negative constraints** — e.g. `"bloodwork"` for a non-senior patient — so a real house-style violation now fails the gate (previously smoke passed regardless of the single most business-critical rule).
- **`instructions.md` template** — added a rule: output only the finished document; never echo HTML comments / template boilerplate / house-style instructions into the deliverable.

## [1.0.1] — 2026-07-04

### Fixed — E2E dogfood (BRO-1685): the gates now run against **real** eve v0.19.0, not assumed schemas
A first forge run on a real vet-clinic packet found that 3 of 4 gates + the channel template + the smoke stage did not work as written (mock-fidelity-gap-false-green: unit-tested against synthetic fixtures the real tool never emits).
- **`validate.py`** — now strips eve's stdout banner (`☰eve v0.19.0`) before parsing, and reads the **real** schema: `diagnostics` is a dict `{errors,warnings}` (not a list), readiness is `status:"ready"` (not a boolean). Test fixtures replaced with a captured-from-real-eve object.
- **`deploy_safety.py`** — `scan_dir` now skips `node_modules`/`.eve`/`dist`, so a project-root scan no longer FAILs on the eve library's own `channels/*.ts`.
- **`references/templates/channel.ts`** — corrected to `eveChannel` from `eve/channels/eve` (was `defineChannel`, which needs routes); SKILL stage 3 now says **edit the scaffolded channel** (the scaffold already ships the right wrapper).
- **SKILL** — stage 1↔2 ordering (stage the spec outside the tenant dir; `eve init` refuses a non-empty target); `npm run typecheck` (not `pnpm`); gate on `agent/` not the project root; a **§Smoke against a locked channel** recipe (a locked channel 401s anonymous callers → authenticate via `vercel env pull` OIDC; payload field is `message`, not `input`); ground-truth standardized on `truth.json`; strip-HTML-comments instruction.
- Added `references/templates/tenant-spec.example.json` and `tests/requirements-dev.txt`.
- Validated: locked agent deployed + smoke-passed 5/5 (house-style senior-bloodwork rule respected); the deploy-safety gate blocks `none()` on a real authored channel.

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
