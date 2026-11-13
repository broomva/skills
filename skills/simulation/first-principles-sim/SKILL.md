---
name: first-principles-sim
tier: D
category: simulation
version: 0.1.0
description: >-
  Build a simulation in which the thing you see or hear is never drawn: model
  the mechanism (source, medium, interaction, state, observation), let the
  phenomenon come out of it, and prove each stated quantity against something
  computed outside the model. Works for any setup with known laws: particle
  detectors, fluids, heat, sound and instruments, optics, orbits, circuits,
  reaction-diffusion, neurons, structures. Every claim goes in a ledger
  (sim-claims.yaml) as reference, independent, conservation, control,
  prediction, convention or omitted, and scripts/sim_audit.py checks the
  ledger: every test asserts, every reference table carries its source and
  date and is read by a test, every quoted number is printed by the report
  command, and each listed one-line code change turns a test red. USE WHEN:
  "simulate X from physics", "from first principles", "physically accurate",
  "make it emerge, don't fake it", "like rauchg's vinyl", "a realistic
  simulation of", "verify the simulation against real data", "audit this
  simulation", or building an explainer whose picture or sound must be a
  consequence of the model. NOT FOR: stylised effects where faking is the
  right call (game feel, a shader that only has to look good), policy or
  ontology rollouts (parallax), data-fitted or learned surrogates, or driving
  an existing solver (openrocket-sim).
---

# first-principles-sim: model the mechanism, let the phenomenon emerge, prove the numbers

A simulation that looks right is evidence that it looks right. This skill is for building one
where the picture or the sound is a consequence of the model, and where each number the package
states is enforced by a check that can fail.

It comes from two artifacts. [rauchg/vinyl](https://github.com/rauchg/vinyl) gets a record
player's crackle and wow from simulated groove geometry, with no audio effects. Its tests print
numbers and assert nothing. The cloud chamber in `broomva/workspace` (`packages/cloud-chamber`)
applied the same idea to ionizing radiation and added the checks. One of those checks found a
bug the picture hid, and two rounds of independent review each found defects that the author's
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
   pure function of its inputs and a seed. SI units throughout; every constant has a source.
3. **Open the ledger before the code.** Copy `assets/templates/sim-claims.yaml` into the
   package. Give every quantity you intend to state one claim and one kind (table below).
   Fetch the reference tables now and store them with their URL and fetch date.
4. **Build bottom-up, one stage at a time, with its check.** Do not start a stage until the
   one below it passes against its anchor. A wrong stopping power makes every track wrong, and
   the track will not tell you.
5. **Observe without drawing.** The renderer or the audio output reads state and nothing else.
   Then measure the output itself, headless, against the same anchors: a track's length in
   pixels against the published range, a tone's pitch against the string's length.
6. **Add the negative controls.** Remove the cause and require the effect to vanish: no
   radiation, a black frame. Read the result after the slowest relevant process has had time
   to act, or the control passes because nothing has happened yet.
7. **Write the report command.** It prints every number the prose quotes. Quote nothing else,
   and quote the digits it prints.
8. **Write a mutation for each checked claim.** One line of the code under test, changed so the
   claim becomes false. The test must go red. If it stays green, the test checks something
   other than the claim.
9. **Run the audit**, then shift every seed and run the tests again.

   ```bash
   python3 scripts/sim_audit.py <package> --run-report --run-mutations
   ```

   Exit 0 means no check failed. `--strict` also fails on warnings (a checked claim with no
   mutation). A run that was not requested reports SKIP, never PASS.
10. **Get an independent review** (cross-review, P20) on a copy of the tree. Fix each finding by
    checking the claim against something computed another way, or by narrowing the claim.
11. **Write the three tables** in the README from the ledger: what is checked against what, what
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

A ledger must hold at least one control, one `reference` or `independent` claim, and one
`convention` or `omitted` claim. A package where every check is the model agreeing with itself
has no anchor, and a model with nothing left out is misdescribed.

When the laws are themselves models (an agent-based market, a flocking rule), most claims will
be predictions and conventions. That is the honest result. Say it in the README.

## What the audit checks, and what it cannot

| It checks | It cannot check |
|---|---|
| Every test file contains an assertion | That the assertion is about the claim. Only a mutation shows that |
| A reference file has a URL and a date, and a test reads it | That the table was copied correctly, or that it is the right table |
| A quoted string appears in the docs and in the report output | That the report computes it correctly. A short string such as `1.1` matches by accident; quote enough digits or the unit |
| A mutation turns its test command red | That the test is right. A test that fails for another reason also kills the mutation |
| The ledger has a control, an anchor and a limit | That the prose labels predictions as predictions |

The assertion check strips comments but does not parse strings, and it counts `throw` and
`raise` as ways to fail. The independence of an `independent` claim is not decidable: a test
that retypes the formula it tests passes this audit until a mutation of that formula is listed.
That is what the review in step 10 is for.

## Failures this skill exists to prevent

Each of these happened in the cloud-chamber build, with the suite green.

| What was written | What was true | The check that catches it |
|---|---|---|
| A rotation with a special case near the vertical axis | It discarded accumulated deflection; steep tracks came out too straight, and the picture looked fine | A reference claim: scattering width against the Highland formula |
| A test of the water nucleation threshold | It tested a formula the simulation never calls | A mutation of the function the engine calls |
| Two "brute-force" tests | They retyped the engine's formula; doubling its coefficient left them green | A mutation of the coefficient |
| A black-frame control over a warm plate | The frame was read before droplets could have appeared | Read the control after the slowest timescale |
| A plate limit of -5.7 °C in the README | The report printed -8.4 °C; the number had been typed from memory | `quoted`, with `--run-report` |
| Landing times "for droplets" | They were counted over array entries, each standing for 15 droplets | A conservation claim on the weighted count |
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
python3 -m pytest tests/ -q
```

The tests build a small falling-body package in a temp directory, break one thing at a time,
and check that the audit names it. The cloud chamber's own ledger is the real-data case: at
0.1.0 the audit kills nine of its eleven mutations and reports two survivors, both gaps in that
package's tests (see [references/method.md](references/method.md)).
