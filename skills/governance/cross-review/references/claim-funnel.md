# Claim ledger → blinded debate → independent refuter

Use for load-bearing empirical/literature claims in `autoreview`, `peer-review`
and knowledge-tier `cross-review`. For code findings, a concrete settling
observation is still required, but this three-agent funnel applies only when the
finding depends on empirical claims. Keep the existing severity, score, hash
binding and round budget. A funnel pass is a structural receipt, not approval.

1. Pin the artifact hash and primary evidence (raw data, figures, source lines,
   instrument outputs), with access limits. Extract every primary-source claim
   in scope, including inconvenient ones:

   `id | claim | what_supports_it | whats_missing | status`

   `status` is exactly `established | contested | untested`. Established means
   supported within the stated conditions, never universally proven. Use an
   explicit "none identified within scope" for a missing-evidence cell, not a
   blank. Keep the final ledger separate from the artifact so it does not change
   the hash under review.
2. Dispatch a skeptic and a believer independently with **no inherited main
   thread context**. Give both the same primary material and neutral claim
   questions. Do not send the writer's ledger statuses, interpretation, drift
   conclusions, intended answer or the other agent's output. Use the host's
   fresh-context mechanism (for example `fork_turns="none"`), not a role label
   in the writer's thread. Each returns:

   `claim_id | reading | evidence | settling_observation | disposition`

   Every objection **and defense** names one concrete test or observation and
   the result that would falsify **its own** reading. "Run more tests" is not a
   settling observation. A believer's defense is held to the same standard as
   a skeptic's objection. No findings is valid if reviewed claims and raw sources
   read are explicit; do not invent an objection to populate a table.
3. A third, distinct fresh-context refuter reads the primary figures/data
   directly and tries to break each surviving claim. It may receive the two
   completed readings after their independent return, but never the writer's
   intended verdict. It returns the same finding fields. If raw sources cannot
   be read, record the gap; do not substitute the debate summary for evidence.
   All three receipts explicitly cover the same ledger claim IDs, including a
   claim the refuter judges already defeated. Preserve each side's output.
4. Reconcile from observed evidence: keep, narrow, contest or mark untested.
   The writer re-runs material observations; a proposed settling observation
   is **not** a completed test. Missing controls yield `not_detected` or
   `inconclusive_no_positive_control`, never refutation. An untested critical
   claim keeps readiness provisional/blocked under the caller's rubric.

## Packet and gate

`cross-review claim-packet packet.json` (or `python3 scripts/review_packet.py
packet.json`) exits 0 for a structurally complete packet, 2 for missing/invalid
fields. Validate before scoring; retain stdout and dispatch IDs next to the
review ledger. It cannot attest to isolation, completeness of extraction,
truth of references or actual source reads. Inspect host dispatch receipts and
raw evidence before accepting those claims. Failure leaves the claim review
incomplete and cannot be hidden by a high rubric score.

```json
{
  "artifact_hash": "sha256:actual-artifact-hash",
  "primary_sources": ["data/run.json#measurement-1"],
  "claims": [{"id": "c1", "claim": "the boundary held in run 1",
    "what_supports_it": "data/run.json#denial",
    "whats_missing": "positive-control receipt", "status": "untested"}],
  "skeptic": {"dispatch_id": "host-task-1", "fresh_context": true,
    "artifact_hash": "sha256:actual-artifact-hash", "reviewed_claim_ids": ["c1"],
    "raw_sources_read": ["data/run.json#measurement-1"], "findings": [{
      "claim_id": "c1", "reading": "the process may never have started",
      "evidence": "data/run.json has no liveness record",
      "settling_observation": "A same-run successful allowed write would falsify the dead-process reading",
      "disposition": "open"}]},
  "believer": {"dispatch_id": "host-task-2", "fresh_context": true,
    "artifact_hash": "sha256:actual-artifact-hash", "reviewed_claim_ids": ["c1"],
    "raw_sources_read": ["data/run.json#measurement-1"], "findings": []},
  "refuter": {"dispatch_id": "host-task-3", "fresh_context": true,
    "artifact_hash": "sha256:actual-artifact-hash", "reviewed_claim_ids": ["c1"],
    "raw_sources_read": ["data/run.json#measurement-1"], "findings": []}
}
```

`findings: []` is a receipt of no findings, not an implicit defense. Any actual
argument, including a defense, belongs in a finding row with its settling
observation. When the host cannot isolate agents, disclose that the funnel did
not run; retain the ledger and its unresolved claims without claiming a pass.

## Peer-review adapter

Load `peer-review`'s original review prompt for domain criteria. Before its
researcher/reviewer synthesis, apply steps 1–4 here to empirical claims. Provide
its synthesizer the validated packet and unresolved claims; do not replace its
scientific rubric with P20's code score. This composes with a third-party skill
without editing installed copies or depending on their private directory layout.

Origin: owner-requested adaptation of Ginkgo's captured 2026-11-17 campaign
prompt (workspace PR 1321): blinded skeptical/forward groups followed by
independent verifiers, and explicit readout schemas. The stored SPA symbol
names differ from the intake's nZ–qZ labels; those labels and the specific
10 mM artifact assertion were not verified and are not premises of this rule.
