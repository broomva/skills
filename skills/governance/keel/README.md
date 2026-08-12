<p align="center">
  <img src="design/mark.png" alt="Keel" width="180" />
</p>

<h1 align="center">Keel</h1>

<p align="center">
  <a href="https://github.com/broomva/skills/actions/workflows/test-keel.yml"><img src="https://github.com/broomva/skills/actions/workflows/test-keel.yml/badge.svg" alt="Tests" /></a>
  <a href="../../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT" /></a>
  <a href="https://agentskills.io"><img src="https://img.shields.io/badge/agent%20skill-installable-7dd3fc" alt="Agent Skill" /></a>
</p>

**Your agents are grading their own homework. Keel measures how much.**

```bash
npx skills add broomva/skills --skill keel
```

A ship's keel is the reference line everything else is measured from — and an
*even keel* is a stability property, not a decoration.

Keel measures one thing:

> A check is only a check if the signal it reads comes from somewhere the thing
> being checked cannot write to.

Most verification in an agent-maintained codebase fails this. An LLM reviews
what an LLM wrote. A doc is validated against another doc. A status field reads
"passed" because something set it to "passed". The pipeline is green and
nothing has been verified.

## Where the predicate comes from

Silver & Sutton's [*Welcome to the Era of Experience*](https://storage.googleapis.com/deepmind-media/Era-of-Experience%20/The%20Era%20of%20Experience%20Paper.pdf)
makes the case that agents have to leave human-prejudged reward behind for
**grounded** signals — ones "that arise from the environment itself" — because
relying on a human rater "usually leads to an impenetrable ceiling on the
agent's performance", and without grounding an agent "will become an echo
chamber of existing human knowledge."

That argument is right, and it stops one question short. **Grounded and
independent are different properties.** The paper's own inventory of available
signals — "cost, error rates … profit, sales … visits, yields, stocks, likes …
accuracy, power, distance, speed, efficiency" — mixes producers an actor cannot
touch (a payment that settled, a customer who churned) with producers it
operates itself (its own analytics, its own test suite). Its clearest example
is the sharpest case: coding agents improved on **execution feedback**, "where
the agent actually runs code and observes what happens" — maximally grounded,
and the canonical reward-hack surface in agentic coding, because the agent
writes the test.

So Keel asks the second question:

| | asks |
|---|---|
| *Era of Experience* | is this signal from the environment? |
| **Keel** | **and can the thing being measured write to it?** |

An abundance of grounded signals is not an abundance of independent ones. Keel
measures the difference.

## What it does

Keel walks a target's verification edges — CI steps, test targets, review
gates, deploy conditions, integration signals — and classifies each one:

| Class | The signal's producer is… |
|---|---|
| `anchored` | outside the actor's write boundary — a process exit code, a type checker, a payment that settled, a customer action |
| `self_referential` | inside it — an LLM judging output, a doc checked against a doc, a self-set status |
| `unknown` | untraceable. **Fails closed.** |
| `not_a_check` | nothing — the node asserts no property. Excluded from the ratio, which is why it is the one class worth shopping into |

**Grounding ratio** = `anchored / (anchored + self_referential + unknown)`.

`unknown` counts against, deliberately. Absence of evidence of dependence is
not evidence of independence.

## It gets cheaper every run

Novel shapes are judged by the agent. Recurring shapes get crystallized into
**probes** — small, reviewable scripts — so the next occurrence costs no model
call at all. The probe library is code, which means it is diffable, testable,
and rejectable, and it compounds across everyone who runs Keel.

Probes may **abstain**. They may never return `unknown`. A probe that is unsure
falls through to the agent, so a lazy probe degrades to "ask" rather than to
"looks fine."

## And it audits itself

Probes drift. `keel audit` samples probe-classified nodes and hands them back to
the agent to re-decide **with the cached verdict hidden** — the blindness is the
mechanism, because an audit you can see the answer to measures your agreement
with yourself. It then reports the agreement rate **with its denominator**, and
names the probes that disagreed.

It does not retire them. Retiring a probe is a judgment about the world, and
that stays with a human.

The library's agreement rate is Keel's own counter-metric — a tool that measures
groundedness while refusing to measure its own would be making the exact mistake
it exists to find.

## From a number to a path

A ratio nobody can act on is a report card. So `keel route` reads the report
and, for every ungrounded check, proposes a route to an anchored signal **that
already exists in the same graph**:

> `Rakefile:24 tests` cannot fail — Ruby's `system` does not propagate exit
> status, so the task exits 0 when rspec fails. The same assertion already runs
> anchored at `.circleci/config.yml:101`, where CI gates on the real exit code.

The rule underneath it: **independence cannot be manufactured, but it can be
routed.** Keel never invents an anchor. It connects a check that asserts
nothing to a producer you already own — and when no such producer exists, it
says so instead of guessing.

Routing never moves the ratio. A proposal is not a change; the number only
moves when a human applies one and Keel re-measures from the target. The thing
that proposes changes to your graph must never be the thing that scores it,
or the score stops meaning anything — so that separation is enforced by a test,
not by a promise.

## Modes

| | |
|---|---|
| `keel measure` | walk the verification edges, classify, report the ratio |
| `keel route` | propose routes from ungrounded checks to anchors you already have |
| `keel audit` | re-decide a sample of cached verdicts; report the agreement rate |

`keel construct` (counter-metric pairing, arbitration, audit loops) and
`keel apply` are specified and not yet built — see
[`docs/constructive-grounding-layer.md`](docs/constructive-grounding-layer.md).

## Using it

Keel runs **inside your agent harness** — Claude Code, Codex, Cursor, or
anything that reads [Agent Skills](https://agentskills.io). It does not
reimplement a harness, and there is no daemon or hosted service.

```bash
npx skills add broomva/skills --skill keel   # requires the skills CLI; Bun for local dev
```

Then point your agent at a target in plain language:

```
measure the grounding of this repo with keel
```

The agent gathers the verification edges, classifies each one, and writes a
`report.json` plus a self-contained HTML report that opens from `file://` and
survives being emailed. Ask it to `route` afterwards to get a proposal per
ungrounded check.

Keel itself transmits nothing. Classification a probe cannot handle happens in
whatever model your harness is already running, under your existing provider
terms.

Probes, though, are **executed code**, and the sandbox that confines them is
macOS-only — `sandbox-exec` exists nowhere else. On Linux and Windows a probe
runs with a stripped environment and a kill-timer, but it can write files,
reach the network, and spawn processes. Review a probe before you install it,
and see [SECURITY.md](SECURITY.md) for exactly what is enforced where.

## Scope, honestly

Keel measures the *shape* of verification, not its quality. A repo can be 100%
anchored with terrible tests. Anchoring says the signal comes from outside; it
does not say the signal is enough.

And the deep limit, stated in the product rather than discovered later: **a
test's execution is anchored; its oracle may not be.** When the same agent
writes the implementation and the assertions, the runtime honestly decides
pass/fail — but the specification was authored inside the write boundary, and
both can drift together and stay green. Keel classifies the execution axis and
names the limit rather than silently upgrading it to proof.

## Contributing

The highest-value contribution is **a probe** — a small reviewable script that
classifies a recurring shape without a model call, making Keel cheaper for
everyone. A close second: telling us Keel got a classification **wrong**. That
is the most useful bug report this project can receive.

| | |
|---|---|
| [probes/README.md](probes/README.md) | the probe contract, the rules, how to contribute one |
| [SECURITY.md](SECURITY.md) | private disclosure, and what Keel executes on your machine |
| [Open an issue](https://github.com/broomva/skills/issues/new) | Keel assigned the wrong class — say which node and why |
| [Design system](design/README.md) | tokens, components, and the brand rules |

## License

MIT — see the [repository LICENSE](../../../LICENSE).
