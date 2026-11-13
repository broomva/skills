---
name: first-principles-sim
tier: D
category: simulation
version: 0.1.0
description: >-
  Build a simulation in which the thing you see or hear is never drawn: model
  the mechanism (source, medium, interaction, state, observation), let the
  phenomenon come out of it, and check each stated quantity against something
  computed outside the model. For setups with known laws and at least one
  measured or derived quantity: particle detectors, fluids, heat, sound and
  instruments, optics, orbits, circuits, reaction-diffusion, neurons,
  structures. Every claim goes in a ledger (sim-claims.yaml) as reference,
  independent, conservation, control, prediction, convention or omitted, and
  scripts/sim_audit.py checks the ledger: the tests are green and every test
  file asserts, every reference table carries its source and date and is read
  by a test, every number the ledger quotes appears in the docs and in the
  report command's output, and each listed small code change turns a test
  red. USE WHEN: "simulate X from physics", "from first principles",
  "physically accurate", "make it emerge, don't fake it", "like rauchg's
  vinyl", "a realistic simulation of", "verify the simulation against real
  data", "audit this simulation", or building an explainer whose picture or
  sound must be a consequence of the model. NOT FOR: stylised effects where
  faking is the right call (game feel, a shader that only has to look good),
  policy or ontology rollouts (parallax), data-fitted or learned surrogates,
  or driving an existing solver (openrocket-sim).
---

# first-principles-sim: model the mechanism, let the phenomenon emerge, prove the numbers

A simulation that looks right is evidence that it looks right. This skill is for building one
where the picture or the sound is a consequence of the model, and where each number the package
states is enforced by a check that can fail.

It comes from two artifacts. [rauchg/vinyl](https://github.com/rauchg/vinyl) gets a record
player's crackle and wow from simulated groove geometry, with no audio effects. Its tests print
numbers and assert nothing. The cloud chamber in `broomva/workspace` (`packages/cloud-chamber`)
applied the same idea to ionizing radiation and added the checks. One of those checks found a
bug the picture hid. Two rounds of independent review then each found defects that the author's
own green tests had hidden. This skill is that method, with those defects turned into a gate.

## The rule

Name the phenomenon, then never write code that draws it. In the cloud chamber nothing draws a
track: particles lose energy, ions seed droplets, droplets grow and fall, and the renderer plots
droplets. If a `drawTrack` function exists, the simulation is an animation.

## The arc

Read [references/method.md](references/method.md) before starting; it has the reasoning and the
cloud-chamber example for each step. For a field other than particle physics, read
[references/domains.md](references/domains.md) for the mechanism chain and the anchors to check.

1. **Decide whether it fits.** You need a mechanism with known laws and at least one quantity
   someone has measured or derived. If neither exists, say so and stop: the result would be an
   animation with equations in it.
2. **Name the phenomenon and the chain.** Write what must emerge, and the stages that produce
   it: source, medium, interaction, state, observation. One file per stage. Each stage is a
   pure function of its inputs and, where it draws random numbers, a seed. In a time-stepped
   field solver the source is the initial condition and the forcing, and the interaction is
   the update rule. SI units throughout; every constant has a source.
3. **Open the ledger before the code.** Copy `assets/example/falling-body/sim-claims.yaml` into
   the package. Give every quantity you intend to state one claim and one kind (table below).
   Fetch the reference tables now and store them with their URL and fetch date.
4. **Build bottom-up, one stage at a time, with its check.** Do not start a stage until the
   one below it passes against its anchor. A wrong stopping power makes every track wrong, and
   the track will not tell you.
5. **Observe without drawing.** The renderer or the audio output reads state and nothing else.
   Then measure the output itself, headless, against the same anchors: a track's length in
   pixels against the published range, a tone's pitch against the frequency that the string's
   length, tension and mass per length give.
6. **Add the negative controls.** Remove the cause and require the effect to vanish: no
   radiation, a black frame. Read the result after the slowest relevant process has had time
   to act, or the control passes because nothing has happened yet.
7. **Write the report command.** It prints every number the prose quotes. Quote nothing else,
   and quote the digits it prints.
8. **Write a mutation for each checked claim.** A small change to the code under test, usually
   one line, that makes the claim false. The test must go red. If it stays green, the test checks something
   other than the claim. The audit warns for each checked claim that has none.
9. **Run the audit.**

   ```bash
   python3 scripts/sim_audit.py <package> --run-report --run-mutations
   ```

   Exit 0 means no check failed. `--strict` also fails on warnings and on anything not run. A
   run that was not requested reports SKIP, never PASS. Add `--run-gates` to run the checks
   listed under `tests.gates`. A YAML ledger needs PyYAML; a `sim-claims.json` one does not.
10. **Vary what should not matter.** Shift every random seed and run the tests again. For a
    deterministic solver, halve the step and the grid spacing instead: the error against the
    anchor must fall at the order the scheme promises.
11. **Get an independent review** (cross-review, P20) on a copy of the tree. Fix each finding by
    checking the claim against something computed another way, or by narrowing the claim.
12. **Write the three tables** in the README from the ledger: what is checked against what, what
    the model predicts and is not compared with a measurement, and what is approximated or left
    out.

## Claim kinds

| Kind | What enforces it | Needs |
|---|---|---|
| `reference` | A published table or value | `test`, and `reference` (a stored table) or `source` (a citation) |
| `independent` | The same quantity computed another way: brute force against a closed form, quadrature against sampling | `test` |
| `conservation` | A conservation law or an identity of the equations | `test` |
| `control` | A null input that must give a null output | `test` |
| `prediction` | Nothing. A model result with no measurement to compare | `statement` |
| `convention` | Nothing. A choice or a typical value | `statement` |
| `omitted` | Nothing. Physics left out | `statement` |

A claim's `test` is a file the test command runs, or a file listed under `tests.gates` with
its own command (a check run separately, such as a headless render). A mutation's `file` is
code under test: not a test, not a gate, and nothing in the tests directory.

Give each mutation the `command` that runs only its claim's test. With the whole suite as the
command, whichever assertion fails first kills the mutation, and it may belong to another
claim. The example package has one test file per claim for this reason.

A ledger must hold at least one control, one `reference` or `independent` claim, one
`convention` or `omitted` claim, and one mutation. A package where every check is the model
agreeing with itself has no anchor, and a model with nothing left out is misdescribed.

When the laws are themselves models (an agent-based market, a flocking rule), most claims will
be predictions and conventions. That is the honest result. Say it in the README.

## What the audit checks, and what it cannot

| It checks | It cannot check |
|---|---|
| The test command exits 0 in a copy of the package | That the tests test anything. Only mutations show that |
| Every test file contains an assertion | That the assertion is about the claim |
| A reference file has a URL and a date, and code beside the tests names the file | That the table was copied correctly, that it is the right table, or that the code which names it also uses it. A test that loads tables by listing a directory must still name each file |
| A string the ledger quotes appears in the docs and in the report's standard output | Numbers in the docs that the ledger does not list. And a short string such as `1.1` matches by accident; quote enough digits or the unit |
| A mutation turns its test command red | That it died for the right reason. A mutation that breaks the code outright kills any test, a test that fails for another reason also kills it, and nothing checks that the command runs the claim's `test` file |
| With `--run-gates`, each gate's command exits 0 | Without the flag, anything about a gate beyond the file existing and asserting. It reports SKIP |
| The ledger has a control, an anchor, a limit and a mutation | That an `independent` check really is. A closed-form solution of the equation being solved verifies the solver, not the physics both sides assume |
| A checked claim has a mutation (a warning if not) | That the prose labels predictions as predictions |

Three more limits:

- **The package must run from a copy of its own directory.** Commands run in a temporary copy,
  so tests that import a sibling package fail there. The `suite` check says so when it happens.
- **Linked directories are shared.** `node_modules`, `.venv`, `venv` and `target` (or the
  names under `link`) are symlinked into the copy, so a command that writes a cache there
  writes into the real one. The audit refuses a mutation inside a linked directory. If one of
  those names holds your source, set `link` in the ledger.
- **The assertion detector is a list of patterns.** It strips comments for the languages it
  knows but does not parse strings, and it counts `throw`, `raise` and a non-zero `exit` as
  ways to fail. For a framework it does not know, set `tests.assertion` in the ledger.

These are what the review in step 11 is for.

## Failures this skill exists to prevent

Each of these happened in the cloud-chamber build. The first was caught by a reference test
when that test was written. The rest were found with the suite green, by review or by
regenerating a number. The plate-limit row happened in a draft, before the first commit, so the
repository does not record it. The last column is the kind of check that catches each one; the cloud
chamber's own ledger does not yet have a mutation for every row.

| What was written | What was true | What catches it |
|---|---|---|
| A rotation with a special case near the vertical axis | It discarded accumulated deflection; steep tracks came out too straight, and the picture looked fine | A reference claim: scattering width against the Highland formula |
| A test of the water nucleation threshold | It tested a formula the simulation never calls | A mutation of the function the engine calls |
| Two "brute-force" tests | They retyped the engine's formula; doubling its coefficient left them green | A mutation of the coefficient |
| A black-frame control over a warm plate | The frame was read before droplets could have appeared | Reading the control after the slowest timescale |
| A plate limit typed into a draft README from an expectation | The report, once it existed, printed a different number | `quoted`, with `--run-report` |
| Landing times "for droplets" | They were counted over array entries, each standing for about 15 droplets | A conservation claim on the weighted count |
| "Every test asserts against a published reference" | Several check consistency, not a reference | The kind column of the ledger |
| A three-pass iteration for the inertia cap | It does not converge; the heaviest columns got no downdraft | An independent claim: bisection of the same equation over the whole range |

## Composition

| Step | Composes |
|---|---|
| Independent review | `cross-review` (P20) |
| Exercising the built page as a user | `dogfood` (P11) |
| Filing what was learned | `bookkeeping` (P6) |
| Waiting on CI | `p9` |

## Validation

```bash
python3 -m pytest tests/ -q        # the audit against a small package, one fault at a time
python3 tests/run_mutants.py       # the audit's own tests against changes to the audit
```

`assets/example/falling-body` is a complete package that passes the audit with `--strict`. The
tests copy it, break one thing at a time, and check that the audit names it.

`run_mutants.py` holds the audit to its own rule, more strictly than the audit holds a
simulation. It generates changes to `scripts/sim_audit.py` from the source (every single-line
condition forced true and false, every failure, warning and skip reported as a pass, every
assertion pattern removed, every element of a constant list removed), adds a hand-written
list for what those cannot express, and requires the tests to fail for each one. A survivor
must be listed with the reason it changes nothing. It cannot tell a mutant that a test caught
from one that died because the change raised an exception.

The cloud chamber's ledger is the real-data case. On 2026-11-13 the audit killed nine of its
eleven mutations and reported two survivors, both gaps in that package's tests (see
[references/method.md](references/method.md)).
