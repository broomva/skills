# Changelog

All notable changes to `skillify` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-06-28

Close the gate's blind spot — **contract honesty**.

- **New required step 1c — reference integrity.** The gate now FAILs a skill whose
  `SKILL.md` / `skill.json` / `templates/*.yaml` reference a `scripts/`/`references/`/
  `assets/`/`templates/` file that doesn't exist and isn't marked Planned. Fenced
  example blocks are excluded; scaffold-template outputs (`assets/templates/…`) count
  as satisfied. Motivated by BRO-1575: 5 skills shipped advertising scripts/templates
  that were never written — all passing the old gate. Running 1c across the monorepo
  surfaced 4 more genuine broken-contract skills.
- **Step 3 now recognizes bash test suites** (`*.test.sh` with `ok()`/`fail()` helpers
  or `PASS`/`FAIL` accounting), closing a false-negative where a real shell test
  battery (e.g. cross-review's 8-test suite) read as "no tests".
- +9 unit tests (49 total).

## [0.2.0] — 2026-06-06

Full lifecycle — publish + install-dogfood, not just static authoring. skillify
v0.1 gated *files on disk*; v0.2 gates *installability from the registry*, and
the skill itself moves to its canonical home in the `broomva/skills` monorepo.

### Added

- **Pipeline steps 9–11** in `SKILL.md`: **Publish** under the `broomva/skills`
  monorepo (`skills/<name>/`, not a standalone repo — the deprecated pattern) and
  **Dogfood the install (skills.sh E2E)** — `npx skills add … --list` parse →
  real install → confirm `~/.claude/skills/<name>/` + next-session discovery.
- **`skillify_check.py` skills.sh installability checks:**
  - Step 1 now rejects the **silent frontmatter gotcha** — a multi-quoted-string
    YAML list item (`- "a", "b"`) that makes the skills.sh parser discard the
    whole frontmatter (`No valid skills found`). Deterministic, no network.
  - **`--skills-sh <repo>`** makes step 9 a real install-verify: runs
    `npx skills add <repo> --list` and requires the skill is listed.
- 4 new tests (35 total). Canonical install is now
  `npx skills add broomva/skills --skill skillify`.

### Changed

- Home moved from standalone `broomva/skillify` → `broomva/skills/skills/skillify/`
  (via `bstack skills graduate`); the standalone is a redirect stub.

## [0.1.1] — 2026-06-05

P20 cross-review hardening. A fresh-context adversarial review (score 3/10,
FIX-FIRST) found the gate checked *presence, not correctness* — its central
false-PASS risk. The doctor now **executes** what it cheaply can:

### Fixed

- **Empty / garbage test files no longer pass step 3** — a test file must be
  non-empty AND contain a real test construct (`def test_`, `assert`, `it(`,
  `test(`, `describe(`, `@pytest`); `--run-tests` actually invokes pytest.
- **Syntax-broken scripts fail step 2** — `py_compile` (.py), `bash -n` (.sh),
  `node --check` (.mjs/.js/.ts when node present).
- **`.test.` is extension-scoped** — `fixtures.test.json` is no longer counted
  as a test (only `*.test.{py,sh,mjs,js,ts}`).
- **`latent_only: true` with code present is a contradiction → FAIL** (was an
  unconditional bypass of steps 2+3).
- **Folded/block-scalar frontmatter** (`description: >-`) parsed correctly
  (pyyaml when available; the hand-roll no longer manufactures bogus keys).
- **Step 6 requires a structured registry line** (table row / list item /
  backtick) — a bare prose mention no longer counts as "registered".
- **`--strict` without workspace paths WARNs visibly** instead of silently
  skipping the checks strict exists to enforce.
- **Recursive** `scripts/`/`tests/` discovery (nested `tests/unit/test_*.py`).
- Dogfood claim made true + accurate: repo-local gate in CI; workspace `--strict`
  gate against `roles/_index.md`.
- **Round 3 (two more P20 passes — fix the *class*, not the example):**
  (a) `--strict` without workspace path flags now FAILs (exit 1), matching the
  documented invariant — was a cosmetic WARN;
  (b) registry step 6 matches the name as a real **entry** (first token of a
  list item, or a table cell that starts with the name — markdown links handled)
  — a backticked/prose mention on a bulleted or piped line no longer registers;
  (c) `_is_real_test`: Python via AST (a `test`/`test_*` function, or a `Test*`
  class with a test method — no longer over-matches `testimony`/`Testimonials`);
  non-Python strips **string literals AND comments** before the construct scan,
  so `"it( assert"` inside a JS string is not a test. 31 regression tests total.

## [0.1.0] — 2026-06-05

Initial release. The bstack-native **skillify-as-a-verb** — distill a working
session into a tested, registered skill. Capstone of the skillify arc (BRO-1411);
originated from `/checkit` on Garry Tan's "skillify" essay (BRO-1416).

### Added

- **`SKILL.md`** — the end-of-workflow composition contract. Composes
  `look-back` (extract) → `CreateSkill` (scaffold) → latent/deterministic split
  → tests → `role-x.py eval` resolver-eval → `bstack skills audit
  --require-tests` → P20 cross-review → `bookkeeping` file. Reimplements nothing.
- **`scripts/skillify_check.py`** — the deterministic "skillify doctor". Runs the
  10-step checklist on a skill directory; PASS/WARN/SKIP/FAIL per step; exit 1 if
  a required step (SKILL.md, deterministic code unless `latent_only`, unit tests)
  is incomplete. `--strict`, `--json`, workspace-aware steps via `--roles-dir` /
  `--registry` / `--entities-dir`. Pure stdlib, zero network.
- **11 tests** (`tests/test_skillify_check.py`) — unit + CLI integration. skillify
  passes its own gate (dogfood).
