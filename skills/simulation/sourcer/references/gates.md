# The twelve gates

Twelve gates, five stages, eleven fail closed. The spec's own table is the
specification; BRO-2294's prose says thirteen and is wrong by one, and a
thirteenth invented to match a tally would be a gate that asserts nothing.

| Stage | Gate | What it makes impossible | On failure |
|---|---|---|---|
| ingest | `plan-sealed-and-log-chained` | growing the denominator mid-run; back-dating a snapshot | closed |
| ingest | `transport-custody` | bytes in the store that never came off a wire | closed |
| per node | `record-admissible` | an unclassified record; a key its own quote does not derive | closed |
| per node | `span-verbatim` | citing a page that does not contain the claim | closed |
| per node | `span-entails-claim` | an observed record nobody judged | closed |
| per edge | `edge-admissible` | dangling endpoints; predicates outside the vocabulary | closed |
| per edge | `triple-entailed` | a relation inferred from co-mention, or judged by nobody | closed |
| whole map | `lattice-exact` | an observed grade surviving a path through a simulated one | closed |
| whole map | `inventory-closed` | silent loss — a page fetched and accounted for nowhere | closed |
| whole map | `corroboration-grade` | *(marks single-sourced claims)* | **annotate** |
| pre-ship | `projection-fidelity` | a projection asserting more than the map does | closed |
| pre-ship | `gate-suite-proven` | the gates passing vacuously | closed |

## Why `corroboration-grade` never gates

It did not survive attack: two outlets reprinting one press release corroborate
each other. It still marks single-sourced claims, because *how much of this
rests on one page* is a real question — it simply may not change the verdict.

The verdict reads `policy`, not loudness. An annotating gate that returns a
failure still cannot sink a run.

## Three devices keep the suite non-vacuous

**Recorded denominators.** Every gate reports how many items it examined.
Passing at zero is often correct — a map with no edges has no inadmissible
edges — so the rule is not *never zero* but that a zero denominator carries a
stated reason, enforced in `GateResult.__post_init__` where a new gate cannot
forget it.

**A gate that could not run is not a pass.** `inconclusive` is its own status
and makes a fail-closed run `INVALID` exactly as a failure does.

**Committed fixture pairs.** `gate-suite-proven` puts 25 probes through the
deterministic gates — planted decoys they must reject and honest maps they must
accept — and requires **both polarities per gate**, not in aggregate. Counting
the accepting half globally was its own hole: an always-failing gate passed all
of its own decoys while other gates supplied the suite's accepting total.

## What a green suite does not establish

> A page at this URL, held at this digest, verifiably says this.

It does **not** certify that what the page says is true. An inflated title, a
phantom advisory board, a shell company listing a nominee director each produce
a fully green `observed` claim. That is a strong, checkable guarantee and it is
not omniscience, and a reader who confuses the two will be misled by a perfectly
honest map.

## Known residuals

- **The lease is narrowed, not fenced.** `land` authorises before mutating and
  re-checks immediately before touching the frontier, so a dead lease cannot
  expand someone else's item. It remains a check followed by a write; closing
  that needs one transaction spanning `land`, which the store does not offer
  across a process boundary. A lapsed lease can still admit records, which is
  deliberate — `put_record` records a differing re-sighting as a **conflict**
  that `select()` returns and `payloads_held` counts, so nothing is lost.
- **The custody split's tool-surface half is a deployment property.** It holds
  because crawl agents are defined without a network tool. It is the one part of
  this architecture the gate set cannot verify about itself from the inside.
- **Profile keys are unversioned.** Changing the derivation invalidates a store
  written by an earlier build.
