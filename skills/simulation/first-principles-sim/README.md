# first-principles-sim

Build a simulation where the picture or the sound is a consequence of the model, and prove each
number it states.

- [SKILL.md](SKILL.md): the arc and the claim kinds.
- [references/method.md](references/method.md): each step, with its reason and an example.
- [references/domains.md](references/domains.md): how the method applies to other fields.
- [scripts/sim_audit.py](scripts/sim_audit.py): the audit.

## Install

```bash
npx skills add broomva/skills --skill first-principles-sim
```

## Audit a package

```bash
cp assets/example/falling-body/sim-claims.yaml <package>/sim-claims.yaml   # then replace every entry
python3 scripts/sim_audit.py <package> --run-report --run-mutations
```

`assets/example/falling-body` is a complete package that passes with `--strict`.

A YAML ledger needs PyYAML. A `sim-claims.json` ledger needs only the standard library. CI runs
Python 3.11 and 3.12. The package's tests must run from a copy of the package directory.

## Test

```bash
pip install -r tests/requirements-dev.txt
python3 -m pytest tests/ -q
python3 tests/run_mutants.py   # changes the audit one behaviour at a time; the tests must fail
```
