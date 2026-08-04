# Keel — the constructive grounding layer (post-event)

**Status:** roadmap. Nothing here is in scope before
the pitch. See `docs/plans/00-orchestration.md` for tonight.

**Read first:** `docs/adrs/2026-07-24-ai-native-platform-reframe.html` — the
decision and its sourcing. This document is *what to build*; the ADR is *why it
is allowed*.

---

## The shape

Keel today is diagnostic: it walks verification edges and reports a grounding
ratio. The constructive layer adds the second half — for every node that is not
anchored, find the exogenous producer the organization **already owns** and
rewire the check to read it.

> Independence cannot be manufactured, but it can be routed.

The product sentence:

> Keel reads your operations through whatever integration layer you already
> have, finds the ground truth you already own, and builds the loop graph that
> keeps your agents attached to it.

The grounding ratio is not the product. It is the altimeter, the first pass, and
the counter-metric that keeps the constructor honest.

---

## The partition — frozen, and the whole safety argument

| Keel **constructs** | Keel **imports, never authors** |
|---|---|
| Counter-metric pairings | **Anchors** — discovered, never invented |
| Hierarchy (which loop owns which reference) | **Frozen nodes** — the anchor registry is not agent-tunable |
| Arbitration loops | **The root definition of "better"** — human, once, per company |
| Audit loops | |
| Routing of existing anchors into unanchored checks | |

Source: `grounded-vs-ungrounded-improvement.md:58-69` enumerates exactly three
things topology cannot supply; `:51-56` lists the four it can.

**If a unit finds itself writing code that lets the agent add an entry to the
anchor registry, it has broken the safety argument and must stop.**

---

## Phases

### Phase 1 — prescriptive report (the bridge)

The cheapest real step, and the only one that could ever be pulled forward.

| Unit | Deliverable |
|---|---|
| **P1-a** | Renderer prints a *proposed anchor* beside each `self_referential` / `unknown` verdict |

No engine change. Every verdict already carries `writeBoundary.argument`, which
already records *why* the check is ungrounded — the proposal is a rendering of
data that exists.

**Acceptance:** a report on a repo with ≥1 `self_referential` node shows a
proposed anchor with a named producer, or explicitly says none was found.

### Phase 2 — anchor discovery over the integration surface

| Unit | Deliverable |
|---|---|
| **P2-a** | `integration` NodeKind actually emitted — gatherer reads a connected integration surface |
| **P2-b** | Anchor registry: pre-committed, human-signed, versioned, **not agent-writable** |

Composio (or any equivalent) is the access layer, answering one bounded
question: *which exogenous producers does this company already own?* Verified
reachable: `composio search "payment settled webhook"` → `STRIPE_GET_EVENTS`.

**This is the phase that makes `SKILL.md`'s existing company claim true.** Until
it lands, that claim is a `self_referential` `doc_claim` inside Keel — see ADR
§Known gap.

**Schema note:** the frozen contract survives this. Only two fields are
repo-locked and both are metadata, not predicate — `Node.source` ("repo-relative
path", `keel.ts:33`) and `Report.revision` ("commit sha", `keel.ts:149`).
Widening them to generic provenance strings is a comment change. Do not treat
this as licence to touch the rest of the schema.

### Phase 3 — the constructor

| Unit | Deliverable |
|---|---|
| **P3-a** | Emit counter-metric pairings for unpaired optimizing loops |
| **P3-b** | Emit arbitration cells where loops conflict |
| **P3-c** | Emit the reference hierarchy + audit loops |

**Dogfood target is bstack itself.** Handoff §2.4 records, verified by grep,
**zero hits** for `counter-metric` / `metric pairing` and **zero hits** for
`arbitration` / `conflicting loops`. The constructor should generate the
counter-metric for P20's unpaired 7/10, for P6's unpaired Nous ≥ 5/9, and the
arbitration cell for the m6-vs-P16 conflict that §2.4 records being settled by
ad-hoc agent judgment.

If it cannot produce those three, it does not work — and we will know, because
we already know the right answer's shape.

### Phase 4 — substrates beyond the repo

Spec: `docs/designs/2026-07-24-substrate-generalization.html`.

The predicate needs only an actor with a definable write boundary, so it also
fits company operations and — more cleanly than either — a **public company**,
where securities law has already drawn the actor/producer line. Validation there
has something the repo corpus does not: **an answer key**. Backtest pre-collapse
filings of companies that later blew up (Luckin Coffee `CIK 0001767582`: 86
pre-collapse filings on EDGAR, including a `424B4` filed 2020-01-10, three weeks
before the Muddy Waters report).

Cost to the frozen schema is a comment change — see the design doc §What this
costs in the schema. Cost to `gather` is real: extraction over prose, not YAML.

---

## The one architectural invariant

**The constructing loop is not the scoring loop.**

`verifier-independence-depletes-under-optimization.md:44-50` — the instant the
score becomes a selection signal, the constructor hill-climbs into the scorer's
blind spot. Freezing does not help (`:97-108`): *"freeze stops the gradient;
only a query budget stops the selection."*

| | Constructing loop | Scoring loop |
|---|---|---|
| Does | proposes + applies rewirings | classifies, ε-audits |
| Cadence | fast | **~an order of magnitude slower** |
| May tune anchor registry? | never | never |

Cadence separation has numbers, not vibes — RCS λ margins (handoff §2.3):
L1 `0.411` → L2 `0.069` → L3 `0.006`, roughly 6× then 11×.

**The ε-audit agreement rate is the depletion detector.** It was built as a
counter-metric on the probe library; it is also exactly the instrument this
architecture needs. A falling agreement rate means the constructor is eating the
scorer's independence — that is the alarm, and it must be wired to one.

### The failure mode this is guarding against

`self-improvement-verifier-ceiling.md:59-64` — *Self-Harness* (arXiv:2606.09498):
agents that autonomously edit their own scaffolding converge in **3–5
iterations** and fix only behavioural errors, never capability errors. A
self-scoring constructor plateaus there *with the ratio still climbing*, which
is worse than plateauing visibly.

---

## Non-goals

- **Not a workflow-graph builder.** Composio, Dust, Lindy, Gumloop, n8n,
  Relevance and Zapier Agents own that lane. Keel is the admission predicate and
  remediation path *over* whatever graph they produce.
- **Not full autonomy.** The root definition of "better" stays human — one input
  per company. This is a selling point, not an apology: the buyer with real
  anchors does not want its judgment replaced, it wants its existing ground
  truth wired in.
- **Not a measurement product.** Diagnosis without a path is what this roadmap
  exists to fix.

---

## Standing constraints

Inherited from `00-orchestration.md` and still binding: Bun + TypeScript +
Biome; zero runtime dependencies unless a plan names one; **judgment is the
agent's, scripts are plumbing**; `unknown` fails closed; any code path that
defaults a node to `anchored` is a bug.

One addition specific to this layer:

- **A proposed rewiring is a proposal, not an edit.** The constructor emits;
  a human or a pre-committed policy admits. An agent that applies its own
  rewiring and then scores it has collapsed the two loops.
