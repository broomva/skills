# Grounding classes — worked cases

The question is always the same:

> **What produces this signal, and can the actor being verified write to that
> producer?**

Not "is this a good check." Not "does this look rigorous." Only: where does the
signal come from, and who can reach it.

## Clearly anchored

| Edge | Why |
|---|---|
| `vitest run`, `pytest`, `cargo test` in CI | The runtime decides the exit code. No amount of persuasion changes a segfault. |
| `tsc --noEmit`, `mypy`, compiler | Deterministic analysis of the artifact itself. |
| A payment that settled at the processor | The bank is not reachable by the agent's write path. |
| A customer renewed / churned | An action taken by a party outside the system. |
| Independent uptime prober hitting a public URL | Third-party observation the deployer does not author. |
| Load/latency measured by the client, not the server | The measurer is not the measured. |

## Clearly self-referential

| Edge | Why |
|---|---|
| An LLM reviewing LLM-written code | Same class of system on both sides. Correlated blind spots; agreement is not evidence. |
| A doc validated against another doc | Paperwork against paperwork. |
| A status field the actor sets, gating on that field | The claim and the check are the same write. |
| An agent reporting "task complete" | A claim marker, not a landed signal. |
| `--update-snapshots` then asserting the snapshot | **The code authored its own expected output.** The test executes, but the oracle came from the thing under test. |
| A `/health` endpoint returning a hardcoded 200 | Reports liveness of the reporter. |

## The cases that look anchored and are not

These are where most of the value is. Read carefully.

**A test that exists but is not in the pipeline path.** Executable, therefore
"anchored" if you only read the file. But it gates nothing. Classify the *edge*
that actually blocks the merge, not the file that could have.

**A green aggregate that wraps unknown children.** "All checks passed" is only
as anchored as the checks it aggregates. Do not classify the wrapper; descend.
If you cannot descend, that is `unknown`, not `anchored`.

**A bot review that renders like a human review.** CodeRabbit, Copilot review,
any LLM reviewer produces a signal from the same class of system that produced
the work. It renders as an approval and carries the authority of one. It is
`self_referential`.

**A coverage threshold.** Coverage is measured by execution, so the producer is
anchored — but it measures *reach*, not correctness. Classify `anchored` and
note the limit in the argument. Do not let it read as proof of anything but
execution.

**A metric read from a system the actor writes to.** Application logs, its own
telemetry, a self-reported job status. The channel is the actor's output. A
detector reading the audited channel has an adversary-controlled view.

**A check that cannot fail.** `"test": "echo ok"`, a run step ending in
`|| true`, `continue-on-error: true`, a target whose body is `exit 0`. The
runtime honestly produces the exit code — the producer is outside the write
boundary — but a signal that cannot vary carries no information.
Falsifiability is a structural property: an edge that cannot fail asserts
nothing, so it is `not_a_check`, with the vacuousness named in the argument.
This is still shape, not quality: the question is not whether the check is
good, but whether it is capable of being a check at all.

## The deep limit — say this out loud in the report

A test's **execution** is anchored. A test's **oracle** may not be.

When the same agent writes the implementation and the assertions, execution
independence still holds — the runtime genuinely decides pass or fail — but the
*specification* was authored inside the write boundary. The test then proves
"the code does what the test says," and says nothing about whether the test says
the right thing. Both sides can drift together and the suite stays green.

Keel classifies the **execution** axis, because that is the axis it can
actually trace. When you see a test suite whose assertions are plausibly
co-authored with the implementation, mark it `anchored` and name the limit in
`writeBoundary.argument`. Do not silently upgrade it to proof.

The same distinction rescues one case that looks hopeless: an LLM judge scoring
against a rubric **fixed before generation** is meaningfully stronger than an
ad-hoc judge, because the verdict is a function of a constraint the generated
content could not influence. Still not anchored — the judge remains the same
class of system — but the argument should record that the reference was frozen.

## When to say `unknown`

Say it whenever the fork point is not traceable. A vendored binary with no
source. A check whose implementation lives outside the repo. An integration
whose behavior you cannot inspect. A wrapper you cannot descend into.

`unknown` is a real answer, it is frequently the correct one, and it counts
against the ratio on purpose. The failure mode Keel exists to prevent is a
confident green — so guessing `anchored` to avoid an ugly number is the one
mistake that makes the whole tool worthless.
