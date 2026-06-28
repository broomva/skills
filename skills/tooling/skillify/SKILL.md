---
name: skillify
category: tooling
description: >-
  Skillify-as-a-verb — distill a working session (or a pointed-at chat history)
  into a permanent, TESTED, registered skill at the end of a workflow. The
  bstack-native composition of Garry Tan's 10-step "skillify it": look-back
  extraction → CreateSkill scaffold → latent/deterministic split → unit tests →
  resolver-eval (role-x.py eval) → script-test gate (bstack skills audit
  --require-tests) → P20 cross-review → bookkeeping file. Composes existing
  primitives; reimplements nothing. The deterministic core (scripts/skillify_check.py)
  makes "a feature that doesn't pass all ten is not a skill" machine-checkable.
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
> Every failure or hard-won ad-hoc workflow becomes a *tested* skill, so the
> bug becomes structurally unreachable and the procedure becomes permanent
> infrastructure. The latent space *builds* the deterministic tool; the
> deterministic tool then *constrains* the latent space.

## The 10 steps (bstack-native)

| # | Skillify step | bstack mechanism (composed, not reimplemented) |
|---|---|---|
| 1 | SKILL.md contract | **CreateSkill** scaffold → name + description + triggers |
| 2 | Deterministic code | latent-vs-deterministic split — move precision work into `scripts/` (`latent_only: true` exempts pure composition skills like this one) |
| 3 | Unit tests | `tests/test_*.py` (vitest/pytest) on the deterministic core |
| 4 | Integration tests | live-endpoint / real-data tests where applicable |
| 5 | LLM evals | judgment-output skills only — LLM-as-judge, compose **P20** |
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
3. **Build the deterministic core** — write `scripts/*` for the precision work.
   Pure composition skills set `latent_only: true` and skip this.
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
not-shipped/generated. A path the skill *scaffolds into a target repo* (shipped under
`assets/templates/…`) counts as satisfied. This is the #1 real defect — a skill that
*installs* fine but whose SKILL.md tells an agent to run a `scripts/<name>.py` that was
never written. Fix = ship the file, or mark the reference Planned.

Reports PASS / WARN / SKIP / FAIL for each step. **Required** steps (1 SKILL.md,
1c reference integrity, 2 code unless `latent_only`, 3 unit tests when code present)
gate the exit code. `--strict` promotes the recommended steps to required. Step 3
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
