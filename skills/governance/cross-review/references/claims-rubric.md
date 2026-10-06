# Claims Rubric — bstack P20, knowledge tier

`cross-review pre-push` hands this rubric to the one stratum that reviews a **knowledge-tier** diff: one
whose every changed path is under `research/` or is `docs/knowledge-index.md` (see `rubric.md` §Stakes
tiers). Such a diff adds or edits knowledge — entity pages, notes, their evidence folders. Its failure
mode is a false or unsourced claim, so this rubric asks about claims and nothing else. Scripts inside an
evidence folder are judged only on whether they reproduce what the page cites, never as software.

The ledger is unchanged: five dimensions, 0-2 each, `AXES: a,b,c,d,e`, pass at >=7 with no dimension at 0.
The severity rules are the code rubric's (`rubric.md` §The adversarial brief): a dimension scores 0 only
for a BLOCKER or a MAJOR the reviewer reproduced; a MINOR never lowers a score.

## The five dimensions

| Dimension | Points | Pass condition |
|---|---|---|
| **Claims trace to sources** | 2 | Every factual statement on the page restates a file the change carries, or a cited source, at the place it cites |
| **No quote cut or placed against its sense** | 2 | No quote is trimmed, joined or set beside another so that it implies what its source does not say |
| **Numbers recompute** | 2 | Every figure the page states matches its source, or the script that derives it, when recomputed |
| **Gaps disclosed** | 2 | What was not read, not measured or not established is said, not left for the reader to assume |
| **Evidence reproduces** | 2 | The captured files are the ones cited, and any script that claims to rebuild them does |

A finding reproduces when the reviewer quotes the page's sentence beside the source line it misstates, or
gives the command and the output that shows a number or a file is wrong.

## The brief (what to give the evaluator)

> You are reviewing a knowledge page and its evidence, not code. Read the diff. For each claim the page
> makes, open the source it cites and check it says that. Grade every finding by severity:
>
> - **BLOCKER** — the page states something false about its subject.
> - **MAJOR** — a claim is unsourced, a quote is cut or placed so it misleads, a number is wrong, or a gap a
>   reader would rely on is hidden. Quote the page and the source.
> - **MINOR** — wording, ordering, formatting, or a hardening idea for the evidence scripts.
>
> Score each dimension from its worst finding: 0 for a BLOCKER or a MAJOR you reproduced (quote both
> sides, or the command and output), 1 for a MAJOR you did not reproduce, 2 otherwise. List MINORs; they
> never lower a score. Report `AXES: a,b,c,d,e` in table order, `SCORE: N/10`, and `VERDICT: APPROVE` (>=7,
> no 0) or `VERDICT: REVISE`. An empty finding list is a valid result for a sound page.

## Strata-A specific: Codex cross-vendor brief

When invoking Strata A via `codex exec`, prepend this preamble to the rubric:

> You are an OpenAI model checking a knowledge page written by Claude. Your job is to open each cited
> source and test the page's sentences against it. You are not reviewing code style, and the evidence
> scripts matter only if they fail to reproduce what the page cites.

## Rounds

The knowledge tier expects one round. A second round is for verifying the fix of a dimension that scored
0. The ledger does not enforce this, since it still allows three free rounds; the orchestrator states in
the PR why a further round was run.
