# Changelog

All notable changes to `first-principles-sim` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-11-13

First release (BRO-3709), distilled from the cloud-chamber build (BRO-3705).

- `scripts/sim_audit.py`: audits a simulation package against its claim ledger
  (`sim-claims.yaml`). Checks that every test asserts, that reference tables carry a source and
  a date and are read by a test, that quoted numbers appear in the docs and in the report
  output, and that each listed mutation turns its test command red in a copy of the package.
- `assets/templates/sim-claims.yaml`: a ledger to copy.
- `references/method.md`: the eleven steps, each with its reason and the cloud-chamber example.
- `references/domains.md`: the stage chain, anchors and controls for other fields.
