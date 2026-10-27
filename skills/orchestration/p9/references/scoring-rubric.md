# P9 — Failure-Classifier Scoring Rubric

This file is the **human-canonical** description of P9's CI-failure classifier.
The Python equivalent lives in `_builtin_rubric()` inside `scripts/p9.py`. A
unit test asserts the two stay in sync — adding an entry here without
updating the code (or vice versa) fails CI.

## How the classifier works

For each failure type below, the classifier searches the failure log for any
of the listed **detection signatures** (regexes). If at least one matches,
the entry's score is `0.7 + 0.1 × (extra_matches)`, capped at `1.0`. Among
all matching entries, the highest-scoring one wins. If its score is below
the entry's `confidence_floor` (default `0.7`), the result drops to
`unclassified` and the failure is **escalated** rather than auto-healed.

## Cardinal rule

The classifier is **narrow on purpose**. False positives that "almost"
match would burn heal attempts on the wrong fix. Prefer escalation to
heal-by-guess.

---

## Failure types

### 1. `lint`

**What it catches:** non-zero exits from biome, eslint, clippy, or generic
"lint" markers in `::error` annotations.

**Detection signatures (any match → candidate):**
- `biome\s+(check|lint).*(found|error)` (case-insensitive)
- `eslint.*\d+\s+(error|problem)`
- `clippy.*::error`
- `::error.*lint`

**Heal command:** `bun run lint:fix` (project-specific; configurable per
repo via `.control/policy.yaml` overrides — TBD in PR 3).

**Idempotent:** yes — running the lint fix twice leaves the same result.

---

### 2. `format`

**What it catches:** prettier/rustfmt drift.

**Detection signatures:**
- `prettier.*--check.*would reformat`
- `rustfmt.*Diff in`
- `would reformat`

**Heal command:** `bun run format`.

**Idempotent:** yes.

---

### 3. `type`

**What it catches:** TypeScript/Rust type errors.

**Detection signatures:**
- `tsc.*error TS\d+`
- `cargo check.*error\[E\d+\]`
- `type error.*at\s+[\w./]+:\d+`

**Heal command:** **none** — type errors require human reasoning.
Escalates on first occurrence.

**Idempotent:** N/A.

---

### 4. `test_flaky`

**What it catches:** tests that fail intermittently. Detected primarily by
**signature history** (same test, same line, passed→failed→passed within
the last N runs), not log-text match. The textual pattern below exists only
as a fallback recognizer.

**Detection signatures:**
- `^\s*FAIL\s+` (multiline; weak signal)

**Heal command:** `gh run rerun --failed`.

**Idempotent:** yes (re-running is safe).

**Confidence floor:** **0.9** (higher than default 0.7) — only confident if
history confirms flakiness. Otherwise drops to `unclassified` so we don't
mask real regressions.

---

### 5. `codegen_drift`

**What it catches:** generated files (graphql, prisma, openapi, etc.) out
of sync with their source schema.

**Detection signatures:**
- `(generated|codegen).*(out of (date|sync)|stale)`
- `schema mismatch`
- `graphql codegen.*diff`

**Heal command:** `bun run codegen` (project-specific).

**Idempotent:** yes.

---

### 6. `import_missing`

**What it catches:** `Cannot find module 'X'` and equivalents.

**Detection signatures:**
- `Cannot find module ['"]([^'"]+)['"]`
- `unresolved import\s+\`([^`]+)\``
- `Module not found`

**Heal command:** **none** in v1 — automated dependency installation has
high blast radius (which package version? which lockfile?). Escalate.

**Idempotent:** N/A in v1.

---

### 7. `runner_admission_timeout`

**What it catches:** a job that never ran. A self-hosted runner's job-start
hook waits for host admission (for example a single shared heavy-job lease),
times out, and exits 75 (EX_TEMPFAIL). The check shows red, but no step of the
PR was executed; the following steps are reported as skipped.

**Detection signatures (both required, floor `0.75`):**
- `##\[group\]Run '[^'\n]*/job-start\.sh'` (the runner invoking its own hook,
  not any line that names the file)
- `##\[error\]Process completed with exit code 75\b`

One signature alone scores 0.7, stays below the floor, and escalates. Two
matches score 0.8.

**Heal command:** `gh run rerun {run_id} --failed`, once per failing run.

- Live mode reads the run ids from the PR's own failing checks (`gh pr checks
  --json bucket,link`). Only links into the PR's repo's Actions count.
- Each failing run is classified on its own. The PR heals only when every
  failing run is this type; one run with a real error escalates the PR.
- With `--log-file` (or `-` for stdin), pass `--run-id`. Without a run id the
  heal refuses.
- `--apply` also needs the type in the policy's
  `ci_heal.classified_failure_types`.
- The caller decides *when*: do not re-run while the host's admission gate is
  red or a host hold is active. The re-run would queue on the same lease.

**Idempotent:** safe to repeat, but not free. Each re-run creates a new run
attempt and waits for host admission again.

---

### 8. `unclassified` (terminal)

Anything not matched above with confidence ≥ floor. **Always escalates** —
no heal attempt, no retry, no guessing. Creates a Linear ticket immediately.

---

## Adding a new entry

1. Add the dataclass entry in `_builtin_rubric()` (`scripts/p9.py`).
2. Add the matching section here.
3. Add a fixture log under `tests/fixtures/failures/<type>.txt`.
4. Add a unit test in `tests/test_p9_unit.py` asserting the classifier
   matches the fixture with the expected confidence.
5. The rubric-sync test will confirm the markdown and code match.

## Why not LLM-classify?

LLMs in the hot path of a CI loop are unsafe: latency, cost, and
non-determinism. Classifier here is **pure regex on logs** — fast,
predictable, auditable. The agent's intelligence belongs in the
*evaluator* (deciding whether the heal worked), not the classifier
(detecting which kind of failure happened).
