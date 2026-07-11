# Changelog — governed-autonomy-loop

## 0.4.0 — 2026-07-11

Cure the arc-wedge root cause with a CLOSED-LOOP backstop (BRO-1857). Two arcs in
a row (BRO-1481, BRO-1322) opened green PRs then died before writing their typed
status — because they deferred the status write to a background poll that never
fires for a headless one-shot session. Critically, the arc prompt *already forbade*
this, emphatically, citing the prior incident — and the arc violated it anyway.
That is the incantation-to-control thesis proven on the loop itself: a prose rule
is open-loop and will be violated, so the fix must be mechanical.

- **Step F derive-from-artifact self-heal**: when an arc's `arc-status.json` is
  missing, the governor no longer gives up (`no_status` → wedge). It derives state
  from the DURABLE, independent artifact (`h ⟂ U`): an open **non-draft** PR → treat
  as `awaiting_ci`, route to CI → merge/reconcile (reseeding a fresh session since
  the arc is dead). Only a draft/absent PR is a genuine wedge. Bounded by the reseed
  generation cap. This recovers the crashed-before-status case with no operator.
- **Arc-prompt execution-model note** (secondary, marginal — the rule already
  existed + failed): the arc is headless + single-turn with NO background
  re-invocation; bounded-poll = foreground sleep-loop THIS turn; else write
  `awaiting_ci`.
- +2 scenario evals (`no-status-open-pr-self-heal`, `no-status-no-pr-genuine-wedge`).

## 0.3.0 — 2026-07-11

Close the silent-block gap (BRO-1851): a dead-arc wedge that pins a WIP slot now
ESCALATES off-terminal instead of only landing in the digest. Found in production —
the VPS Life-governor silently blocked the operator for ~8h on a crashed arc
(BRO-1481) that opened its PR but died before writing its typed status.

- **`mine_loop_log.py health`** (+10 tests): a deterministic wedge detector — an
  in-flight arc that is dead (`stall`/`arc_exit`/`resume_skip:no_status|working_but_dead`)
  with no forward progress for ≥`--min-ticks` **outer** ticks (default 2) → exit 3.
  Counts OUTER ticks only, matching the governor's escalation cadence (same rule, not
  a faster any-tick alarm). A `resume_skip:complete` clears the dead signal (a
  complete arc is done-waiting-for-merge, not wedged). Validated on the live VPS log:
  flags the real BRO-1481 wedge (`resume_skip:no_status`, 3 outer ticks pinned) —
  would have paged after 2 outer ticks (~4h) instead of 8h.
- P20-hardened (round 4): `_ESCALATE_WHY` gains `wedged` (else the skill would
  redact its own governor's `wedged` records); `RECONCILE_SKIP_REASONS` gains
  `life_partition` (the drift check flagged it live on the Mac log mid-review — the
  self-evolution mechanism working in the wild).
- **Controller Step D GOVERN** now escalates a WEDGE (`why: wedged`) via the
  escalation adapter, once per episode — the case the arc-status contract can't
  self-report (a crashed arc). `WEDGE_ESCALATE_TICKS` knob (default 2).
- The escalation `why` vocab gains `wedged` alongside `needs_decision`/
  `blocked_human`/`reseed_exhausted`.

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
- P20-hardened: `reason` on `label_apply`/`dispatch_skip` is FREE TEXT (the
  eligibility rationale, derived from the untrusted unit body), not a vocab token —
  so redaction now whitelist-VALIDATES `reason`/`why`/`state` against controlled
  vocab and drops non-vocab values (both the fixture example AND the group label),
  making "safe to commit" mechanical instead of an assumption. +3 regression tests
  using the real leaked record. Drift-vs-redaction scope disambiguated in the doc.

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
