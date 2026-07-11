# Changelog — governed-autonomy-loop

## 0.2.0 — 2026-07-10

Ground the skill in the two reference production loops' operational history (Mac
ticket-dispatch 721 records + VPS Life-governor 1,115 records = 1,836 live
decisions), mined via the new `scripts/mine_loop_log.py`.

- **`mine_loop_log.py`** (tested, +8 tests): turns any running loop's
  `loop-log.jsonl` into a taxonomy report + ranked, redacted decision fixtures, and
  a **drift check** — exits 3 if a live loop emits a reason the skill's contract does
  not know (the skill-self-evolution hook). Both reference loops mine to **✓ no
  drift** — empirical proof the extracted contract matches reality.
- **`loop_state.RECONCILE_SKIP_REASONS`** promoted to a first-class contract
  (`no_pr / open_pr / recently_active / arc_live / epic_in_progress / phases_open`),
  the observed "why NOT close" vocabulary.
- **Controller Step A** now enumerates that taxonomy — grounding the single most
  common governor decision (reconcile_skip is ~65% of all live records), which the
  handoff-seeded prose under-specified.
- **Scenario evals re-grounded**: +3 live-drawn scenarios (`reconcile-skip-no-pr`,
  `reconcile-skip-arc-live`, `complete-arc-with-stuck-pr`) with `provenance` citing
  the actual records (e.g. VPS BRO-1483's `complete`-arc-with-stuck-PR interplay:
  18 resume_skip/complete + 6 stall records) instead of handoff paraphrase.
- **`references/live-telemetry.md`**: the observed taxonomy, redaction guarantee,
  and the keep-learning workflow (sense → distill → fold-into-contract → re-sense).

## 0.1.0 — 2026-07-10

Initial release. Skillified from the broomva ticket-dispatch governor (BRO-1740 +
BRO-1833 P1–P6) via `/skillify` (BRO-1849).

- **Deterministic core** (extracted from the reference prose, tested):
  `tick.sh` portable scheduler, `loop_state.py` (in-flight fold, P5 reseed gate,
  busy-guard, arc-status contract), `validate_config.py` (fail-closed kill switch /
  DRY_RUN / num_or / partition guard), `denylist_check.py` (tracker write-surface
  coverage). 65 unit + integration tests + an E2E smoke.
- **Latent controller**: `runner-prompt.template.md` — the invariant spine factored
  from the Linear/merge specifics into four adapter slots.
- **Adapter contracts**: tracker / irreversible-act + enforcement / runtime /
  partition (`references/adapters.md`).
- **Server-side net**: `merge-gate.yml` aggregate gate + ruleset recipe
  (no-admin-bypass, prove-green-before-requiring).
- Fixed a watchdog fd-inheritance bug found while extracting the scheduler: the
  wall-clock watchdog subshell held a captured-pipe parent open via its sleep; now
  it redirects off the caller's stdout and reaps its own sleep on TERM.
- Shipped denylist adapter covers `create_initiative_label` (the reference tick.sh
  DRY_FLAGS omitted it — a real fail-open the coverage check catches).
