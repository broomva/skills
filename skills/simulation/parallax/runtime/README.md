# Parallax

A developer platform that produces simulation results you can check.

You point Parallax at a context — a business's data, an agent workspace, or an
arbitrary local directory — and it proposes an ontology built from what is
actually there. You accept that proposal before it becomes active. It then rolls
the accepted model forward under candidate decisions, so you can see what a
change does before you commit to it.

Every answer is typed `observed | simulated`. Nothing in the system can produce
a number without saying how much of it was real.

## Why this is not another simulator

A simulator's output is unfalsifiable by default: it produces confident numbers
about a world that does not exist. The usual response is to claim more fidelity,
which is not a claim anyone outside the simulator can check.

Parallax takes the other route. Determinism is checkable in five seconds, and
reproducibility is a property the system carries, propagates, and withdraws on
its own. The design target is not a simulator that is right. It is a simulator
that cannot lie about being a simulator.

Three things follow from that, and all three are enforced in code:

- **A domain's transition and its invariants are code, never a model.** No model
  computes a ledger and no model judges whether a constraint held.
- **A policy cannot certify its own reproducibility.** `certifyPolicy` runs it
  repeatedly against an identical probe. A policy that cannot reproduce its own
  output under a fixed seed is demoted whatever it declares about itself, and
  the demotion is written onto the branch.
- **An ontology nobody accepted cannot run.** The accept gate is a runtime
  check, not a type-system convention, and it refuses while any blocking
  question is open. Units on numeric quantities are always blocking.

## Run it

This runtime is not a repository root. It lives at
`skills/simulation/parallax/runtime/` inside
[`broomva/skills`](https://github.com/broomva/skills), and every command below
is run from there.

Requires [Bun](https://bun.sh).

```bash
bun install
bun run demo           # the runtime on one sample flow: run, observe, check, fork, prove
bun run demo:whatsapp  # the same thing as one WhatsApp thread, ending in a receipt file
bun run demo:live      # the same thread against the deployed hub, ending in a link it fetched first
bun test
bun run typecheck      # bun test does not typecheck; this is a separate gate on purpose
bun run mutants        # deletes a guarantee, checks whether anything goes red
bun run lint
```

To get `parallax` itself on your PATH:

```bash
bun link                # then `parallax help` anywhere
parallax propose        # reads the directory you are standing in
parallax answer --answer 1=pieces
parallax accept --proposal <ref> --by <who> --acknowledge-unmapped
parallax run --horizon 12 --seed 42
```

The nine commands are the nine tools, one for one — see
[AGENTS.md](./AGENTS.md#the-three-surfaces-are-one-capability-set) for the
correspondence and the two places the surfaces deliberately differ.

`bun run mutants` exists because a passing suite is not a testing suite. It
removes one specific promise at a time — the accept brand, idempotent
acceptance, answer-value identity, "the newest acceptance" — and reports which
ones nothing notices. It refuses to run against a dirty tree — this directory's,
not the whole monorepo's — requires every anchor to match exactly once, and
carries a control in each polarity: a mutant that must die and a mutant that
must live. If either control misbehaves the run is reported invalid, because a
harness that cannot see red and a harness that reports noise are both worth
nothing.

The landing page at <https://broomva.github.io/parallax/> — with the worked use
case at </use-cases/> and the full evidence page at </proof/> — is still served
out of the original `broomva/parallax` repository, which is archived read-only and
is frozen at the last build made there. Its source lives in that same repository at
`web/`, and a copy that briefly lived in this monorepo has been removed — it
published nothing (this repository has no Pages site), so it was a build gate over
a page nobody here could republish. Nothing in this monorepo reaches that page.

The hub is <https://parallax-hub.onrender.com>. `GET /health` reports the commit
the server is running, which is the only field on it that a stale image cannot
fake — a `version` string is a source constant and a deploy dashboard reports
intent. The hub is on a free tier, so the first request after fifteen idle
minutes pays about a twelve-second cold start.

The demo runs a WhatsApp storefront under an ungoverned sales agent, catches it
overselling stock it does not have, forks the history at the moment before the
damage, replays the same twelve steps with a governor installed, and prints the
difference. It finishes by proving replay is a hash comparison rather than a
claim: the same seed produces an identical trace hash, a different seed
diverges, and an unpinned actor causes the branch to withdraw its own
reproducibility claim.

## Drive it from an agent

The agent skill is the directory this runtime sits in —
`skills/simulation/parallax/`. It teaches an agent when to reach for Parallax,
the nine-command flow, and what each of the 52 error codes actually means —
several have remedies a plain reading of the `reason` will not produce.

```bash
npx skills add broomva/skills --skill parallax -g -a claude-code
```

The skill and this runtime are one directory now. There is a single copy of
each, so there is no drift gate: there is nothing to compare it against.

## The shape of it

A domain arrives as data. The runtime never changes.

| Slot | Supplies | Who computes it |
|---|---|---|
| `state` | typed fields, units mandatory | schema |
| `actions` | name, actor, params | schema |
| `transition` | how an action changes the state | code, never a model |
| `invariants` | what must always hold | code, never a model |
| `initial` | where it starts | data |

Six operators are closed over that record: `step`, `observe`, `check`,
`rollout`, `diff`, `traceHash`. Adding a domain adds a record. Adding a
capability adds an operator, and there are six of those. That asymmetry is what
separates a simulation runtime from a pile of bespoke simulators.

## The agent is a user

Every capability a human can reach is reachable programmatically, and every
failure is a value with a stable machine-readable code rather than a thrown
string a caller has to parse. Error types are per-operation: a plugin failure
inside a rollout carries a partial trajectory, the same failure at registration
carries nothing, and a single error type cannot express that difference.

```ts
const proposal = proposeOntology({ kind: "filesystem", root: "./src" });
if (!proposal.ok) return proposal.error.code; // SOURCE_UNREADABLE | SOURCE_EMPTY | ...

const active = activate(proposal.value, { transition, invariants, answered, acceptedBy, at });
if (!active.ok) return active.error.code;     // BLOCKING_QUESTIONS_OPEN | NO_INVARIANTS | ...
```

## Status

The runtime, the log with copy-on-write forking, the reproducibility lattice,
the conservation-invariant checker, the ontology proposal and its accept gate
all exist and run. So do a CLI, an HTTP hub and an agent tool surface over the
same handler functions, and a second domain — a clinic appointment desk with its
own transition and its own conservation law, which is the generality proof: the
runtime did not change to accept it.

The LLM policy adapter, a third domain, a domain supplied by someone who is not
us, an MCP server, and the web console are designed and not built. The MCP one is
worth naming because the seam for it is already cut and can read as finished:
`toolSpecs()` hands out every tool as data, the schemas were written so a JSON
Schema surface and a Zod surface cannot disagree, and a test already asserts every
tool name is legal as an MCP tool name. What is missing is only the transport.

Nothing here has been calibrated against a real business, because we have no
real transcripts — that is the oldest open item in this project and it cannot be
closed by writing code.

We would rather say that than publish an accuracy number we cannot support.

## Licence

Apache-2.0. See [LICENSE](./LICENSE).
