# The probe library exactly as the corpus run minted it

These 30 files are the **unmodified** output of the 15-repository corpus run of
2026-07-25 — the artifacts that produced the crystallization curve. They exist
so the evidence behind that curve is reviewable rather than resident on one
laptop, which is where it lived until it was committed.

**None of them ship.** The skill's `probes/` directory contains one probe,
`example-llm-review-gate.v1.ts`, which is a contract reference and is not drawn
from this set. So the crystallization curve was produced by a library that a
fresh install does not get: a new user starts from an effectively empty cache
and pays a model call for every node until they mint their own. That gap is
real, it is the main thing standing between this record and a shipped library,
and the report should not be read as though the curve describes a first run.

## What would have to be true before any of these ship

1. **Types.** Minted probes are untyped because they are written to
   `~/.config/keel/probes/`, outside any package, where a relative import to the
   `Probe` contract would not resolve. Inside the skill it does resolve, so
   shipping one means the compiler holds the contract — including that `assess`
   may never return `unknown`.

2. **The whole-body guard**, needed on 17 of the 18 `not_a_check` probes. Their
   abstention was a denylist of runner names, which cannot enumerate the world;
   six were measured filing a step `not_a_check` whose body also ran
   `./scripts/verify-contract.sh --strict`. Since `not_a_check` leaves the
   denominator, that drift *raises* the ratio — the one direction this project
   must never move silently. A probe that can inflate a score by abstaining
   badly is worse than no probe.

3. **Version hygiene.** `frozen-dependency-install.v1` is superseded by `v2`,
   which withdrew the `npm ci` token (a substring of `pnpm ci:<task>`). Both are
   kept here because the record is of what the run minted, not of what survived
   review.

Until those hold, promoting any of these would ship a library whose failure mode
is a quietly higher grounding ratio — the exact defect Keel is built to detect.

## Reading these files

The header comments reference paths from the repository layout at the time they
were minted (`skills/keel/schemas/keel.ts`). They are left as written: the value
of this directory is that it is byte-for-byte what the run produced, and
retouching the paths would trade that away for tidiness. Resolve them against
`schemas/keel.ts` and `probes/` in the current layout.

Nothing here is loaded at runtime. This directory is a record, not a library.
