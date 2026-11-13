# The method, step by step

Each step below says what to do, why, and what it looked like in the cloud chamber
(`packages/cloud-chamber` in `broomva/workspace`). Read the whole file once before starting a
new simulation.

## 1. Does it fit?

The method needs two things:

- **A mechanism with known laws.** Energy loss in matter, diffusion, Newton's laws, Maxwell's
  equations, reaction kinetics. If the "law" is something you would invent for this project,
  the output is your invention.
- **An anchor.** At least one quantity that someone measured or derived independently of your
  code: a table, a formula with a stated accuracy, an analytic solution.

It does not fit when a convincing look is the whole goal. A game's water does not need to
conserve mass. Faking is cheaper there and nobody is misled.

## 2. The phenomenon and the chain

Write one sentence naming what a viewer will see or hear. That is the phenomenon, and no code
may produce it directly.

Then write the chain of stages that produces it. Most physical setups have the same five:

| Stage | Question | Cloud chamber | vinyl |
|---|---|---|---|
| Source | What enters, at what rate, with what spectrum? | Cosmic muons, radon alphas, gamma-ray electrons | The cut groove: audio turned into wall displacement |
| Medium | What state is the stage in before anything happens? | Temperature and vapor profile between plate and top | The pressed disc: roughness, dust, warp |
| Interaction | What does the source do to the medium, event by event? | Energy loss, scattering, knock-on electrons, ion pairs | Stylus contact on two walls, with friction |
| State | What evolves afterwards? | Droplets nucleate on ions, grow, fall | Tip position and velocity, platter speed |
| Observation | What does the instrument report? | Light scattered by droplets into a camera | Cartridge voltage, then the preamp chain |

Rules for the code:

- One file per stage. A stage imports only the stages below it.
- Each function is a pure function of its arguments and a seeded random generator. The same
  seed gives the same output, element for element. Test that.
- SI units inside. Convert at the edges, and name the unit in a comment where a table uses
  another one.
- Constants live in one place, each with its source.

## 3. The ledger comes first

Before writing a stage, list what you intend to state about it and how each statement will be
enforced. This is `sim-claims.yaml`. Writing it first changes what you build: a quantity with
no possible anchor gets labelled a prediction on day one, and the README inherits that label.

Fetch reference tables at this point:

- Download the table. Do not type numbers from memory or from a search snippet.
- Store it under `test/reference/` with a header giving the URL and the fetch date.
- Tests parse the file. A value typed into a test can drift from the table without anyone
  seeing it.
- A single scalar with a citation (a textbook value, a formula's stated accuracy) may be typed
  into the test. The ledger then carries `source:` in place of `reference:`.

In the cloud chamber: NIST ASTAR, PSTAR and ESTAR tables, the PDG muon table and the IAEA beta
energies are stored files. The Highland formula and the vapor-pressure points are cited values.

## 4. Bottom-up, each stage with its check

Order matters because errors compound upward and the picture hides them. Check, in this order
of preference:

1. **Reference.** The stage's output against a published table, at a stated tolerance.
2. **Independent.** The same quantity computed another way. Sampling against quadrature. A
   closed-form shortcut against a brute-force numerical solution. The second method must not
   share the first one's formula; if you could copy and paste between them, it is not
   independent.
3. **Conservation.** Mass, energy, charge, particle number, or an identity of the equations.
   These catch bookkeeping errors and say nothing about whether the physics is right.

**Pinned tolerances.** When the model has a known bias (the cloud chamber's beta energies are 3
to 6% high because its Fermi function is non-relativistic), assert it from both sides: above 3%
and below 6%. Then neither a regression nor a silent improvement passes unnoticed.

**Validity ranges.** For each formula, work out the dimensionless number that governs it
(Reynolds, Knudsen, the ratio of step to mean free path) at the conditions the simulation
actually reaches, and print it in the report. The cloud chamber's first settling law ignored
inertia; the Reynolds number of an alpha column showed the law did not apply.

**Scale tricks are claims.** If one array entry stands for many particles, or a time step
merges many collisions, that is a convention, and totals must still be counted in real units.
The cloud chamber counted landing times over array entries when the claim was about droplets.

## 5. Observation

The renderer reads state. It has no access to the source list and no notion of a track, a
wave or a note. Then test the output, not only the state:

- Render headless, at fixed seed, and measure. The cloud chamber's render gate finds the lit
  pixels of an alpha track and compares their extent with the ASTAR range.
- State the limits of the picture. A point sprite 0.9 mm wide draws a 25 µm track as 0.9 mm.
  That goes in the ledger as a convention.

For sound, the same applies: measure the pitch, the decay time or the spectrum of the rendered
samples, and compare with the anchor.

## 6. Negative controls

A control removes the cause and requires the effect to vanish. Without one, a renderer that
always draws something passes every positive test.

Two rules:

- **Wait long enough.** Read the control after the slowest process that could produce the
  effect. The cloud chamber's warm-plate frame was first read before any droplet could have
  appeared, so it was black for the wrong reason.
- **Check exact nulls exactly.** Black means every channel of every pixel is zero. Silence
  means every sample is zero.

## 7. The report command

One command prints every number the prose quotes, each on a labelled line. The prose quotes
the digits it prints. The audit's `quoted` check ties the two together: the string must appear
in the docs and in the report output.

This exists because of one error. A README sentence gave a plate limit of -5.7 °C. The report,
when it was written and run, printed -8.4 °C. The first number had been typed from an
expectation.

## 8. Mutations

A test file that asserts is not the same as a claim that is enforced. The cloud chamber had a
test for the water nucleation threshold that passed, and tested a function the engine never
called. It had two brute-force tests that retyped the engine's formula.

A mutation settles it. Change one line of the code under test so that the claim becomes false,
and run the test:

```yaml
mutations:
  - id: old-column-offset
    claim: downdraft-viscous
    file: src/engine.ts
    find: "export const COLUMN_OFFSET = 0.45"
    replace: "export const COLUMN_OFFSET = 0.84"
    command: "bun test test/engine.test.ts --timeout 60000"
```

Good mutations:

- Change the thing the claim is about, by more than the tolerance and not absurdly more. A 1%
  shift against a 0.3% tolerance is a better mutation than a factor of ten.
- Reintroduce a bug you fixed. The cloud chamber's `old-rotation` mutation restores the
  near-axis special case.
- Bypass a call. `engine-skips-cap` replaces the capped downdraft with the uncapped one, to ask
  whether anything checks that the engine uses the function its unit test verifies.

Avoid equivalent mutations: flipping the sign of an azimuth drawn uniformly from a full circle
changes nothing statistically, and its survival means nothing.

The audit applies each mutation in a temporary copy of the package and never edits the live
tree.

### What the first real run found

Run against the cloud chamber at 0.1.0, the audit killed nine of eleven mutations and two
survived the whole suite:

- `engine-skips-cap`: no test fails when the engine ignores the inertia cap. The cap's own
  unit test passes because it calls the function directly.
- `double-mist`: the mist test reads a closure figure computed from an intermediate variable.
  Doubling the output array, which is what the engine reads, leaves it at 1.

The first was already an open finding from the third review round. The second had passed all
three rounds.

## 9. Seeds

Run the suite with every seed shifted, several times. A statistical test that passes at one
seed may be passing by luck, and a tolerance set by looking at one run is too tight. The cloud
chamber reads `CHAMBER_SEED_SHIFT` and runs the suite eight times.

## 10. Independent review

The author's tests agree with the author's code because one understanding produced both. A
reviewer with a different model, and no access to the author's reasoning, reads the claims
against the code. Give reviewers a copy of the tree: asked to verify, they will edit what they
are pointed at.

For each finding there are two honest fixes:

- Make the test exercise the claim against something computed another way.
- Narrow the claim to what is checked.

Rewording the claim so the existing test covers it is the second fix, and is fine. Adding a
test that restates the code is neither.

## 11. The README

Three tables, generated from the ledger by hand:

- **What is checked against what:** quantity, reference, agreement asserted, test.
- **What the model predicts:** each `prediction`, with the sentence "none is compared with a
  measurement".
- **What is approximated, and what is left out:** each `convention` and `omitted` claim.

## In CI

Pin the runtime version. Give statistical tests a timeout that fits the slowest runner. Run the
audit with `--run-report --run-mutations` once the package passes it; until then, the survivors
are tickets.
