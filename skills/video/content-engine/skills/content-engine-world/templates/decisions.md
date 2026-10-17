# {Working title}: decisions

Every round's questions, the recommendation, and the owner's answer copied **verbatim** from the
asks ledger (`{.control/asks/<arc>.yaml}`) or the session. Taste ids (`T1`, `A2`, `G3`, `X1`) cite
`owner-taste.md`.

> Rules `world_check.py` enforces: every seed and question has a verbatim answer (a blockquote or a
> quoted string) or is `pending` (W12); round 0 has 4 to 6 seeds, one of them a stretch, before any
> later round (W13); an answered round has a `### Method notes` bullet (W14). Two record forms are
> accepted: headed items with `- **Answer:**` lines, or a questions table and an answers table
> keyed by the ledger's ask id. Both are shown below.

## What is already decided (never re-asked)

- {policy}: {ledger file} `{ask id}`, answered {date}.

## What is open (proposals only, revisited in later rounds)

- {a spec's proposal, an earlier session's idea, assets on disk}. A rule found in a spec or a note is
  decided only when an answered ask backs it; until then it is listed here.

## Cost anchors

{Unit prices from the production tool, dated, and what they imply for the seeds: e.g. a hook that
needs motion transfer costs N times one that uses original motion.}

---

## Round 0: divergent world seeds (asked {date})

Four to six genuinely different worlds, plus one question about the shape of the world (one world
or many). Each seed is its own ask, answered **Build on it / Keep as an ingredient / Drop it**, so
seeds can be mixed. Nothing from earlier experiments is a default.

### Seed 1 · {name}

- **Premise.** {one line}
- **Hook.** {why someone stops scrolling}
- **Why it fits.** {taste ids}
- **Why it suits short-form.** {recurring situations; a day-to-day and an extraordinary mode; crossovers. Grade any mechanic you lean on: measured, reported, heuristic or proposal}
- **Cost.** {sets, cast, motion; from the cost anchors}
- **Main risk.** {the main way it fails}
- **Recommendation: {build on it | keep it as an ingredient | drop it}.**

### Seed 5 · {name} (deliberately against the owner's taste)

- **Premise.** …
- **Hook.** …
- **Why it is here.** {which T/A/X it goes against, and what evidence still favours it}
- **Why it suits short-form.** …
- **Cost.** …
- **Main risk.** …
- **Recommendation: …**

### Q7 · One world or many

- **Proposal.** {how the seeds could share one world}
- **Options.** {one world / separate worlds linked by crossovers / one seed only}
- **Recommendation: …**

### Proposals (not asked)

1. **{idea}.** {why it fits, with taste ids}

### Answers

Answered in {channel} by {who}, {date and time}.

| Ask | Recommended | Answer (verbatim) | Matches? |
|---|---|---|---|
| Q1 `{r0-seed-slug}` | build | "{the ledger's answer text, verbatim}" | yes |
| Q7 `{r0-shape-ask}` | one-world | "{…}" | yes |

**What this settles.** {in prose}

**What it opens.** {the next frontier}

### Method notes

- {what worked in the process} / {what did not} / {what to change next round}

---

## Round 1: {frontier name} (asked {date})

### Facts gathered for this round

Facts are the agent's job (dispatch a research subagent); decisions are the owner's.

| Fact | Verdict | Source |
|---|---|---|
| {claim} | true / partly / false | {url or file} |

### Questions and recommendations

| # | Ask | Question | Recommendation | Why (taste or evidence) |
|---|---|---|---|---|
| 1 | `{r1-ask-id}` | {question} | **{option}** | {taste ids or a fact above} |

### Proposals (not asked)

1. **{idea}.** {why it fits}
2. **Against the grain: {idea}.** {what it breaks on purpose}

### Answers

*(waiting; copied verbatim from the ledger when they land)*

---

## Round 2: {frontier name}, headed-item form (asked {date})

#### R2-Q1 — {question title}

- **Ask id:** {r2-ask-id}
- **Question:** {the question and its options}
- **Recommendation:** {option} — {one-line reason}
- **Answer:**
  > {the owner's words, verbatim, including typos}

### Method notes

- {…}
