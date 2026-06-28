# Contributing to phronesis

> **Status:** This document will be expanded in M8 (final docs milestone).
> The information below is the minimum viable contributor guidance during M0-M7.

## Development setup

```bash
git clone <repo-url>
cd phronesis
uv sync
make smoke
```

Required: Python 3.12+, [uv](https://docs.astral.sh/uv/) 0.4+.

## Making changes

1. Branch from `main` (use a descriptive branch name, e.g. `feat/m1-frameworks-rice`).
2. Write the failing test first (TDD discipline).
3. Make the smallest change that passes the test.
4. Run `make smoke` and ensure green.
5. Commit with conventional-commits style (`feat:`, `fix:`, `docs:`, `chore:`, `test:`).
6. Open a PR; ensure all CI checks pass.

## What CANNOT be committed

* Tenant data — anything under `engagements/<not-template>/`. Pre-commit hook blocks this. P6.
* Secrets — patterns matching `aws_access_key_id="..."`, `api_key="..."`, etc. Pre-commit hook blocks assignment-shaped strings.
* Frameworks that don't satisfy `frameworks/_schema.yaml` — `make framework-lint` blocks this.

## Adding a new framework

*(Detailed recipe lands in M8 at `references/how-to-add-framework.md`.)*

For now: copy an existing framework YAML in `frameworks/<category>/`, edit the fields, run `make framework-lint`. The schema is `frameworks/_schema.yaml`.

## Style

* Code: ruff (config in `pyproject.toml`).
* Type hints: required on all public APIs.
* Docstrings: required on all public types and functions.

## Testing discipline

* Unit tests for typed primitives, linter rules, renderer correctness.
* Integration tests for stage-to-stage flow.
* Property tests for invariants (every framework YAML schema-valid; replay idempotence).
* Fixture-based E2E (`acme-bank`, `nova-construction`) for end-to-end validation.
* Canary anonymization test and Bision-failure-prevention test are release gates.
