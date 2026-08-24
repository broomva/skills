# R1–R7: what a data provider must satisfy

Seven rules. None was invented. Each answers a specific, observed failure in a
prospecting service examined during BRO-2268 — a FastAPI backend behind a tunnel
that produced two runs, neither of which ever returned a candidate:

```
run …91c53b61   "ecopetrol"        22%   strategies 0/11   candidates 0
run …f09ae3b4   nómina/RRHH brief  23%   strategies 2/46   candidates 0   ← was 6/46
```

The rules are written as constraints on **any** provider, not as a description of
that one. Search is the first provider we built; it is not the only shape the
contract admits.

---

## R1 — Every field is classified at the moment it is written, never after

A field is `observed` only if the provider holds the artifact it was read from
and can produce it. Everything else — concluded, matched, guessed, averaged — is
`simulated`.

**Why it cannot be deferred.** Parallax's `provenance.ts` types values at birth:
`Origin = "observed" | "simulated"`, and `meetOrigin` is a meet on the two-element
lattice `observed > simulated`, so anything derived from a simulated input is
simulated however much observed data went in beside it. There is no operator that
adds provenance to a value that arrived without one, by construction rather than
by discipline. A provider that emits a bare table has already destroyed the
distinction, and nothing downstream can recover it.

**The default that is refused.** Unclassified must not become `simulated`. It
reads as caution and is a fabrication: it asserts we know the value was produced,
when we know nothing about it at all.

**Contamination is per column.** Nine cited values and one guess is a *simulated
column*. Averaging, or reporting the majority, is the overclaim the type exists
to prevent.

**Where R1 stops.** It binds the PROVIDER. Parallax's runtime cannot verify an
artifact — it has no access to the run directory and may not be on the same
machine — so an `origin` arriving there is a supplier's assertion, and a caller
hand-typing one is making it with nothing behind it. The runtime prints
"supplier reports its values observed" rather than "observed" for exactly that
reason, and the human accept gate is where an uncheckable assertion is weighed.
A review read the loose version of this rule as a claim that the runtime enforces
it, which it never did and cannot; the rule is about what a provider may emit.

---

## R2 — A record cites its artifact, or it is not evidence

An `observed` field carries a retrievable reference **and** a hash of the bytes
actually read, with a stored copy.

**Why the hash and the copy, not just the URL.** A citation that only names a page
decays silently: the page changes, the link still resolves, and nothing anywhere
reports that the sentence it supported is gone. "The provider saw it" is not a
citation — and a citation nobody can resolve is indistinguishable from an
inference, which collapses R1 back into a formality.

---

## R3 — Progress is a function of work completed, never of stage index

**The failure.** `progress` read 22 at t+2s and 22 at t+67s while `stats` said
0 of 11 strategies complete. Eleven consecutive responses were byte-identical at
1290 bytes. The bar looked alive because it measured how far through its own
pipeline the code had walked, not how much of the job was done.

**The second half.** On the other run `strategies_completed` went **backwards**,
6 → 2, because the orchestrator restarted rather than resumed. A completion count
that can decrease is not progress; it is a restart reported as progress, and the
caller cannot tell the two apart.

**The rule.** Progress is `done / total` over units of real work. Nothing else may
set it, and it may not decrease. Where an honest counter and a smooth one
disagree, ship the honest one.

---

## R4 — A run that found nothing says so, and says it as loudly as one that found something

Zero results is legitimate, common, and must be **reachable, terminal, and
visibly distinct from still-running**.

**The failure.** `candidates_found = 0` on both runs, and no run was ever observed
leaving `orchestrating`. So "we looked and there is nothing" and "still working"
were indistinguishable for as long as anyone was willing to wait. A pipeline with
no terminal empty state cannot be told apart from one that is stuck.

---

## R5 — A started run can be stopped by whoever started it

Cancellation is part of the interface, not an operational afterthought. Without
it the only way to end a wedged run is to restart the service, which makes every
other consumer's run collateral.

**The failure.** There was no cancel or delete endpoint.

---

## R6 — Calls are authenticated, and the credential is required rather than optional

An optional credential is an absent one: the first caller who omits it
establishes that omitting it works.

**The failure.** CORS was correctly scoped to the browser origin, and a
server-side POST with no credential started a real run anyway. The API key was
optional in the caller.

---

## R7 — A page that renders is not a run that carried

A status surface must fail visibly when its subject is absent, not serve
identical bytes and a reassuring zero.

**The failure.** The status page returned HTTP 200 with identical bytes whether
the backend was alive or dead, and showed a permanent 0% when it 404'd.

**And the one worth admitting.** An earlier version of our own report cited that
HTTP 200 as verification. It proved the shell serves — not that the link carries
a run. That is the same defect one level up, in the report about the defect.

---

## Which rules this implementation answers by shape

R5 and R6 exist because the studied thing was a long-running remote service. The
provider here is a script the agent runs inside its own turn: there is no
endpoint to authenticate and nothing that keeps running after the turn ends.

`cancel` is implemented anyway, because a run's directory outlives the turn and a
human may want to close one out. An API-key check on a local function would be
theatre — a control that satisfies a checklist and protects nothing.

Saying which rules do not apply, and why, is better than implementing all seven
and letting a reader assume each one is load-bearing.
