# Typed Temporal Revision Envelope

The write-side contract for four typed frontmatter fields. It exists because
the temporal-drift audit (`references/temporal-drift-audit.md`) is a
**detector**: it can surface that a page asserts mutable state without an as-of
date, but it cannot establish which belief is current or which record
supersedes another. That question is only decidable if the write path emits the
answer.

Producers therefore come first, and semantic validation is layered on top of
what they actually write. A schema that claims guarantees no writing path
supplies is compliance theater.

## The four fields

| Field | Meaning | Who may write it |
|---|---|---|
| `recorded_at` | System time — when the graph recorded this state | The pipeline, mechanically |
| `valid_from` | Claim-effective time — when the claim became true | A source or an explicit revision, only if it supplies one |
| `supersedes` | Records this page replaces, as `[[wikilink]]`s | An explicit correction workflow only |
| `revision_link` | The record(s) that authorized the supersession — a **list** | An explicit correction workflow only |

`recorded_at` and `valid_from` are deliberately different clocks. Collapsing
them — treating "when we wrote it down" as "when it became true" — is the
temporal flattening that motivated this work.

## Provenance rules

**`recorded_at` is mechanical.** It is stamped on creation and re-stamped on a
substantive update, always from system time. It is quoted (`recorded_at:
"2026-08-10"`) so it does not re-serialize into a full timestamp on the next
edit, and it is listed in `_VOLATILE_FRONTMATTER_FIELDS` so it is excluded from
the content-identity comparison. That exclusion is load-bearing: without it
every page would differ from its own update candidate on every run, resurrecting
the date-bump churn the guard was built to kill and degrading `recorded_at` into
a "last run" stamp.

**Legacy pages are not backfilled by the update path.** A page predating the
envelope has no knowable system time, and the update path must not invent one.
Backfilling there would not churn the graph (the volatility exclusion prevents
that) — it would do something quieter and worse: stamp today onto the arbitrary
subset of legacy pages that happen to acquire an unrelated delta. Legacy pages
acquire the field through an explicit revision or a dedicated migration.

**`valid_from` is never guessed.** It is read from exactly one key,
`metadata.valid_from` on the raw item, and only when that value parses as an
ISO date. It is never derived from:

- prose in the body (`"effective 2025-01-01"` is a sentence, not a field);
- any ISO date found elsewhere in the page;
- `item.timestamp`, which is when the claim was ingested, not when it became
  true.

An absent `valid_from` is a truthful "not stated". A defaulted one asserts that
every promoted claim became true on its promotion date.

**`supersedes` and `revision_link` are never inferred.** Promotion never emits
them, no matter how emphatically the content says "this replaces X". They come
from exactly two explicit workflows, both routed through
`_apply_revision_envelope`:

- `bookkeeping revise` — an operator or agent naming the revising entity, the
  superseded slugs, and the authorizing record;
- `bookkeeping merge` — already an explicit correction, which now records the
  canonical as superseding the dup with the tombstone as its authorizing record.

`revision_link` is required alongside `supersedes` because a supersession with
no authorizing record is untraceable — it asserts that something was replaced
without saying who decided that or on what basis. It is a **list**: a page can
be corrected more than once, and a scalar that each revision overwrote would
leave the latest ticket claiming authorship of every earlier supersession.

## Refuse, never repair

Both correction workflows read the existing envelope before rewriting it, so a
value they cannot read exactly is a value they would destroy. They refuse
instead, with the repair left to a human:

- a `supersedes` entry that is not canonical `[[slug]]` form, or is not a
  string, or is not in a list;
- a `revision_link` entry that is not a string;
- an envelope key declared **twice** in the same frontmatter — PyYAML resolves
  duplicates to the last, so a read-then-write silently discards the earlier
  one;
- a page with no YAML frontmatter, where every setter would no-op while the
  command reported success.

`merge` aborts on all of these rather than tombstoning the dup and skipping the
supersession: a merged record whose provenance says nothing is a worse outcome
than a merge the operator has to re-run.

## Known limitations

These are stated rather than designed around, because the phase's own doctrine
is that a schema must not claim guarantees its writers do not supply.

- **Entry-to-link binding is not represented.** `supersedes` and
  `revision_link` are parallel sets, not pairs. The envelope says "these
  records were replaced, on the authority of these decisions" and no more.
  Per-entry binding is a larger schema change and is better designed against
  real revisions than in advance.
- **Writes are not atomic or locked.** `revise` and `merge` do a
  read-modify-write, so two concurrent runs can lose one another's additions.
  This is true of every write path in the engine (`promote`, `merge`,
  `lint --fix`); locking one command would buy a false sense of safety.
- **Non-UTF-8 bytes do not survive a rewrite.** Pages are read with
  `errors="replace"`, the codebase-wide idiom. A page containing invalid UTF-8
  will have those bytes replaced if it is revised.

## Commands

```bash
# Record an explicit correction.
python3 scripts/bookkeeping.py revise \
  --entity new-belief \
  --supersedes old-belief-a old-belief-b \
  --revision-link "https://linear.app/broomva/issue/BRO-1234" \
  [--valid-from 2026-04-15] [--dry-run]

# A merge records the supersession on the canonical automatically.
python3 scripts/bookkeeping.py merge dupe canonical [--revision-link REF]
```

`revise` refuses rather than warns when the revising entity is missing, a
superseded slug has no file, an entity supersedes itself, or `--valid-from` is
not an ISO date. Writing an unresolvable `supersedes` would manufacture the
exact dangling-provenance state the audit then has to report.

Re-applying the same revision is byte-identical: `supersedes` is unioned with
what is already present (a page can be corrected more than once, and a later
revision must not silently drop what an earlier one recorded), rendered
canonically, and the date stamps are idempotent within the day.

## Validation — warning-only, opt-in

These findings are emitted by `lint --temporal` only. Default `lint` output is
unchanged; a page with a wholly malformed envelope still produces no default
finding.

| Field | Condition |
|---|---|
| `temporal_recorded_at` | Unparseable, or in the future relative to the audit date (system time cannot postdate the audit) |
| `temporal_valid_from` | Unparseable. A *future* `valid_from` is allowed — a scheduled change is not a defect |
| `temporal_supersedes` | Not a list; entry not a string; entry not `[[wikilink]]` form; self-supersession; target has no entity file; target's `recorded_at` is newer than this record's (timeline inversion) |
| `temporal_revision_link` | `supersedes` set with no non-blank `revision_link`; `revision_link` set with no `supersedes`; any entry blank or not a string (one usable entry must not launder the rest — the writer refuses such a page, so the audit that precedes it must see it) |

Merge tombstones resolve deliberately: superseding a slug that was merged away
is the normal case, and reporting it as dangling would flag every merge.

## What this still does not prove

The audit checks that stamps parse, that a supersession resolves, that it
carries an authorizing record, and that its timeline runs forwards. It does not
judge whether a supersession is **correct** — whether the newer record really
does replace the older, or whether a source is authoritative. That remains
Dream (P13) review work.

Promotion of any of these checks to a hard gate requires live-graph calibration
on independently reviewed revisions showing useful precision and recall, plus an
independent cross-review. Existing warnings are not evidence of that; they are
the instrument that produces it.

## Migration: replaying merges the graph already recorded

```bash
python3 scripts/bookkeeping.py backfill-revisions            # dry run
python3 scripts/bookkeeping.py backfill-revisions --apply
```

A `status: merged` tombstone names the canonical (`merged_into`), dates the
merge (`merged_at`), and is itself the record that authorized it.
Reconstructing the envelope from those three is transcription, not inference,
so this is the sanctioned way a pre-envelope page acquires the fields.

`recorded_at` is stamped with the **historical** `merged_at`, not the migration
date — the graph did not learn a June merge in August, and saying so would
flatten the exact distinction the envelope exists to preserve. `updated` does
move to today, because the file is genuinely being edited. The migration is
idempotent, and a tombstone with no parseable date is reported rather than
given an invented one.

What it deliberately does **not** treat as a supersession: `aliases:` (88 in
the live graph, almost all `aka` search synonyms rather than merged-away
entities) and `contradicts:` edges with no recorded resolution. Deciding which
of those were renames is the prose inference this envelope refuses.

## Calibration

Two receipts, answering different questions.

`temporal-revision-calibration-2026-08-10.json` — the **producer-phase**
receipt: candidate versus merged implementation over the live graph, confirming
default lint and the temporal-audit baseline are unchanged. It proves parity,
not precision.

`supersession-calibration-2026-08-10.json` — the **audit** receipt, measured
against a corpus this migration built from the seven recorded merges:

| Measure | Result |
|---|---|
| Negative control (5 real migrated canonicals, untouched) | **0** envelope findings |
| Positive control (one injected defect per class) | **12/12** detected, each on its specific field |
| Observed false-positive rate | 0/7 — 95% upper bound ~43% at this n |

The positive controls exist because zero findings on a clean corpus is
ambiguous: a checker that never fires scores identically to a correct one.

### Why there is still no hard gate

**Eleven of the twelve checks are not the kind of thing calibration measures.**
They are decision procedures — is this string `[[slug]]`, does this file exist,
does this date parse. Precision is 1.0 by construction; a finding *is* the
defect. Demanding a statistical measurement for a decision procedure is ritual.
Their real bar is soundness, established by the positive controls plus the
mutation proof.

One of them is softer than the rest and should be named rather than hidden in
the count: *"supersedes target resolves"* is crisp to **evaluate** but admits
argument about **interpretation** — a target can be unresolvable because the
tombstone was later cleaned up, not because the provenance is broken. It is
reported as a defect because an untraceable supersession defeats the purpose of
recording one, but that is a policy choice, not a fact, and it is the check
most likely to need revisiting once the corpus is larger.

**The one genuine heuristic cannot be measured on this corpus.** Timeline
inversion reads the *superseded* record's `recorded_at`; tombstones carry none,
so the real corpus never exercises it.

And with 5 of 943 pages carrying the envelope, a gate would have almost nothing
to protect and no operational history behind it. Revisit when the fields are
widespread through ordinary `merge`/`revise` use rather than a migration, when
tombstones carry stamps, and when an independent reviewer has judged a set of
real findings.
