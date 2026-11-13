# Changelog

All notable changes to `first-principles-sim` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-11-13

First release (BRO-3709), distilled from the cloud-chamber build (BRO-3705).

**Experimental.** Merged on the owner's decision without a passing independent review. Four
review rounds each scored it 5 out of 10 (one stratum scored 3 and 4 in rounds 1 and 3). The
open findings are on BRO-3709; the main ones:

- **False passes.** Any non-data file beside the tests that names a reference table (a
  checksum file, a `README.rst`) counts as code that reads it. A ledger listed as its own doc,
  with a report that prints it, passes the quoted check.
- **Wrong results through symlinks.** A mutation aimed at a file reached through a symlink
  inside the package changes the link's target, not the copy the tests import, and reports
  SURVIVED.
- **Crashes.** A very large `--timeout`, a deeply nested ledger and an id with a lone
  surrogate give tracebacks. Duplicate YAML keys are accepted silently. A `find` containing
  `\r\n` never matches.
- **The script's own tests.** `tests/run_mutants.py` generates several hundred changes and all are caught,
  but in every round a reviewer wrote further changes by hand and about half survived (24 of
  48 in round 4). Most are outside what the generator produces: only the first gate or support
  path being used, paths in `docs`, `gates` and `support` leaving the package, the mutation
  baseline ignoring `--timeout`.
- **Not measured since the changes:** the lens's recall on a new set of cold prompts.

- `scripts/sim_audit.py`: audits a simulation package against its claim ledger
  (`sim-claims.yaml`). Checks that the tests are green and every test file asserts, that
  reference tables carry a source and a date and are read by a test, that quoted numbers appear
  in the docs and in the report output, and that each listed mutation turns its test command
  red. Commands run in a temporary copy of the package. `--run-gates` runs checks the test
  command does not, such as a headless render.
- `assets/example/falling-body`: a complete package that passes the audit with `--strict`. Its
  ledger is the template to copy.
- `tests/run_mutants.py`: generates changes to the audit from its source, adds a hand-written
  list, and requires the test suite to fail for each one.
- `references/method.md`: the steps, each with its reason and the cloud-chamber example.
- `references/domains.md`: the stage chain, anchors and controls for other fields.
