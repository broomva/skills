# PLANS.md

## role-x reflex router v1, behind `ROLE_X_OUTPUT=reflex` (BRO-2674)

Status: in progress on `feat/role-x-reflex-router`; eval paused for the rate-limit window (resets 13:50 -05). Owner decision 2026-09-30: turn
role-x into something that raises adherence to bstack's primitives and skills, as its
quality-bar p9 line already does, across all of them.

### Evidence it starts from

- ctx_ablation (#248, #251): concrete action lines move behaviour. role-x's p9 line took
  p9 watch to 6/9 against 0/9 bare, and MEMORY.md's action rules carried memory's lift.
- role-x's task-entity list does not: 0–7% opened in the evals, 0.70% in production.
- role-x is 23.8% of all injected bytes, about 1k tokens per turn.

### Scope and constraints

- Default unchanged. `ROLE_X_OUTPUT` unset means today's intake block (`legacy`);
  `reflex` is the router; `shadow` logs it without injecting; `qbar` is the lens block cut
  to its quality bar (an eval arm #251 asked for). `ROLE_X_MODE`, the brief's name, is an
  alias. The hook is registered in write-gated settings, so the switch is an env flag.
- Catalog `references/reflexes.yaml`: trigger clauses → one factual, command-naming line
  → the source that states the rule. Primitive reflexes from the workspace AGENTS.md
  §P1–P20, memory action rules, and one line per installed skill with
  `evals/prompts.json`.
- State predicates first, from one `git status --porcelain=v2 --branch`, a reflog tail,
  and ctx-core's `board.json` cache (never its log). Then lexical prompt routing, then a
  `ROLE_X_JEV` narrowing seam, `off` in v1. No model classifier in v1.
- Output ≤3 lines and ≤150 tokens, no persona lines, no entity list; byte count logged.
  Any error prints nothing.

### Milestones

1. [x] Catalog + router + role-x wiring + tests (predicates ±, catalog/source, budget,
   fail-open, mutation check). Names aligned with the workspace spec
   (`2026-09-30-reflex-router-and-ontology-ranked-context.html`, a74109b8f):
   `ROLE_X_OUTPUT` (alias `ROLE_X_MODE`), `[bstack reflexes]`, dotted ids, `status`,
   `signature`, `ROLE_X_JEV` seam, `role-x reflexes route --evals`.
2. [x] ctx_ablation: `reflex` and `qbar` arms (aliases `rolex-reflex`, `rolex-qbar`),
   `home_contains` grader, 7 held-out tasks (`tasks/reflex-heldout.json`).
3. [ ] Sonnet run: calibrate held-out, then bare / rolex / qbar / reflex, arms one at a
   time, jobs ≤2. Estimate ≈ $35 notional (pilot 132 trials ≈ $20 at #251's
   $0.15/trial; held-out ≤ 21 + 84 trials ≈ $15). Checkpoint 11:21 -05: stopped by
   the 0.85 budget guard at 2/21 calibration trials, five-hour window at 0.88 (fleet
   load). It resets 13:50 -05 (18:50Z); resume with `~/.cache/ctx-ablation/reflex-chain.sh`.
4. [ ] Results doc, PR, P20 (B + C strata, read-only), `p20-record`, `gate-check`,
   pinned merge. The flag stays default-off; the owner decides the flip.

### Verification

`pytest skills/orchestration/role-x/tests`, `pytest tests/skill_evals/test_ctx_ablation.py`,
`python3 scripts/skill_evals/ctx_ablation/run.py validate --deep`.

## Context evals, layer 2: the causal context-ablation harness

Status: pilot v3 done; PR #248 in review round 3 (branch `feat/context-ablation-evals`). Layer 1, the observational
context ledger in bstack's leverage sensor, is a separate session's work. The owner
decided on 2026-09-29 to build both layers.

### Objective

Measure whether the context we inject makes sessions behave better per token:
role-x intake, the ctx-core brief, and MEMORY.md. Also measure whether it triggers
the right retrieval reflexes, and how far it compresses.

### Scope and constraints

- `scripts/skill_evals/ctx_ablation/`, a sibling of `runner.py` that imports its
  jail, argv contract, stream parser and interval math.
- Arms are explicit `--settings` files under a jailed HOME:
  `bare, memory, rolex, ctx, all, rolex-top2`. `~/.claude/settings.json` is never
  touched.
- State is constant across arms. Only the injection varies.
- Tasks come from real turns and memory feedback files. Graders assert on tool
  inputs, end state and fact tokens, never on narration.
- Control-absent rule: every task must fail in the bare arm in a calibration run,
  or it is dropped as vacuous.
- role-x's cap was a constant, so the compression arm uses a new env override,
  `ROLE_X_TASK_ENTITY_TOP_N`, with tests.

### Milestones

1. [x] Harness: arms, fixture, stubs (gh, trash, p9, paseo, Paseo MCP, case guard),
   graders, metrics and CLI. 137 tests; the mutants of every guard are killed.
2. [x] 16 candidate tasks. Each fails a null run and its control-removed
   exemplar, and passes its informed exemplar.
3. [x] Preflight on the real corpus. The live canary shows each of the six arms
   sees exactly its own injections.
4. [x] Calibrate 16 candidates × 3 trials in the bare arm: 13 retained, 3
   vacuous (`tasks/pilot.calibration.json`).
5. [x] Pilot: 10 retained tasks × 6 arms × 3 trials, 180 trials
   (`ctx_ablation/PILOT.md`). v1 was superseded after P20 round 1 (false fails, a
   real-Trash side effect), and v2 after round 2 (a vacuous check, a weak memory proof,
   a guard that could not prove it ran). v3 is the result: 180 trials, 2 void, run on 8e8b5fa.
   The later commits add checks that change no v3 outcome.
6. [ ] Scale to 30 tasks: not run. The owner held this session to the pilot
   because of the shared subscription limit, and the pilot is floor-limited on
   haiku. The next measurement is sonnet on the 13 retained tasks; PILOT.md has
   the estimate.

### Verification

`python3 scripts/skill_evals/ctx_ablation/run.py validate --deep`, and
`pytest tests/skill_evals/test_ctx_ablation.py`.

## ctx-core phase 1: the read-only shared board

Status: final review (PR broomva/skills#246), narrowed by the owner after the
fresh round (B 6/10, C 7/10).

Branch: `feat/ctx-core-phase1`

Design: broomva/workspace#825, `docs/specs/2026-09-29-shared-context-core.html`
(round 7), revised by the phase-0 spike
(`~/.config/broomva/fleet/ctx-spike-20260929/SPIKE-REPORT.md`).

### Objective

Ship `skills/orchestration/ctx-core/`:
- `ctx.py`, the single writer and reader of a per-scope `events.jsonl`, with a
  cached `board.json` fold, `ctx board [--json] [--rebuild]`, `ctx doctor` and
  `ctx doctor --unscoped`;
- the SessionStart, Stop and StopFailure hook entry, behind the `ctx-hook.sh`
  missing-file guard.

The hooks ship as scripts only. Registering them is an owner step.

### Constraints

- Coordination only, not a security boundary (owner decision 2026-09-29).
- Hooks: under 200 ms of wall time, exit 0 always, no output on any failure,
  and the lock held only for the append.
- Structured fields only (the owner's narrowing). No free text is stored, and
  one linear guard covers what is.
- A repo with no scope is a silent no-op. Nothing under `crm/` is written. The
  `sri` and `broomva` stores never cross.
- Never edit `~/.claude/settings.json`, `~/broomva/.claude/settings.json` or
  any `hooks.json`.

### Definitions

- **Live:** an event within the last 6 h and no `session.died` since the
  session's last other event. The same text is in SKILL.md and in
  `ctx.LIVE_DEFINITION`. `session.died` is the only terminal event; Stop fires
  every turn.
- **Board cap:** a hook will not parse a `board.json` over 2 MiB. At 550–720
  bytes a row, that is about 2,900–3,800 sessions, roughly 4 weeks at ~117 a
  day. The recovery path:
  1. `ctx board --rebuild`, for a stale or hand-edited cache;
  2. to shrink the board, move `events.jsonl` aside by hand, then run `ctx
     board --rebuild`.

  The scripted archive procedure is phase 2.

### Out of scope

- Phase 2 of the design:
  - the mailbox, deltas and asyncRewake;
  - retention and the archive procedure (`ctx doctor` says "no retention in
    phase 1");
  - splitting died from failed, and reset-time extraction.
- The role gate and the owner CLI are **not** later work. The design cut them
  (round 7). The boundary is GitHub rulesets and the server-side merge gate.

### Exit criterion (phase 1)

- One side is the board's live rows (the definition above).
- The other side is the `list_agents(cwd:"/")` agents in scope whose
  transcript was modified in the same 6 h.
- It passes when at least 95% of each set appears in the other, and every
  difference is listed with its reason.
- One expected reason for a difference is a single turn longer than 6 h.

### Milestones

- [x] `ctx.py` + `ctx_hook.py` + `ctx-hook.sh`, stdlib only, Python 3.9+.
- [x] Tests: scope isolation, lock contention (including the lock hold),
  rebuild determinism, fail-open, the guard (free text, and linear time at
  10 KB and 1 MB), the hook deadline, and the wrapper. Plus a mutation check.
- [x] SKILL.md with the owner's registration snippet (via the wrapper); catalog
  rows; CI workflow.
- [ ] Cross-Review (P20), final round, then p9 gate-check and a merge pinned to
  the head, or BLOCKED.
- [x] Local dogfood: synthetic hook JSON into each script, and the board
  rebuilds.

## Legal-readiness skill

Status: in progress

Branch: `feat/legal-readiness-skill`

Tracking: `broomva/skills#153`

### Objective

Generalize the 2026-08-09 SaaS legal/security adversarial audit into a reusable,
tested skill that configures evidence and controls while preserving legal,
entity, tax, filing, contract, and counsel boundaries.

### Dependency chain

- Upstream: corrected claim ledger, jurisdiction predicates, lifecycle receipts,
  skillify packaging contract, official-source freshness requirement.
- Implementation: `skills/governance/legal-readiness/` workflow, stdlib validator
  and probe, template, references, tests, and evals.
- Registration: README catalog, path-filtered CI, workspace role/eval and KG
  provenance in a companion PR.
- Verification: pytest, example rejection/acceptance, strict skillify, role-x
  resolver eval, bstack test audit, skills.sh clean install, Cross-Review (P20).

### Non-goals

- No legal advice, compliance opinion, entity formation, tax/registry filing,
  contract execution, or fabricated operator/vendor facts.
- No universal jurisdiction checklist and no assertion that a passing schema
  proves legal sufficiency.

### Milestones

- [x] Define latent/deterministic boundary and evidence contract.
- [x] Implement skill, validator, probe, template, and tests.
- [x] Register role/eval and KG provenance in the companion workspace change.
- [x] Dogfood local discovery, validator/probe, strict skillify, role resolver,
  and isolated bstack test audit.
- [x] Pass Cross-Review (P20).
- [ ] Pass CI, merge, install, and cleanup.

Use this file for multi-step work where durable context matters.

## Objective

- Outcome: Ship a tested `audit-harness-usage` skill and stdlib CLI that reads
  Claude Code, Codex CLI, Gemini CLI, and exported Cursor usage traces without
  reading prompt bodies into its output, and reports Google Antigravity quota
  windows as a distinct non-token provider surface.
- Why it matters: Token totals are currently split across incompatible local
  schemas, and API-equivalent estimates are easily mistaken for actual bills.
- Non-goals: Reconstruct prompts, scrape Cursor credentials, or claim that a
  subscription was billed at public API list price.

## Constraints

- Runtime/tooling constraints: Python 3.11+, standard library only at runtime;
  no CodexBar runtime dependency.
- Security/compliance constraints: Read-only scanning; no prompt/tool content
  in reports; Antigravity requests pinned to localhost; no credential refresh;
  unknown prices remain visibly unpriced.
- Performance/reliability constraints: Stream JSONL, use file mtime prefiltering,
  tolerate malformed rows, and deduplicate Claude streaming/fork copies.

## Context Snapshot

- Relevant files/modules: `skills/tooling/audit-harness-usage/`, README catalog,
  one path-filtered GitHub Actions workflow, Redfish role lens/provenance.
- Existing commands/workflows: `skillify_check.py --strict --run-tests`,
  `bstack skills audit --require-tests`, role-x resolver eval.
- Known risks: Vendor schemas and prices drift; Codex forked sessions lack a
  universally stable event identifier; Cursor generally needs an export/API
  response rather than a trustworthy local trace; Antigravity exposes quota
  fractions but no supported trace-level token or cost history.

## Execution Plan

1. Implement normalized adapters and versioned pricing.
   - Expected output: CLI, schema reference, price snapshot with sources.
   - Verification: Synthetic fixtures for every provider and cost component.
2. Package the operational skill and resolver lens.
   - Expected output: `SKILL.md`, catalog/CI registration, candidate lens/eval.
   - Verification: skill validator, resolver eval, strict skillify check.
3. Dogfood on redacted local traces and compare with CodexBar.
   - Expected output: Aggregate receipt and documented reconciliation limits.
   - Verification: pytest, CLI JSON schema checks, CodexBar comparison, P20.

## Checkpoints

- [x] Baseline captured
- [x] Implementation complete
- [x] Static checks passed
- [x] Tests passed
- [x] Docs updated

## Decision Log

- Date: 2026-08-05
  - Decision: Keep mechanical accounting deterministic and put interpretive
    recommendations in the skill procedure.
  - Reason: Reproducible totals and costs require inspectable arithmetic;
    anomaly interpretation benefits from model judgment.
  - Alternatives considered: A model-only log review (not reproducible) and a
    universal token formula (wrong across provider schemas).
- Date: 2026-08-06
  - Decision: Port CodexBar v0.45's lineage accounting into the standard-library
    Python scanner and keep CodexBar strictly as a development parity oracle.
  - Reason: Fork-time parent baselines, owned suffixes, and interleaved
    watermarks provide precise local accounting without imposing an application
    or Swift runtime dependency on skill users.
  - Alternatives considered: Invoke CodexBar as a subprocess (rejected runtime
    dependency) or retain lower/upper fork bounds (unnecessarily imprecise).
- Date: 2026-08-06
  - Decision: Model Antigravity as a distinct quota-only provider and port the
    read-only CodexBar localhost probe shape without importing CodexBar.
  - Reason: Antigravity and Gemini CLI have separate storage/runtime surfaces;
    the local Antigravity service returns remaining fractions and reset times,
    not reconstructible historical token or cost records.
  - Alternatives considered: Fold the quota into Gemini CLI (semantically
    wrong) or estimate tokens/USD from percentages (unsupported fabrication).
- Date: 2026-08-06
  - Decision: Add a native, self-contained HTML projection with bounded
    evidence-backed opportunity signals, explicit unknown/no-data states,
    accessible semantics, and atomic owner-only output replacement.
  - Reason: A visual receipt makes component mix, model concentration, quotas,
    and confidence gaps easier to act on without changing accounting truth.
  - Alternatives considered: Markdown-to-HTML projection (too flat for the
    quantitative relationships) or an external dashboard dependency (not
    portable, less private).

## Final Verification

- Commands run: pytest, Python 3.12 compile, strict skillify gate, resolver eval,
  isolated bstack test audit, native CLI scans, CodexBar comparison, and P20.
- Key outputs: 64 tests passed; a live 30-day Claude CodexBar comparison
  matched tokens and cost exactly with no CodexBar runtime dependency. The
  live Antigravity probe returned four quota windows without identity leakage
  or token/cost fabrication. A self-contained HTML dashboard renders the same
  schema with no remote assets or executable scripts. The optional parity
  command is checked in but intentionally not run in CI; strict skillify and
  P20 are rerun after every backend-contract change.
- Follow-up tasks: refresh the versioned rate card when provider prices or model
  identifiers change; re-run frozen-corpus parity when CodexBar's lineage rules change.

---

## Broomva design portability refactor

Status: complete

Branch: `feat/broomva-design-skill`

Pull request: `broomva/skills#149`

### Scope

Make `broomva-design` usable across arbitrary digital products without weakening the archived source evidence or the optional agentic-work language.

### Constraints

- Keep the portable `DESIGN.md` platform-neutral.
- Keep archive-derived artifacts hash-pinned and available through `full`.
- Treat React/web components as one adapter, not the design system itself.
- Keep agentic work states, Undertow, receipts, and Maestro opt-in.
- Preserve overwrite safety, idempotence, local-reference checks, and manifest verification.

### Milestones

- [x] Rewrite the core design contract and skill routing.
- [x] Add neutral foundation and web profiles plus an agentic-work extension.
- [x] Add general product-pattern and platform-adaptation references.
- [x] Expand tests, trigger fixtures, catalogs, and workspace resolver integration.
- [x] Render and inspect non-agentic examples across themes and viewports.
- [x] Run forward testing, Cross-Review (P20), and pre-push repository checks.

### Verification

- `python3 skills/design/broomva-design/scripts/materialize.py verify-source`
- `python3 -m unittest discover -s skills/design/broomva-design/tests -v`
- `bash skills/design/broomva-design/tests/smoke.sh`
- `python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/design/broomva-design`
- Materialize every profile twice and verify it.
- Interact with and capture non-agentic commerce and content/data examples at 375px, 768px, and 1440px in light and dark themes.

---

## Bookkeeping temporal-drift warning audit

Status: implementation complete; PR #151 lifecycle pending

Branch: `feature/gh-150-temporal-drift-warnings`

Tracking: `broomva/skills#150` (GitHub fallback; the Linear connector exposes
only the unrelated Stimulus workspace)

Pull request: `broomva/skills#151`

### Objective

Add an opt-in, non-blocking `bookkeeping lint --temporal` audit that surfaces
mechanically defensible temporal drift without pretending to perform semantic
reconciliation.

### Dependency chain

- Upstream: entity YAML `updated` metadata plus dated source/body evidence;
  mutable-state labels and headings in entity markdown.
- Implementation: `skills/knowledge/bookkeeping/scripts/bookkeeping.py` lint
  helpers and CLI dispatch.
- Contract/docs: `skills/knowledge/bookkeeping/SKILL.md`, schema reference, and
  changelog.
- Verification: focused temporal fixtures, the full Bookkeeping pytest suite,
  live-graph calibration, repository checks, P20, and CI.
- Downstream: agents running `lint --all --temporal`; status/health behavior and
  existing default lint output must remain unchanged.

### Non-goals

- No automatic contradiction or supersession judgment.
- No required `valid_from`, `recorded_at`, `supersedes`, or `revision_link`
  schema fields before typed producers exist.
- No hard gate and no BM25/retrieval changes.

### Milestones

- [x] Freeze warning semantics with positive and negative tests.
- [x] Implement opt-in temporal lint helpers and CLI routing.
- [x] Calibrate on the live graph and document limits.
- [x] Run full validation and Cross-Review (P20).
- [ ] Open, watch, merge, and clean the PR lifecycle.

### Acceptance

- Existing lint output is byte-for-byte unaffected unless `--temporal` is set.
- Temporal-only findings use warning severity and do not produce a failing exit.
- Metadata drift considers only valid ISO dates on or before the audit date.
- Mutable-state detection is bounded to catalog-visible claims, headings, and
  explicit label lines rather than scanning arbitrary present-tense prose.
- Tests cover true positives, dated controls, invalid/future dates, and
  false-positive-prone language.

### Verification checkpoint — 2026-08-09

- 331 Bookkeeping pytest cases passed after repairing one pre-existing
  wall-clock-dependent retention fixture.
- 50 retrieval benchmark tests passed.
- Skill-version lint and `git diff --check` passed.
- Clean workspace calibration (`f4e04b45`): 928 pages, 96 warning-only
  findings across 91 entities; machine receipt checked in.
- Default single-file lint stayed clean while `--temporal` reproduced the
  Chronos warning and recognized corrected Lago as clean.
- Cross-Review (P20) round 1: 9/10, one evidence-artifact finding.
- Cross-Review (P20) round 2: 10/10 APPROVE after adding the JSON receipt and
  its consistency test.
- Bookkeeping replay against workspace `b1a4a662`: 931 entities frozen,
  2 unrelated design-system items would promote, no writes applied.
