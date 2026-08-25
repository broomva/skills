# The closed vocabulary

Generated from `scripts/extract.py` — do not edit by hand. `vocabulary_doc()`
builds the extractor's brief from the same tables, so a predicate added to the
code cannot be missing from the prompt that claims to be the complete list.

## Entity kinds

| Kind | Identity | Notes |
|---|---|---|
| `org` | normalised name | `ACME S.A.S.` and `acme s.a.s.` merge |
| `person` | normalised name | |
| `profile` | **exact URL** | in `EXACT_KINDS`; two URLs one character apart are two pages |
| `location` | normalised name | projects to a `concept` page |
| `product` | normalised name | not projected; carried as an attribute |

The kind set is closed because the identity rule — *same kind + same key means
same entity* — has no fixed domain otherwise, and two crawls can then disagree
about whether a thing is one entity or two.

## Predicates

| Predicate | Domain → Range | |
|---|---|---|
| `subsidiary_of` | org → org | inverse of `parent_of` |
| `parent_of` | org → org | inverse of `subsidiary_of` |
| `acquired` | org → org | |
| `invested_in` | org → org | |
| `partner_of` | org → org | symmetric |
| `supplies` | org → org | |
| `competitor_of` | org → org | symmetric |
| `employs` | org → person | |
| `leads` | person → org | **not** the inverse of `employs` |
| `founded` | person → org | |
| `board_member_of` | person → org | |
| `advises` | person → org | |
| `has_profile` | person → profile | **expansion predicate** |
| `org_profile` | org → profile | **expansion predicate** |
| `located_in` | org → location | |
| `offers` | org → product | |
| `possibly_same_as` | X → X, same kind | symmetric; always `simulated` |

### Why `leads` has no inverse

A CEO is both employed by a company and leads it. Declaring `leads` the inverse
of `employs` would make a correct graph look self-contradictory, so `INVERSES`
is deliberately partial — it holds only the pairs that genuinely say the same
thing backwards.

### The two expansion predicates

`has_profile` and `org_profile` are the only predicates whose range is
`profile`, and a verified `profile` node's name is a URL. That is the **only**
route by which a crawl moves from one entity to the next: a link the bytes
literally contained, at offsets the extractor committed to before any check ran.

`EXPANSION_PREDICATES` is the control point rather than an accident of typing.
The next predicate given a `profile` range must not silently become a way to
move.

## Edge attributes

`title` · `since` · `until` · `note` — strings, ≤200 characters.

These ride on the **edge's** evidence span, so the entailment verifier judges
them together with the relation. An unevidenced attribute is a claim wearing a
data hat.

Two reserved attributes are written by `admit`, never by an extractor:
`_subject_span` and `_object_span`, carrying the endpoint offsets as
`start:end` into the edge's own page. They exist so `triple-entailed` can
re-check containment from stored data instead of asking the producer whether it
validated its own output.

## Bounds

| Bound | Value | What it refuses |
|---|---|---|
| `MAX_RELATION_SPAN` | 600 bytes | co-mention across a page |
| `MIN_NAME_CHARS` | 2 | a one-character "entity" |
| `MAX_NAME_CHARS` | 120 | a paragraph quoted as a name |
| `MAX_ATTR_CHARS` | 200 | an essay in an attribute |

The relation bound is the arithmetic half of `triple-entailed`. It rules out
co-mention that is *far apart* — a company in the header and a person in the
footer. It cannot rule out co-mention that is close together, because two names
within 600 bytes is an ordinary team page; that is what the blinded verifier is
for, and `triple-entailed` fails an edge nobody judged.
