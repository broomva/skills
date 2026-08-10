---
name: what
description: |
  Explain the CONCEPTS a session used, at the operator's register, grounded in
  what actually ran. After an agent works, you are handed results built out of
  vocabulary you did not choose — primitive short-names, entity slugs, library
  names, terms of art from the diff. `/what` names those terms, ranks them by
  what actually blocks understanding, defines each one, and anchors it to where
  it appeared and to its knowledge-graph entity. Fired mid-conversation with a
  short slice it degrades to the re-pitch case: "that did not land, say it
  again with more context and a simpler register."
  USE WHEN: /what, "wait what", "what did you just do", "explain that again",
  "I don't follow", "you lost me", "what do those terms mean", "re-pitch that",
  "explain the concepts", "what is all this jargon", after an autonomous arc or
  a long PR when the vocabulary outran the operator.
  NOT FOR: a summary of actions taken (that is the P1 Bridge session log);
  state for the next agent (that is /handoff); teaching a whole body of work to
  mastery over multiple gated stages (that is /comprehend); explaining a named
  paper or external research topic (that is /eli5); continuing, fixing, or
  extending the work (/what explains, it never builds).
disable-model-invocation: true
user-invocable: true
argument-hint: "[term] [--scope session] [--all]"
---

# what — explain the concepts, not the timeline

A session ends. The work is done and the summary is accurate, and you still
cannot review the next PR in that area, because eight of the nouns were new.
That gap does not close by re-reading the summary. It closes by someone naming
the eight nouns and defining them.

Nothing else in the stack does this. Bridge (P1) records *what happened*.
`/handoff` writes *state for the next agent*. `/comprehend` runs a multi-stage
teach-to-mastery loop. `/what` is the fast one: **the vocabulary of the last
stretch of work, explained once, grounded in where it actually appeared.**

## The one rule

> **Concepts, not chronology.**
>
> If the answer reads "first I did X, then Y, then Z", it is a session log and
> it has failed. `/what` is organised by *idea*, ranked by *what blocks
> understanding* — never by what was hardest to build or said most often.

## Scope

`/what` explains **everything since you last asked** `/what`. One rule covers
both cases:

| You fire it | Slice | Behaviour |
|---|---|---|
| After a long arc | since the last `/what`, else the whole session | full concept inventory |
| Right after one dense message | that message | the re-pitch case (below) |
| `/what <term>` | the whole session | one concept, in depth |
| `/what --scope session` | whole session, markers ignored | full inventory |

**The re-pitch case.** When the slice is short or plain, the script returns an
empty inventory. That is not a failure — it is the signal to do what
`wait-what` does: say the last message again, with more context, shorter
sentences, and the workspace's own words. Do not report "no concepts found."

## Procedure

### 1. Build the inventory (deterministic — never do this by eye)

```bash
python3 scripts/what_concepts.py --json          # since the last /what, current project
python3 scripts/what_concepts.py --scope session # whole session
python3 scripts/what_concepts.py --conversation docs/conversations/<id>.md
```

It resolves the transcript, extracts candidate terms from the agent's prose,
and returns each one with four facts that decide the explanation:

- **uses** — how load-bearing the term was.
- **agent_introduced** — the human never used this word. High-value: you
  brought it, so you owe the definition.
- **defined_inline** — already glossed in-session. If yes, do not re-explain
  it; reference it.
- **coverage** — `grounded` (an entity page exists; read it), `partial`,
  `ungrounded` (nothing — a Bookkeeping (P6) candidate).

Ranking is deliberately *not* frequency-first. A term said 200 times and
already defined ranks below a term said twice and never defined.

### 2. Read the grounded claims before writing a word

Every `grounded` row carries an entity path. Read those bodies. The knowledge
graph already holds the workspace's own definition, and inventing a second one
is how two vocabularies for one idea get created.

### 3. Explain, in rank order

Top rows first. Stop at the point where the remaining rows would not change
what the operator can now do. Six well-explained concepts beat twelve listed.

### 4. File the ungrounded terms — do not ask

Every `ungrounded` row that the agent used repeatedly is a Bookkeeping (P6)
candidate. File it, then report. P6 is a reflex, never a question.

## The register

Borrowed from `wait-what` and made explicit. These are the rules the
explanation is graded on:

1. **One idea per sentence.** Active voice. Under ~25 words.
2. **Define on first use.** No term from the inventory may appear in an
   explanation before its own definition.
3. **Use the workspace's words.** `Bookkeeping (P6)`, not "the filing thing".
   Ubiquitous language comes from `CLAUDE.md` and the entity slugs — never
   invent a synonym for something that already has a name.
4. **No enum names, no internal identifiers, no file paths as nouns.** Those
   are anchors, not explanations. `.control/policy.yaml` is where a rule lives,
   not what the rule *is*.
5. **Every concept gets a contrast.** State the nearest thing it is confused
   with, and the difference. A definition without a boundary does not stick.
6. **Every concept gets an anchor.** Where it appeared in *this* session:
   `file.py:120`, a PR number, a commit. Ungrounded and unanchored is a
   vocabulary lesson, not a `/what`.
7. **Say what you are unsure of.** A term you used but cannot define is the
   most useful line in the answer.

## Output shape

```markdown
## The short version
Three sentences. No term from the inventory appears here.

## Concepts

### <Term> — <five-word gloss>
**What it is.** Two or three short sentences.
**Why it showed up.** <anchor: file:line / PR / commit>
**Not to be confused with.** <nearest neighbour, and the difference>
**Where it lives.** <entity path, or "not in the knowledge graph yet">

## Not in the knowledge graph yet
<terms filed as P6 candidates, with what was filed>

## If you remember one thing
One sentence.
```

## Anti-rationalization

| Excuse | Reality |
|---|---|
| "I'll just summarise what I did." | That is the Bridge (P1) log. `/what` explains ideas; a timeline is the failure mode, not a shortcut to it. |
| "I'll pick the concepts by eye." | Selection is precision work. Run the script — by eye you pick what *you* found interesting, which is the opposite of what blocked the reader. |
| "The inventory came back empty, so there's nothing to say." | Empty means re-pitch. Explain the last message again, simpler. Never report the empty table. |
| "This term has no entity page, so I'll skip it." | An ungrounded, heavily-used term is the *highest*-value row and a P6 filing candidate. |
| "Should I file the missing entities?" | Never ask (P6). File, then report. |
| "While explaining, I noticed a bug — let me fix it." | `/what` explains. Name the bug, do not fix it in this turn. |
| "I'll define it in my own clearer words." | If the knowledge graph already names it, its words win. Two vocabularies for one idea is the cost. |

## Composition

| Need | Reach for |
|---|---|
| Rank the terms | `scripts/what_concepts.py` (this skill) |
| Read a grounded entity | `/kg load <slug>` |
| File an ungrounded term | `/bookkeeping` (P6) |
| Teach a body of work to mastery | `/comprehend` |
| Explain an external paper | `/eli5` |
| State for the next agent | `/handoff` |

## Validation (skill self-test)

A `/what` answer is well-formed iff:

- [ ] `what_concepts.py` was actually run, and the answer's concepts come from its top rows
- [ ] No section is ordered by time
- [ ] Every explained term has an anchor in this session
- [ ] Every `grounded` term's entity body was read before it was explained
- [ ] Every `ungrounded` term was filed via P6, not merely noted
- [ ] Each concept states what it is *not*
- [ ] The short version contains no term from the inventory

Script tests: `python3 -m pytest scripts/test_what_concepts.py -v`

## References

- `scripts/what_concepts.py` — the deterministic inventory + knowledge-graph coverage classifier.
- `scripts/test_what_concepts.py` — its unit suite (the step-3 skillify gate).
- Prior art: [`mattpocock/skills` `productivity/wait-what`](https://github.com/mattpocock/skills/tree/main/skills/productivity/wait-what)
  — the terse mid-conversation re-pitch. `/what` keeps its two best ideas (pin
  the register, pin the vocabulary source) and adds session scope plus
  knowledge-graph grounding.
