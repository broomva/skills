---
name: checkable
description: "State a problem so that agents can be handed it and the result relied on without inspecting the work. Writes the problem as claims, the check behind each claim, the actions the work may take, and what stays unverified. A checker refuses the statement when it breaks an invariant: a strict shape, a statement pinned to a base, receipts, checks that can fail, independent verifiers, declared order, reversibility classes, checked hand-offs, a declared remainder. A router then lists the skills and services that serve each part. Use when someone says 'make this checkable', '/checkable', 'how would we trust agents with this', 'state this problem for the fleet', or before handing a non-trivial or irreversible problem to autonomous agents, in code or outside it. Not for reviewing finished work (cross-review), turning a repeated mistake into a check (correct), or a one-step task with nothing irreversible in it."
tier: D
---

# checkable

Agents make candidate solutions cheap. What stays scarce is a reason to rely on
a result nobody inspected. `checkable` moves that reason out of the agent and
into a statement: a small file that says what is claimed, what would show each
claim false, what the work is allowed to touch, and what nobody checked.

The statement is the contract. `scripts/checkable.py` refuses it when it breaks
an invariant, and that is the only thing the script decides. Whether the claims
are the *right* claims is a reader's judgment and stays one.

## Why this shape

1. **Trust attaches to a relation, not a mind.** You can rely on work through
   understanding it, verifying it, confining it, or its track record. Agents
   remove the first, so the statement is built from the other three.
2. **Search is abundant, checking is scarce.** Make every candidate arrive with
   a check that is cheap to run.
3. **Trust is moved, never created.** A claim is as trustworthy as the smallest
   thing you must believe to accept it. Keep that base small and still.
4. **Evidence counts only when its origin differs** from what it judges.
5. **A check that cannot fail is not a check.**
6. **What cannot be checked must be undoable.** What can be neither stays with
   the person who bears the consequence.

Human institutions already work this way: double-entry bookkeeping, replication
in science, two signatures on a payment, a checklist before take-off.

## The statement

A statement is one JSON document of at most 1 MiB. JSON is the only format:
it has no anchors, tags or implicit types, so the text a person reads is the
data the checker gets.

```json
{
  "checkable": 1,
  "problem": "Close the month's books and file the tax prepayment.",
  "domain": [
    "finance"
  ],
  "performers": [
    "model:anthropic"
  ],
  "claims": [
    {
      "id": "books-balance",
      "text": "Debits equal credits for the month.",
      "rung": "proof",
      "verifier": {
        "origin": "code",
        "check": "ledger balance --month 2026-10",
        "rejects": "ledger balance --file fixtures/one-sided-entry.ledger"
      },
      "status": "open"
    },
    {
      "id": "treatment",
      "text": "The chosen tax treatment is the best one available.",
      "rung": "none"
    }
  ],
  "actions": [
    {
      "id": "file-prepayment",
      "text": "File and pay the prepayment",
      "reversibility": "irreversible",
      "reach": "the tax authority's record and the bank account",
      "gate": "human:owner",
      "requires": [
        "books-balance"
      ]
    }
  ],
  "flow": {
    "steps": [
      "books-balance",
      "file-prepayment"
    ]
  },
  "feeds": [
    {
      "from": "this month's closing balance",
      "to": "next month's opening balance",
      "check": "books-balance"
    }
  ],
  "learning": {
    "on_correction": "a misfiled transaction becomes a classifier rule with that transaction as its test"
  },
  "unverified": [
    "treatment: whether the chosen tax treatment is the best one available"
  ]
}
```

| Field | What it holds |
|---|---|
| `domain` | names the router matches against the index |
| `performers` | who does the work, as `model:<provider>` or `human:<role>` |
| `claims[].rung` | where the claim sits on the ladder below |
| `claims[].verifier.origin` | `code`, `sensor:<name>`, `model:<provider>` or `human:<role>` |
| `claims[].status` | `open`, `accepted` or `refuted`; an accepted or refuted claim also carries a `receipt` |
| `actions[].reversibility` | `reversible`, `compensable` or `irreversible` |
| `flow.steps` | claim and action ids in the order they happen |
| `feeds` | each output that becomes an input, with the claim that checks it |
| `unverified` | what nobody checks; a claim on rung `none` is named here by its id |

Two complete statements ship in `examples/`: the one this skill was shipped
under, and a monthly close.

## The invariants

| Code | Invariant | Refused when |
|---|---|---|
| C1 | The statement matches the base | Anything except a claim's `status` and `receipt` differs from `--base`, or a claim is accepted while the statement is not at the base |
| C2 | An accepted claim carries a receipt | `receipt.revision`, `receipt.replay` or `receipt.result` is missing or contradicts the status; for a proof or replay claim, `receipt.replay` is not the claim's own `check` |
| C3 | Every check can fail | A verifier lacks the fields that let it fail for its rung |
| C4 | The verifier's origin differs from the performer's | A performer judges its own work, or a judgment names no model or person |
| C5 | Order is declared | Two actions, or one irreversible action, with no `flow.steps`; an action missing from the steps; a required claim placed after its action |
| C6 | Actions are classed by reversibility | No class, no `undo` for a reversible or compensable action, or an irreversible action whose gate is missing, is a performer, or is a claim weaker than proof or replay |
| C7 | Every hand-off passes a check | A `feeds` hop names no checking claim, or no place is given for corrections |
| C8 | The remainder is written down | `unverified` is missing, or no entry names a claim on rung `none`: an entry names it when it is the bare `<id>` or starts with `<id>:` |

C0 comes first: the statement is read strictly. A value of the wrong type, a
key this format does not define, or a key written twice is refused, and the
other invariants are not decided until the shape is right. Ids are lower-case
letters, digits and hyphens. An origin is `code`, `sensor:<name>`,
`model:<provider>` or `human:<role>`, in lower case with no spaces, so the same
performer cannot be written two ways.

C1 is what stops a performer quietly editing its own contract: the base
revision declares the statement, and changing it means landing the change on
the base first. With `--base`, `check` exits 3 when the comparison could not be
made, including when the statement is not on the base yet.

## The verification ladder

Give each claim the strongest rung it can afford.

| Rung | What it gives | The verifier must carry | In code | Outside code |
|---|---|---|---|---|
| `proof` | decided on the artifact itself | `check`, `rejects` | types, a proof kernel | books that balance, a schedule with no clash |
| `replay` | same inputs, same result | `check`, `rejects` | tests | recomputing a tax from the ledger |
| `measurement` | an independent sensor on the world | `sensor`, `positive_control`, `falsification_criterion` | production metrics | a bank statement, a lab assay |
| `judgment` | an independent judge and a fixed rubric | `rubric`, `pass_rule` | cross-model review | a second medical opinion |
| `track-record` | a prediction scored later | `prediction_recorded` (a date), `scored_by` | revert rate | forecast calibration, a trial period |
| `none` | nothing; confinement only | no verifier | n/a | taste, strategy |

`rejects` is a command that must exit non-zero: a recorded case the check
refuses. `rejects_exit` optionally fixes the exact status it must end with, and
`accepts` optionally adds a case that must pass. A claim on rung `none` may
guard only reversible actions, cannot be accepted, and must be named in
`unverified`. Only a `proof` or `replay` claim, or a named person who is not a
performer, can gate an irreversible action.

## Procedure

1. **Name the objects.** What exists in this problem, and in what state?
2. **Write the goal as claims.** Split each until every leaf sits on a rung.
   What will not split goes on rung `none`.
3. **Give each claim its check and its origin.** Ask what would show it false
   and who or what looks. If the answer is the performer, find another origin.
4. **Class every action.** Can it be undone, and how far does it reach? Gate
   the irreversible ones.
5. **Declare the order** as `flow.steps`. A claim an action requires comes
   before that action. `flow.ref` may also name a flow definition file.
6. **List what stays unverified.** An empty list needs a stated reason.
7. **Land the statement on the base before the work starts.** Then run the
   work, record receipts, and send each correction to `learning`.

Run `check` after step 6 while drafting, `check --base` once the statement has
landed, and `route` to see what to load.

## Commands

```bash
python3 scripts/checkable.py check  <statement> [--base origin/main] [--json]
python3 scripts/checkable.py replay <statement> [--cwd DIR] [--timeout 300]
python3 scripts/checkable.py route  <statement> [--json]
python3 scripts/checkable.py index  [--require-roster]
```

| Command | Decides | Exit |
|---|---|---|
| `check` | whether the statement breaks an invariant; prints coverage | 0 holds, 1 a finding, 2 unreadable, 3 `--base` was given (even empty) and the comparison could not be made |
| `replay` | for each `proof` and `replay` claim: the known-bad case is refused, the known-good case accepted when one is given, then the check runs | 0 all pass, 1 a check failed, 2 a control did not behave or nothing ran |
| `route` | which indexed skills and services serve each part, for the statement's domains and rungs | 0, or 2 for a malformed statement |
| `index` | that every installable skill (`skills/<bucket>/<name>/SKILL.md`) is indexed or set aside, and nothing indexed is gone; a `SKILL.md` nested deeper is not counted | 0, 1, 2, or 3 when a roster was required and not found |

Unreadable input exits 2 with one line on stderr, never a traceback. That
includes a file named `.yaml` or `.yml`, a document over 1 MiB, and a key
written twice. The copy of a statement at the base goes through the same reader
with the same limits, and each git call has a 60-second limit.

In `replay`, a known-bad case that could not run proves nothing, so it is
INVALID, not a refusal: a missing command (exit 126 or 127), a timeout, or an
exit status above 128, which is also how a shell reports a signal. When a
status above 128 really is the refusal, state it as `rejects_exit`. Commands
read nothing from standard input. A timeout stops the command's process group,
and so does SIGINT, SIGTERM or SIGHUP sent to `replay`, which then exits with
128 plus the signal number. A process that leaves that group is not stopped,
and SIGKILL to `replay` cannot be handled.

`replay` runs the commands written in the statement, through a shell. Run it
only on a statement you would run as a script.

## What it composes

`references/index.json` tags each skill in this repository, and each service,
by the part of a statement it serves, the rungs it verifies on and its domains.
The short form:

| Part of the statement | bstack primitive | Serves it |
|---|---|---|
| Objects and state | Snapshot (P15) | `kinetic`, `parallax`, `tekton`, `sourcer`, `data-provider`, `kg` |
| Claims | Tickets (P3) | `disambiguate`, `spec-contract`, `agentic-leadership`, `cuenca` |
| Verifiers | Empirical (P11), Cross-Review (P20) | `keel`, `prove-the-negative`, `dogfood`, `cross-review`, `autoreview`, `kinetic`, `nous` |
| Evidence | Bridge (P1), Bookkeeping (P6) | `bstack verify` records, `lago`, `bookkeeping`, `decision-log` |
| Actions and shield | Gate (P2), Pipeline (P4) | `maestro`, `cuenca`, `praxis`, `forkable-shell` |
| Order | Orchestrate (P19), Wait (P9), Persist (P12) | the Maestro flow kernel, `autonomous`, `arc`, `persist` |
| Performers | Fanout (P5), Lens (P17) | `role-x`, `fleet`, `provider-manager`, `identity` |
| Corrections | Crystallize (P16) | `correct`, `skillify`, `autoany` |
| The remainder | none | `handback`, `premortem`, `parallax` |

Four separations recur across those services, and the invariants are the same
four written for one problem: the writer is not the judge (C4), proposing is
not deciding (C6), the base is not the working copy (C1), and what was observed
is not what was claimed (C2, C3).

`positive_control` and `falsification_criterion` use the names of bstack's
`measurement` record. The two formats are otherwise separate: `sensor` is this
skill's own field, and a statement is not a measurement record.

## Under the flow kernel

`assets/flows/checkable.yaml` is a flow definition for the Maestro flow kernel.
It has three steps. `pin` confirms the repository is at the commit you named
and that the statement and the tool are tracked files whose working copies
match that commit.
`statement` runs `check --base`, so it fails with exit 3 until the statement is
on the base. `replay` runs the statement's proof and replay claims in a
snapshot of that commit, so uncommitted work cannot satisfy them. The kernel
records the exit status and an output hash for each step, and a passing
`replay` prints the same text every time, so the hash can be compared with a
run by hand.

```bash
maestro flow start --definition assets/flows/checkable.yaml --params '{
  "repo": "<repo>", "head": "<sha>", "base": "origin/main",
  "statement": "<path to the statement, relative to the repo>",
  "tool": "<path to checkable.py, relative to the repo>",
  "bin": "<optional: a directory put first on PATH>"}'
```

Then drive it with `maestro flow next`, `claim` and `complete` until its status
is terminal. Without Maestro, run `check --base` and then `replay` by hand in
the same order.

## What the checker cannot tell

| It checks | It cannot check |
|---|---|
| each claim has a check that could fail | that these are the right claims |
| a verifier names an origin other than the performer | that the named judge ever ran |
| origin `code` is accepted as independent | who wrote the code; a check the performer wrote is still the performer's |
| `rejects` exits non-zero and `check` exits zero | that the two exercise the same thing; `check: "true"` with `rejects: "false"` passes `replay` |
| a receipt names a revision, a replay and a result | that the receipt describes something that happened; `replay` runs the check now and does not read receipts |
| an irreversible action names a gate | that the gate was honoured; that is the job of a hook or a flow kernel |
| the statement matches the base | who wrote the base; a base the performer committed alone proves only that the statement did not drift |
| a prediction carries a date | that it was written before the outcome was known |

**Fields that only have to be present.** The checker requires these and cannot
judge what they say, so any text satisfies it: `problem`, `domain`, the `text`
of a claim or an action, `rubric`, `pass_rule`, `sensor`, `positive_control`,
`falsification_criterion`, `scored_by`, `reach`, `undo`, `receipt.revision`,
the `replay` of a receipt outside the proof and replay rungs, the two ends of
a `feeds` hop, `learning.on_correction`, every `unverified` entry and
`nothing_unverified_because`. They exist so a reader can judge them. A review
of the statement, by someone other than its writer, is what gives them weight.

The index was tagged from each skill's description, not its code.

## Anti-rationalization

| Excuse | Reality |
|---|---|
| "The agent explained why it is correct." | An explanation is not a check. Put the claim on a rung or in `unverified`. |
| "The same model reviewed it and agreed." | C4. Agreement from the performer's own origin adds nothing. |
| "The check passed." | Did its known-bad case fail? `replay` says INVALID when it did not. |
| "I'll tighten the claim now that I see the result." | C1. A claim changes on the base, before the work, not after it. |
| "Nothing is unverified." | Then say why, in `nothing_unverified_because`. It is rarely true. |
| "It is only a small irreversible step." | Reach, not size, sets the gate. |

## Verify

From the root of this repository:

```bash
python3 -m pytest skills/governance/checkable/tests -q
python3 skills/governance/checkable/scripts/checkable.py index --require-roster
python3 skills/governance/checkable/tests/mutate.py
python3 skills/tooling/skillify/scripts/skillify_check.py skills/governance/checkable --run-tests
```

`tests/mutate.py` changes the checker one place at a time: it removes each
refusal, negates each `if` condition, replaces each pattern with one that
matches anything, and makes each yes-or-no validator permissive. It counts a
mutant as killed only when a test fails, and any other pytest status as an
error. It does not change operators inside a condition, comprehension filters,
default arguments or the tables of allowed values.
