---
name: skillify
tier: D
category: tooling
description: >-
  Skillify-as-a-verb — distill a working session (or a pointed-at chat history)
  into a permanent, TESTED, registered skill at the end of a workflow. The
  bstack-native composition of Garry Tan's 10-step "skillify it": look-back
  extraction → CreateSkill scaffold → latent/deterministic split → unit tests →
  resolver-eval (role-x.py eval) → script-test gate (bstack skills audit
  --require-tests) → P20 cross-review → bookkeeping file. Composes existing
  primitives; reimplements nothing. The deterministic core (scripts/skillify_check.py)
  makes "a feature that doesn't pass all ten is not a skill" machine-checkable, per
  TIER: D (deterministic — tests + mutation), J (judgment — admission test, rubric,
  held-out cases, cross-model judge, measured agreement floor), or L (lens — a
  both-polarity routing eval). A skill with no pure function is not exempt from
  gating; it is gated on a different axis.
  USE WHEN: "skillify it", "skillify this", "package this as a skill", "distill
  this into a skill", "make this a skill", "turn this into a skill", or at the
  end of an ad-hoc workflow that worked and should become permanent. NOT FOR:
  ingesting an external artifact (use /checkit); retrospective "what have I done
  repeatedly" discovery alone (use the look-back lens); a one-off task with no
  reusable procedure.
---

# skillify — turn a working session into a tested, permanent skill

`/skillify` is the **verb** at the end of a workflow. You built something ad-hoc
in conversation, it worked, and you want it to be permanent — not a screenshot
in a chat log, but a skill a future agent reaches for automatically. Saying
"skillify it" runs the distillation.

It is a **composition skill** — like `/checkit` and `/autonomous`, it fires
existing primitives in sequence. It does **not** reimplement scaffolding, tests,
the resolver, or filing. Its deterministic core (`scripts/skillify_check.py`) is
the *gate*, not a reimplementation of the pieces.

## The one rule

> **A feature that doesn't pass all ten is not a skill. It's just code that
> happens to work today.**
>
> *All ten, for its tier.* What "passing" means differs for a lint, a critique,
> and a lens — but "there is no gate for this kind of thing" is never one of the
> three answers. See **Tiers** below.
>
> Every failure or hard-won ad-hoc workflow becomes a *tested* skill, so the
> bug becomes structurally unreachable and the procedure becomes permanent
> infrastructure. The latent space *builds* the deterministic tool; the
> deterministic tool then *constrains* the latent space.

## Tiers — what kind of thing this skill is

The gate used to ask one question: *is there a deterministic core?* Yes → test it.
No → set `latent_only: true` and nothing is checked at all. That is a **testability
question standing in for an expressibility question**, and the roster falsifies it.
Run the sweep:

```
python3 scripts/skillify_check.py --survey skills/
```

At the commit that introduced this section it reported **94 skills, 44 of them
unclassified** — every one ships no `scripts/` code, and the old gate called every one
"not a skill yet, just code that works today". It was wrong about all 44. Re-run it;
the number is whatever the roster now says, which is the point of shipping a command
rather than a sentence.

Worse, the **2** skills that took the `latent_only: true` exemption bought their way
out of steps 2 **and** 3, and were then gated on nothing at all. The binary did not
merely misclassify judgment skills; on the side it was built to accommodate, it was an
amnesty.

> **Reproducibility note.** The *absolute* pass count moves by one depending on whether
> `node` is installed, because step 2's `.ts` syntax check is skipped when it is not
> (`keel` passes without node, fails with it). The **delta** is what this change claims
> and it is invariant: old gate → new gate is **−2 passing** with node present (28 → 26)
> and with node absent (29 → 27). Both losses are the two `latent_only` skills. Quote
> the delta, not the absolute.

Three tiers replace the binary. **Declare one in frontmatter** (`tier: D`). Only **D**
is inferred, from shipped code; **J and L must be declared** (see below for why).

| Tier | What it is | What the gate requires |
|---|---|---|
| **D** — deterministic | there is a pure function in here (`unslop_gate.py`; a lint) | `scripts/` + real unit tests (a mutation proof is required discipline, but is **not** machine-checked — the gate cannot see one) |
| **J** — judgment | a well-posed question whose valid answers vary (`critique`, `impeccable`, `devils-advocate` — all installed globally, none in this monorepo) | the admission record, a rubric, a held-out case set, a **cross-model** judge config, and a floor carrying its own measurement |
| **L** — lens | it changes what you attend to, not what you do | a routing eval in **both polarities** — fires on the right requests, stays silent on near-misses |

A skill is often more than one thing. Declare the tier whose gate is **hardest** for
it: `skillify` is **D** because it ships `skillify_check.py`, even though most of its
body is procedure.

`latent_only: true` is **deprecated**. It still parses, and it still means "not tier
D" — but it no longer buys an exemption from everything else. A `latent_only` skill
must now satisfy J or L.

### Why the cheap option won, and why it is still the wrong one

Tier J's gate is expensive in exactly two ways the deterministic gate is not, and
both are the reason the binary existed:

1. **The judge is probabilistic too.** A judge sharing the generator's substrate
   inflates confidence rather than testing it, so **cross-model judging is structural
   for J, not an upgrade**. The harness already encodes this: the LLM-judge seam in
   `skill_evals/checks.py` (repo root) requires "a grader model distinct from the model
   under eval" and *raises* rather than returning a permissive stub.
2. **It rots silently and it costs tokens.** A Tier-J skill degrades with nothing
   going red, and per-run spend rules out firing on every commit. J belongs on a
   **cadence** (P7 freshness), not in **per-commit CI** (P4).

Those two costs are the whole reason the gate defaulted to deterministic-or-nothing.
That default was the *cheap* option, not the *right* one — say so out loud. The tier
model does not make J cheap. It makes J expressible and its debt visible.

### The admission test — the hard gate for J

**Non-deterministic ≠ underspecified**, and only the first is admissible.

> **Admission test.** Given this skill and the *same* input, can two independent
> agents produce outputs that a competent third party judges **both valid**?
> If the outputs contradict and nothing adjudicates, the skill is **underspecified**.
> Reject it — that is not a judgment skill, it is a question that was never pinned down.

- *Well-posed probabilistic* — "Critique this design." Two critiques differ; both are
  defensible; a reader can grade each on the rubric.
- *Underspecified* — a classifier whose branch depends on a parameter the skill never
  names, so both answers are "correct" only because the question moved underneath
  them. This is the concrete case that produced these tiers; the four-round record is
  in `research/notes/2026-08-19-recall-dressed-as-a-sweep-postmortem.md`.

A Tier-J skill records the admission test **and its outcome** in `evals/admission.md`.
The gate requires that record: an unrecorded admission test is an unadmitted skill.

### The agreement floor is deliberately unset

Tier J requires an inter-judge agreement floor. **This skill does not tell you what
the floor is**, because nobody has measured it — and asserting a threshold that no
committed process regenerates is exactly the failure documented in the post-mortem
that produced this tier model.

So the gate enforces the *shape* instead of a number: a Tier-J skill must declare
`judge.agreement_floor` **and** carry `judge.agreement_measured` recording the value,
the method, and the date that produced it. A floor declared with no measurement is a
**FAIL**, not a warning. Pick your own floor; show your work.

### What this gate cannot check, and does not pretend to

Two adversarial review rounds spent most of their findings on one question: *can the
gate tell a real artifact from a convincing fake?* The answer is **no, and no static
gate can.** Whether a rubric was thought about, whether forty cases were really
dual-labelled, whether the admission test actually ran — none of that is recoverable
from the bytes on disk. A gate that claims otherwise invites an arms race it loses
every round, one plausible-looking placeholder at a time.

So the boundary is stated rather than blurred:

| The gate checks | The gate cannot check |
|---|---|
| the artifacts exist, parse, and are structurally complete | that they describe something that happened |
| the judge model differs from every declared model under eval | that the judge was ever run |
| the floor is a finite number carrying a `value` + `method` | that the measurement produced *that* floor |
| the case has an input and is not a placeholder | that the case is a good case |
| a script has a non-comment line | that the code does anything useful |

The placeholder checks (`TBD`, `vibes`, `not measured`, …) are a **typo-catcher, not
an authenticity gate.** They catch a field someone forgot to fill in. They do not catch
a field someone filled in falsely, and they are not meant to. That judgement belongs to
the **P20 review layer**, where a human or a second model reads the artifact — and
pretending a regex can do it would be exactly the vacuity this whole gate exists to
prevent.

### Neither J nor L has a real user yet

`--survey skills/` reports **zero** tier-J and **zero** tier-L skills. Both gates ship
exercised only by their own test fixtures. That is worth stating rather than
discovering later: the measured behavioural change of introducing tiers is exactly two
skills moving from pass to fail, and everything else here is a contract waiting for its
first artifact. The residue ticket (BRO-2192) is the reason — the roster's uncarved 44
are procedures, not judgments or lenses.

### What Tier J does *not* yet have

The judge itself is **unbuilt**. `make_judge_check` in `skill_evals/checks.py` (repo root)
is a declared seam that raises, on the stated grounds that a permissive stub is worse
than an honest gap. The tier gate therefore checks that a J skill's **artifacts** are
present, well-formed, and cross-model by construction — and reports the judge *run*
as a SKIP naming that seam. It never reports it as a PASS. A tier that certified
itself through an unimplemented judge would be the vacuity this whole gate exists to
prevent.

## The 10 steps (bstack-native)

| # | Skillify step | bstack mechanism (composed, not reimplemented) |
|---|---|---|
| 1 | SKILL.md contract | **CreateSkill** scaffold → name + description + triggers |
| 2 | Tier + its core | declare `tier: D\|J\|L`; ship that tier's core — `scripts/` for D, the admission record + rubric + held-out cases + cross-model judge config for J, a both-polarity routing eval for L |
| 3 | Unit tests | `tests/test_*.py` (vitest/pytest) on the deterministic core |
| 4 | Integration tests | live-endpoint / real-data tests where applicable |
| 5 | LLM evals | trigger-surface grading (all tiers, recommended); tier J's rubric + held-out cases + cross-model judge are gated in **step 2** |
| 6 | Resolver trigger | a `roles/<name>.md` lens (**P17**) and/or registry entry |
| 7 | Resolver eval | **`role-x.py eval`** + `roles/<name>.eval.yaml` (BRO-1411 slice 1) — *assert the trigger actually routes* |
| 8 | Check-resolvable + DRY | **`bstack skills audit`** (reachability + duplicate + budget) |
| 9 | E2E smoke test | the full path runs end-to-end, agent invokes the script vs winging it |
| 10 | Brain filing rules | **`/bookkeeping`** (P6) — file the KG entity + provenance |

The script-test *gate* (steps 3/4) is enforced registry-wide by
**`bstack skills audit --require-tests`** (BRO-1411 slice 2).

## Pipeline (what `/skillify [target]` does)

`target` defaults to the **current session**; it can also be a
`docs/conversations/<id>.md`, a pasted history, or an existing skill dir to
audit.

1. **Extract** (compose `look-back`) — what recurred, what's the reusable
   procedure, and which parts are *deterministic* (precision → script) vs
   *latent* (judgment → markdown). State the latent/deterministic split in one
   line before scaffolding.
2. **Scaffold** (compose **CreateSkill**) — `SKILL.md` contract: `name`,
   `description` with explicit USE WHEN / NOT FOR triggers, the procedure.
3. **Build the tier's core** — **D**: write `scripts/*` for the precision work.
   **J**: write `evals/admission.md` (the admission test and its outcome), the
   rubric, the held-out case set, and a judge config whose model differs from the
   model under eval. **L**: write the both-polarity routing eval. Declaring a tier
   whose core you did not ship is the one thing the gate will not let you do.
4. **Test** — `tests/test_*` on the scripts; run them green before anything else.
5. **Resolver** (compose **P17** + slice 1) — add a `roles/<name>.md` lens and a
   `roles/<name>.eval.yaml` fixture; `role-x.py eval --lens <name>` must pass.
6. **Audit** (compose slice 2) — `bstack skills audit --require-tests` clean;
   no duplicate/dark-skill collision.
7. **Review** (compose **P20**) — cross-model adversarial gate ≥7/10 before it lands.
8. **File** (compose **P6**) — `bookkeeping` entity + provenance; never ask
   permission, file then report.
9. **Publish** — a skill lives in the **`broomva/skills` monorepo** under
   `skills/<name>/SKILL.md` (the agentskills.io layout), **not** a new standalone
   repo. New skill → add under `broomva/skills/skills/<name>/`; an existing
   standalone → `bstack skills graduate <name> --stub` (copies into the monorepo,
   redirect-stubs the standalone). Add the README table row + a `test-<name>.yml`
   CI workflow. Canonical install: `npx skills add broomva/skills --skill <name>`.
   *(Standalone repos are the deprecated pattern — see `research/entities/tool/skills-sh.md`.)*
10. **Dogfood the install (skills.sh E2E)** — the skill is not done until a user
    can install it. Run the non-mutating parse check first, then the real install,
    then confirm discovery:
    - `npx skills add broomva/skills --skill <name> --list` → the skill is listed
      with its description (exercises the clone+parse path; catches the silent
      frontmatter gotcha). **`--list` is necessary but NOT sufficient** — it only
      parses frontmatter, never the file-copy path, so it passes even when the
      install drops `scripts/` (BRO-1561). The runnable install below is the real gate.
    - `npx skills add broomva/skills --skill <name> -g -a claude-code -y` → confirm
      the bundled files land at `~/.claude/skills/<name>/scripts/…` (not just SKILL.md),
      then run the skill's own test. A clean install that yields a *runnable* skill is
      "published"; a skill that merely `--list`s is not.
    - **Installable layout (step 1b — advisory WARN, not a hard fail):** a top-level
      `SKILL.md` is **standard-valid** (the agentskills.io spec + the skills.sh README
      both list the repo *root* as a discovery location). BUT a *remote* `npx skills add
      <owner>/<repo>` of a repo-root skill with bundled dirs (`scripts/`, …) **drops
      them** — an open upstream bug ([vercel-labs/skills#1523](https://github.com/vercel-labs/skills/issues/1523),
      unfixed). So the gate **WARNs** (the skill is correctly authored; the install path
      is buggy) and recommends vendoring into a `skills/<name>/` subdir — canonically the
      **`broomva/skills` monorepo**, where the subdir is non-redundant. See
      `research/entities/tool/skills-sh.md`.
    - The skill appears in the agent's available-skills list next session.
11. **Gate** — `python3 scripts/skillify_check.py <skill_dir> --roles-dir roles
    --registry roles/_index.md --entities-dir research/entities --skills-sh broomva/skills`.
    Exit 0 (step 9 now runs the real `npx skills add … --list`) or it's not a skill yet.

## The gate (deterministic)

```
python3 scripts/skillify_check.py <skill_dir> \
    [--roles-dir roles] [--registry roles/_index.md] [--entities-dir research/entities] \
    [--strict] [--run-tests] [--skills-sh broomva/skills]
```

Two layers of skills.sh-readiness: **step 1** always rejects skills.sh-breaking
frontmatter (the multi-quoted-string-list gotcha) **deterministically, with no
network** — so a skill that would silently fail to install fails the gate offline.
**`--skills-sh <repo>`** is the opt-in *networked* check: it makes step 9 a real
install-verify (`npx skills add <repo> --list`, asserts the skill is listed).

**Step 1c — reference integrity (required).** A skill must not *advertise files it
doesn't ship*. The gate scans `SKILL.md` (prose + inline-code, fenced example blocks
excluded), `skill.json` (entrypoint + script-valued fields), and `templates/*.yaml`
for references to the skill's own `scripts/`/`references/`/`assets/`/`templates/`,
and FAILs if any points at a file that doesn't exist and isn't marked Planned/
not-shipped/roadmap/TODO. A path the skill *scaffolds into a target repo* (shipped under
`assets/templates/…`) counts as satisfied. This is the #1 real defect — a skill that
*installs* fine but whose SKILL.md tells an agent to run a `scripts/<name>.py` that was
never written. Fix = ship the file, or mark the reference Planned.

*Scope (deliberately conservative to stay false-positive-free):* 1c only checks
prefixed paths (`scripts/…`, `references/…`, `assets/…`, `templates/…`) in SKILL.md
prose, `skill.json`, and `templates/*.yaml`. It does **not** flag bare filenames,
references inside ` ``` ` fenced blocks, or links in `references/*.md` — those trade
recall for zero false positives.

**Step 2 dispatches on tier.** It is required for every skill, but what satisfies it
depends on what the skill is:

| `tier` | Step 2 passes when | Also required |
|---|---|---|
| `D` | `scripts/` present and syntax-valid | step 3 (real unit tests) |
| `J` | `evals/admission.md` + a rubric + held-out cases + a judge config naming a model distinct from the model under eval + `judge.agreement_floor` **with** `judge.agreement_measured` | — (all of it is step 2) |
| `L` | a routing eval asserting **both** polarities | step 7 (resolver eval), when `--roles-dir` is supplied |

Tier J's eval artifacts are gated **in step 2, not step 5**. Step 5 grades the
*trigger* surface; re-requiring it for J would be a second gate over the same
evidence and a weaker one, since step 2 is what verifies the judge is cross-model
and the floor is measured. Step 3 is required whenever a skill ships code **in
`scripts/` or at the skill root**, whatever its tier — that is where the old
`latent_only` amnesty is closed. Code under `src/`, `lib/` or `bin/` is *not* yet
discovered (BRO-2192); the claim is stated at the scope the code actually enforces
rather than at the scope one would want.

The script **syntax** check runs for every tier, not just D. It sits outside the tier
branches deliberately: an earlier draft ran it only in the D arm, so declaring
`tier: L` bought a skill out of a check the previous gate applied unconditionally.
Declaring a tier must never reduce coverage.

Absent `tier:`, the gate **infers D from shipped code** and WARNs, so the roster does
not break on the day this ships. It infers nothing else: **J and L must be declared.**
The tempting second rule — *no code but has a trigger eval → L* — is wrong, and the
backfill proved it, labelling `autonomous`, `handoff` and `checkit` as lenses when all
three run pipelines. A routing eval is tier L's **core**, not its **signature**; every
tier can carry one. A confidently wrong tier is worse than an absent one.

An inferred tier is held to exactly the same gate as a declared one — inference decides
*which* gate, never *whether* one applies. A skill the gate cannot classify still FAILs,
now saying so accurately instead of the old and wrong `no scripts/ code`.

`--survey <root>` runs the whole checklist over every `SKILL.md` under `<root>` and
prints the tier distribution plus the pass/fail tally. It is the same gate over a
population, not a second gate — every count about the roster in this document is
regenerated by it.

Reports PASS / WARN / SKIP / FAIL for each step. **Required** steps (1 SKILL.md,
1c reference integrity, 2 the tier's core, 3 unit tests whenever code ships, 7
resolver eval for tier L when `--roles-dir` is given) gate the exit code. `--strict` promotes the recommended steps to required. Step 3
recognizes Python (AST), JS/TS, **and bash** test suites (`*.test.sh` with
`ok()`/`fail()` helpers or `PASS`/`FAIL` accounting), so a real shell test battery
isn't read as "no tests".

## Composition map

| Step | Composes |
|---|---|
| Extract the procedure | **look-back** lens (`roles/look-back.md`) |
| Scaffold the contract | **CreateSkill** |
| Deterministic core | latent-vs-deterministic discipline (`research/entities/concept/skillify.md`) |
| Resolver + eval | **P17 role-x** + `role-x.py eval` (BRO-1411 slice 1) |
| Script-test gate | **`bstack skills audit --require-tests`** (BRO-1411 slice 2) |
| Cross-review | **P20** `broomva/cross-review` |
| File the knowledge | **P6** `bookkeeping` |
| Final gate | `scripts/skillify_check.py` (this repo) |

## Anti-rationalization

| Excuse | Reality |
|---|---|
| "It worked, it's done." | It worked *today*. Without tests + a resolver-eval it silently rots. Skillify = permanent, not screenshot. |
| "It's a small skill, skip the tests." | The gate is binary (`skillify_check.py`). Small skills with scripts still need step 3. |
| "I'll register it later." | Step 6/7 unregistered = a dark skill nobody can reach. Do it now or it's invisible. |
| "Should I file a KG entry?" | Never ask (P6). File proactively, report after. |
| "Just write the SKILL.md, skip the script." | If the work is deterministic, latent space doing it is the bug. Move precision into `scripts/`. |
| "It's a judgment skill, so it can't be tested." | Tier J exists precisely to refuse this. Untestable and unspecified are different claims; the admission test tells them apart. If two agents contradict with no tiebreak, the problem is not that judgment is hard — it is that the question is not yet a question. |
| "Tier J is expensive, I'll call it L and ship a trigger eval." | L gates *routing*, J gates *output*. A skill whose value is the quality of what it produces, gated only on whether it fired, is ungated on the thing it is for. The tier whose gate is hardest is the one that applies. |
| "I'll declare an agreement floor of 0.7, that's standard." | 0.7 from where? A floor with no `judge.agreement_measured` is a FAIL, not a warning — an unmeasured number that moves under argument was authored, not measured. |

## Scope

- **In scope**: distilling a session / ad-hoc workflow / chat history into a
  tested, registered skill; auditing an existing skill against the 10-step bar.
- **Out of scope**: ingesting an external artifact (`/checkit`); retrospective
  discovery alone (`look-back`); promoting a bstack *primitive* (that's the
  bstack-engine rule-of-three, user-initiated).

## Validation (skill self-test)

Two levels, both real (the doctor *executes*, not just detects — scripts are
syntax-checked, test files must contain a real test construct, `latent_only` is
rejected when code is present):

- **Repo-local** — `skillify_check.py <skill_dir>` exits 0: SKILL.md contract +
  syntax-valid deterministic core (or genuine `latent_only`) + real unit tests.
  This is what the skill repo's CI dogfoods (`skillify_check.py . --run-tests`).
- **Workspace** — `skillify_check.py <skill_dir> --strict --registry roles/_index.md
  --roles-dir roles --entities-dir research/entities` exits 0: additionally the
  resolver trigger (lens in `roles/_index.md`), the resolver eval
  (`roles/<name>.eval.yaml`), and KG provenance.

skillify passes both (dogfood): repo-local in CI, and the workspace gate with
`roles/skillify.md` + `roles/skillify.eval.yaml` + the `concept/skillify` entity.

## References

- `research/entities/concept/skillify.md` — the concept (latent-vs-deterministic,
  the 10-step discipline, the bstack-gap analysis this operationalizes).
- `research/entities/pattern/bstack-engine.md` — Skill-QA discipline ledger.
- `roles/look-back.md` — the discovery lens skillify composes for extraction.
- BRO-1411 (slices 1+2: resolver-eval + script-test gate) · BRO-1416 (this skill).
