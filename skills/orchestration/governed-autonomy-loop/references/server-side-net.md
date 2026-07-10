# The server-side net — the mandatory checklist for autonomous irreversible acts

An autonomous loop that performs an irreversible act (merge / deploy / publish)
is only safe with an **always-runs aggregate gate the host enforces**, not the
agent. This is the hardest-won lesson of the reference arc (BRO-1833 P6): the
agent's own reasoning can be wrong; the server-side check is the backstop that
holds when it is. Ship this before you arm any loop whose arcs self-act.

## Why an aggregate gate (not "require the CI jobs")

Path-filtered CI (`paths-ignore: docs/**, **/*.md`) SKIPS on a docs-only PR. If
the branch ruleset requires the individual CI jobs, GitHub leaves each skipped job
in a permanent "Expected" state and blocks the PR **forever** — the
skipped-but-required footgun. The fix is one job that runs on EVERY PR (no filter)
and passes iff every OTHER check concluded green-or-skipped. That job — and only
that job — is what the ruleset requires. `templates/merge-gate.yml` is the
reference implementation (native `gh api`, no third-party actions on the
merge-critical path).

## The checklist (each item is load-bearing)

- [ ] **Ship the aggregate gate** — copy `templates/merge-gate.yml` to
      `.github/workflows/`. It must: run unfiltered on every PR; pass iff no other
      check is in a blocking conclusion; tolerate the zero-checks (path-filtered)
      case after a short grace.
- [ ] **Prove it green BEFORE requiring it** — open one real PR, watch the gate go
      green, THEN add it to the ruleset. Requiring a gate that has never passed
      bricks the branch.
- [ ] **Require the gate in a branch ruleset** — require: the "Merge Gate" status
      check + a pull request + non-fast-forward. Nothing else.
- [ ] **NO admin bypass** — `enforce_admins` / "do not allow bypass". The arc runs
      as an admin identity; an admin-bypassable ruleset is not a gate for it. This
      is the single most common way the net is silently defeated.
- [ ] **Confirm the arc-side gate too** — the arc's own pre-act step (adversarial
      review ≥ anti-slop bar + policy check) is the FIRST layer; the server-side
      gate is the backstop. Both, not either.
- [ ] **Verify the merge lifecycle defers to policy** — the arc self-acts via the
      standard pipeline (reference: `p9 auto-merge`, `--repo` explicit); merge
      authorization stays with `.control/policy.yaml`, not the arc's judgment.

## Ruleset recipe (GitHub, reference)

```
Branch ruleset on `main`:
  - Require a pull request before merging
  - Require status checks to pass:  "Merge Gate"   (the aggregate job's name)
  - Block force pushes (non-fast-forward)
  - Do NOT allow bypass (enforce for admins / no bypass actors)
```

Reference rulesets from the arc: life ruleset 18779692, workspace ruleset
18780729 (`core/life/.github/workflows/merge-gate.yml` is the exact source of
`templates/merge-gate.yml`).

## The generalization

Merge is one irreversible act. For a **deploy** loop the aggregate gate is a
"deploy-readiness" check (smoke green + migration dry-run clean); for a **publish**
loop it is a "publish-readiness" check (artifact signed + provenance attested).
The shape is invariant — an always-runs, host-enforced, no-bypass aggregate gate
that the arc cannot satisfy by asserting; only by the independent check passing.
