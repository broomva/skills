# PLANS.md

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
- Key outputs: 56 tests passed; a live 30-day Claude CodexBar comparison
  matched tokens and cost exactly with no CodexBar runtime dependency. The
  live Antigravity probe returned four quota windows without identity leakage
  or token/cost fabrication. A self-contained HTML dashboard renders the same
  schema with no remote assets or executable scripts. The optional parity
  command is checked in but intentionally not run in CI; strict skillify and
  P20 are rerun after every backend-contract change.
- Follow-up tasks: refresh the versioned rate card when provider prices or model
  identifiers change; re-run frozen-corpus parity when CodexBar's lineage rules change.
