# Claims Rubric — bstack P20, knowledge tier

`cross-review pre-push` hands this rubric to the one stratum that reviews a **knowledge-tier** diff. That
is a diff whose every changed path is `docs/knowledge-index.md` or a declarative file under
`research/entities/`, `research/notes/` or `research/imported-documents/` (`rubric.md` §Stakes tiers
has the full predicate). Such a diff adds or edits knowledge: entity pages, notes and their captured
evidence. Its failure modes are a false or unsourced claim and a leak, and this rubric asks about those.
A knowledge-tier diff carries no scripts; one that does is the code tier and gets `rubric.md`.

The ledger is unchanged: five dimensions, 0-2 each, `AXES: a,b,c,d,e`, pass at >=7 with no dimension at 0.
The severity rules are the code rubric's (`rubric.md` §The adversarial brief): a dimension scores 0 only
for a BLOCKER or a MAJOR the reviewer reproduced; a MINOR never lowers a score.

## The five dimensions

| Dimension | Points | Pass condition |
|---|---|---|
| **Claims trace to sources** | 2 | Every factual statement on the page restates a file the change carries, or a cited source, at the place it cites |
| **No quote cut or placed against its sense** | 2 | No quote is trimmed, joined or set beside another so that it implies what its source does not say |
| **Numbers recompute** | 2 | Every figure the page states matches its source when recomputed by hand from the cited lines |
| **Gaps disclosed** | 2 | What was not read, not measured or not established is said, not left for the reader to assume |
| **Evidence is sound and leaks nothing** | 2 | The captured files are the ones cited, and no secret, credential, PII or tenant/client identifier appears in the page, its evidence or `docs/knowledge-index.md` (the workspace `REVIEW.md` security pass: workspace#580 leaked a tenant slug into the index). A leak is a BLOCKER |

A finding reproduces when the reviewer quotes the page's sentence beside the source line it misstates,
gives the arithmetic that shows a number is wrong, or names the path and line of a leak and the kind of value leaked.
**Never quote a leaked value.** The verdict is pasted into the PR, so a quoted secret is published again even after
the page is fixed: write `research/notes/x.md:12, an API key (sk-…, redacted)`, not the key.

## The brief (what to give the evaluator)

> You are reviewing a knowledge page and its evidence, not code. Read the diff. For each claim the page
> makes, open the source it cites and check it says that. Search the page, its evidence and the index for
> secrets, credentials, personal data and client or tenant names. Grade every finding by severity:
>
> - **BLOCKER** — the page states something false about its subject, or the diff leaks a secret, PII or a
>   tenant/client identifier.
> - **MAJOR** — a claim is unsourced, a quote is cut or placed so it misleads, a number is wrong, or a gap a
>   reader would rely on is hidden. Quote the page and the source.
> - **MINOR** — wording, ordering, formatting.
>
> Score each dimension from its worst finding: 0 for a BLOCKER or a MAJOR you reproduced (quote both
> sides, the arithmetic, or the path, line and kind of a leaked value, never the value itself), 1 for a BLOCKER or a MAJOR you did not
> reproduce, 2 otherwise. An unreproduced suspicion scores at most 1, never 0. List MINORs; they never
> lower a score. Report `AXES: a,b,c,d,e` in table order, `SCORE: N/10`, and `VERDICT: APPROVE` (>=7, no
> 0) or `VERDICT: REVISE`. An empty finding list is a valid result for a sound page.

## Strata-A specific: Codex cross-vendor brief

When invoking Strata A via `codex exec`, prepend this preamble to the rubric:

> You are an OpenAI model checking a knowledge page written by Claude. Your job is to open each cited
> source and test the page's sentences against it, and to check that nothing in the diff leaks a secret,
> personal data or a client or tenant name. You are not reviewing code style.

## Rounds

The knowledge tier expects one round. A second round is for verifying the fix of a dimension that scored
0. The ledger does not enforce this, since it still allows three free rounds; the orchestrator states in
the PR why a further round was run.
