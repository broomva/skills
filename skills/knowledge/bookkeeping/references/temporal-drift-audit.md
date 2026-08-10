# Temporal Drift Audit

`bookkeeping lint --temporal` is an opt-in, warning-only maintenance signal for
filesystem knowledge graphs. It detects temporal bookkeeping defects that can
be established from local syntax without asking a regex to decide what is true.

## Contract

The audit emits two fields:

- `temporal_updated`: frontmatter `updated` is older than the newest valid ISO
  date found in `sources` or the body.
- `temporal_as_of`: mutable state is asserted in a catalog-visible
  `core_claim`, a state-labelled heading, or an explicit state-label line
  without an inline ISO as-of date.

Every finding has `warning` severity. Existing `lint` behavior is unchanged
unless `--temporal` is passed.

## Precision boundary

The detector includes only surfaces that agents commonly consume detached from
their surrounding history:

- high-precision claim forms such as `is now`, `currently`, `is deprecated`,
  or `is no longer`;
- headings beginning with state labels such as `Status`, `Roadmap`,
  `Open decision`, or `Open follow-ups`;
- explicit label lines such as `**Current state**:` or `Status:`.

It deliberately excludes arbitrary present-tense prose, generic `Open
Questions` sections, the word `shipped` used adjectivally, and prose that merely
discusses superseded records. A future ISO date does not satisfy an as-of marker
and does not make `updated` stale; invalid calendar dates are ignored.

## Calibration receipt — 2026-08-09

Calibration ran against a clean detached worktree of `broomva/workspace`
`f4e04b45`, using the candidate Bookkeeping implementation with
`KG_ROOT=<clean-worktree>` and `KG_NO_POLICY=1`.

The machine-readable receipt, including the full source commit, command
contract, control cases, and ordinary-lint baseline, is
`temporal-drift-calibration-2026-08-09.json`.

| Measure | Result |
|---|---:|
| Entity pages audited | 928 |
| Total findings | 96 |
| `temporal_updated` | 67 |
| `temporal_as_of` | 29 |
| Distinct affected entities | 91 |
| Non-warning findings | 0 |

Known controls behaved as intended:

- `chronos-temporal-primitive` still warns on the undated `Open follow-ups`
  heading after its stale M1/M2 contents were reconciled.
- `lago-event-journal` is clean after its `updated` metadata and resolved
  BRO-1238 decision were corrected.
- Default lint on Chronos emits no temporal finding; adding `--temporal` emits
  one warning and exits successfully.

## What this does not prove

The audit does not determine which claim is current, whether one claim
contradicts another, whether a newer source is authoritative, or whether a
revision should supersede an older record. Requiring `valid_from`,
`recorded_at`, `supersedes`, or `revision_link` before typed producers emit
those fields would create compliance theater and false confidence.

Semantic reconciliation therefore remains a Dream (P13) review step. A future
hard gate requires typed write-side producers, a non-blocking supersession
validator, and calibration showing that the warning has useful precision and
recall on independently judged cases.
