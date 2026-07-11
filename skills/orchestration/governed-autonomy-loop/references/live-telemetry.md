# Live telemetry — keeping the skill grounded in running instances

A skill that freezes at authoring time throws away its instances' lived
experience. A governed autonomy loop writes an append-only `loop-log.jsonl` of
every decision it makes — that log is the ground truth of what the controller
actually does. `scripts/mine_loop_log.py` turns it back into knowledge, so the
skill keeps learning from live loops instead of paraphrasing a design doc.

## What the reference loops actually do (mined, not guessed)

Two production instances (broomva): the Mac ticket-dispatch governor (721 records)
and the VPS Life-governor (1,115 records) — **1,836 real decisions**. The shape:

| decision | share | what it means |
|---|---|---|
| **`reconcile_skip`** | **~65%** | the governor deciding NOT to close a unit — the dominant behavior |
| `label_escalate` | ~10% | trust-bounded triage declined → digest row, no label |
| tick_fire / runner_exit / run_summary / sweep_stale | ~20% | bookkeeping + cadence |
| `dispatch` / `resume` / `stall` / `wip_full` | the rest | the "dramatic" decisions the handoff narrated — a small minority |

The lesson that reshaped the controller (`runner-prompt.template.md` Step A):
**reconcile is mostly the decision NOT to close.** The scenario evals were
originally seeded from the handoff's narration of the *rare* resume/merge/defer
decisions; mining showed the *common* case is reconcile-skip classification —
now enumerated as a first-class taxonomy.

### The observed `reconcile_skip` taxonomy (`loop_state.RECONCILE_SKIP_REASONS`)

`no_pr` (1,195 — ~62% of everything) · `open_pr` (48) · `recently_active` (47) ·
`epic_in_progress` (5) · `phases_open` (1) · `arc_live` (1). Every one appears in
Step A's table; the skill's contract vocabulary covers all six.

### The observed `resume_skip` taxonomy

`complete` (19) · `no_status` (8) · `no_session_id` (2) · `busy` (1) — all already
in `loop_state.RESUME_SKIP_REASONS`. (Live counts drift as the loops append; these
are a snapshot.)

## The drift check (the skill-self-evolution hook)

`mine_loop_log.py` cross-checks every **skip-action** reason (`reconcile_skip` /
`resume_skip` — the actions whose `reason` is a controlled vocabulary) against the
skill's contract and **exits 3 if a live loop emits a skip reason the skill does
not know**. Run against both reference loops today: **✓ no drift — every skip reason
is in the contract.** That is the empirical validation that the SKIP taxonomies
match reality, and the mechanism that catches the moment reality moves ahead.

**Scope, precisely:** "no drift" is a claim about the skip-reason *vocabularies*,
not about the whole log. Other actions carry a FREE-TEXT `reason` by design —
`label_apply`'s eligibility rationale is derived from the untrusted unit body — so
those are NOT vocab-checked (every one would read as "unknown"); they are handled by
**redaction** instead (whitelist-validated out of every report/fixture). Two
independent guarantees: drift = *the skip vocab is complete*; redaction = *no free
text is committable*. Do not conflate them.

## How to keep a loop's learnings flowing back

```sh
# Local instance:
python3 scripts/mine_loop_log.py taxonomy $GAL_STATE_DIR/loop-log.jsonl

# Remote instance (stream over ssh — no raw log leaves the host except the redacted report):
ssh host 'cat ~/.config/…/loop-log.jsonl' | python3 scripts/mine_loop_log.py taxonomy -

# Ranked, redacted decision fixtures to ground new scenario evals:
python3 scripts/mine_loop_log.py fixtures $GAL_STATE_DIR/loop-log.jsonl

# Gate a cron/CI on drift (exit 3 = the loop learned a reason the skill should adopt):
python3 scripts/mine_loop_log.py taxonomy $LOG || echo "drift — update loop_state + Step A"
```

**Redaction guarantee**: reports + fixtures carry only controlled fields (action,
reason, unit id, artifact number, integer ages) — never unit titles/bodies/free
text (invariant 3: log free text is untrusted DATA). A mined report is safe to
commit; a raw `loop-log.jsonl` is not (and never is committed).

## The loop this closes

This is the skill applying its own thesis to itself. The governor senses its plant
(the work queue) and adapts; `mine_loop_log.py` lets the *skill* sense its plant
(its running instances) and adapt — sense → distill → fold-into-contract →
re-sense. It composes with the workspace's skill-self-evolution discipline
(`research/entities/concept/skill-self-evolution.md`): a live loop's `loop-log` is a
CAPTURED-signal source, and a drift exit is the FIX trigger.
