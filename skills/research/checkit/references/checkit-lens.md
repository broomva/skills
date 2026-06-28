# checkit — the portable contract

This is the self-contained behavior reference for the `checkit` skill. In a
**bstack workspace** the in-workspace version is the `roles/checkit.md`
role/x lens; this file is the portable copy bundled with the skill so the full
contract travels to any agent environment installed from skills.sh.

## The no-ask-back contract (the defining invariant)

> An under-specified artifact-pointer **never returns a clarifying question for
> read/research steps**. It returns an inferred-intent statement + a
> contextualized research & knowledge integration + ranked next steps. Costly or
> irreversible steps are bounded by the carve-out below — they are *surfaced as
> next steps*, not executed on a guess.

### How intent is inferred *instead of* asked

1. **Who** is asking — load whatever persona/identity context exists. For a
   focused builder/researcher, the default reading of "check this out" is
   *"does this change how WE build, and should we adopt / reject / file it?"* —
   not a neutral book report.
2. **What** is active — current branch, open PRs, recent work, the last few
   conversation arcs. The artifact is almost always relevant to something in
   flight; find the link.
3. **What's already known** — search existing notes / knowledge first. The
   artifact usually confirms, contradicts, or extends something you already have.
4. **What kind** of artifact — drives the dominant intent (taxonomy below).

### Carve-outs (the only escapes from "just proceed")

- **Costly / irreversible** — proceeding-without-asking covers only *reversible,
  low-cost* steps. Before an expensive multi-agent deep-research fan-out, a
  mutation to an existing note on an inferred contradiction, or filing a ticket:
  do the cheap reversible version first; surface the expensive/destructive option
  as a ranked next step. You still never *ask* — you *defer to a next step*.
- **Irreducible fork** — two readings, materially different deliverables, neither
  favoured by the frame: state both in one line, pick the higher-probability one,
  proceed. Never block.

## Artifact-gate (classify before running the pipeline)

1. **Artifact present** (URL / repo / paper / file / @-mention / image / pasted
   doc) → run the full ingest pipeline using the taxonomy below.
2. **No artifact, but a research-topic** ("research about X", "best practices for
   Y") → run the same pipeline with the topic as the subject.
3. **Neither** (a stray pointer phrase with no artifact and no topic, or an
   off-topic match) → this is not checkit; answer normally. This is the guard
   against spurious activation.

## Intent-inference taxonomy (artifact type → default intent)

| Artifact | Default inferred intent (state it, then do it) |
|---|---|
| **GitHub repo** | Evaluate-against-our-stack: extract mechanism → map to what we build → **build-vs-reuse** decision → file the comparison. |
| **arXiv / research paper** | Extract the load-bearing mechanism + result → map to our design → does it change a decision? → file with HIGH/MED/LOW-tagged claims. |
| **Competitor / product / startup** | Competitive + differentiation analysis: what they do, what we'd adopt, where our edge is → file with a "bearing on our work" note. |
| **Blog post / article / thread** | Extract the insight → is it actionable for us → connect to existing knowledge → a synthesis note if it combines with ≥2 prior notes. |
| **Image / screenshot / diagram** | Identify what it is → relevance → if it encodes a decision/architecture, transcribe into text (don't leave knowledge trapped in a PNG). |
| **File in our repo / @-mention** | Review current state → trace dependencies → what's the next step → tie to a task. |
| **Bare topic string** | Prospective scoped research: triangulate ≥2 sources → landscape / best-practices map → file + suggest the decision it informs. |

When the artifact doesn't fit a row, default to the **GitHub-repo shape**
(evaluate-against-our-stack) — the highest-probability intent for a builder.

## Procedure

1. **Classify** (artifact-gate) then **infer + declare intent** in one line:
   *"Reading this as: <inferred ask> (artifact type: X; relevant to: <active
   work>)."* Proceed — no question.
2. **Contextualize** — snapshot active work; search existing notes/knowledge for
   the topic. Name what's already known.
3. **Deep research** — right engine per artifact type; **verify every URL**;
   scale depth to stakes (deep only per the costly-step carve-out).
4. **Analyze** — mechanism / claim / result; novel? load-bearing? confirms or
   contradicts existing knowledge? tag HIGH / MED / LOW.
5. **Connect** — ≥1 explicit link to existing knowledge; mutation gated by the
   carve-out.
6. **Document proactively** — file the note / entity / summary; report, don't
   ask. Provenance traces to the artifact.
7. **Next steps** — ranked, tied to active work.
8. **Format** — markdown for knowledge substrate; a richer brief only for a
   human-read decision artifact.

## Common anti-patterns this skill prevents

1. **Bounce-back question** — "what do you want me to do with this?" The single
   worst failure; the whole skill exists to prevent it.
2. **Shallow glance** — a summary with no research, connection, or filing.
3. **Research without integration** — deep research reported but never filed; the
   knowledge stays cold and next session re-solves it.
4. **Re-research of solved problems** — skipping the knowledge-first step.
5. **Hallucinated citations** — citing an unverified URL.
6. **Neutral book report** — ignoring who's asking ("does this change how WE
   build?").
7. **Permission-to-document** — "want me to file this?" Forbidden; file first.
8. **Barreling into a costly/irreversible action on a guess** — running a deep
   fan-out or mutating a note on an inference instead of surfacing it as a next
   step (the carve-out violation).

## Self-test

A checkit response is well-formed iff:

- [ ] An inferred-intent line appears BEFORE any research, and **no clarifying
      question was asked** for read/research steps (irreducible forks: both
      readings in one line, proceed on the higher-probability one).
- [ ] Any costly/irreversible step was *surfaced as a ranked next step*, not run
      on a guess.
- [ ] Existing knowledge was searched first (what's already known is named).
- [ ] Deep research ran and every external URL was verified.
- [ ] ≥1 link to existing knowledge was made.
- [ ] ≥1 finding was filed proactively — reported, not asked.
- [ ] A ranked next-steps list ties the finding to active work.
