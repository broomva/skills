# first-principles-sim

Build a simulation where the picture or the sound is a consequence of the model, and prove each
number it states.

- [SKILL.md](SKILL.md): the arc and the claim kinds.
- [references/method.md](references/method.md): each step, with its reason and an example.
- [references/domains.md](references/domains.md): how the method applies to other fields.
- [references/representation.md](references/representation.md): how to hold and show the state,
  and when WebGL2 fits.
- [scripts/sim_audit.py](scripts/sim_audit.py): the audit.

## Install

```bash
npx skills add broomva/skills --skill first-principles-sim -g -a claude-code
```

With `-g -a claude-code` the skill lands in `~/.claude/skills/first-principles-sim`. Without
`-g` it is installed into the current project instead, at
`.claude/skills/first-principles-sim`; use that path in the commands below.

## Audit a package

Run these from this skill's directory (after the global install above,
`~/.claude/skills/first-principles-sim`), with `<package>` as the path to your simulation
package:

```bash
cp assets/example/falling-body/sim-claims.yaml <package>/sim-claims.yaml   # then replace every entry
python3 scripts/sim_audit.py <package> --run-report --run-mutations --run-gates
```

From anywhere else, give the script's full path, for example
`python3 ~/.claude/skills/first-principles-sim/scripts/sim_audit.py <package> ...` for a global
install.

`assets/example/falling-body` is a complete package that passes with `--strict`.

A YAML ledger needs PyYAML. A `sim-claims.json` ledger needs only the standard library. CI runs
Python 3.11 and 3.12. The package's tests must run from a copy of the package directory.

## Test

```bash
pip install -r tests/requirements-dev.txt
python3 -m pytest tests/ -q
python3 tests/run_mutants.py   # generates changes to the audit; the tests must fail for each
```
