# The method in full

The world-building grill is `/grilling` (a design tree worked in rounds, the whole frontier per
round) with four additions: a distilled owner, a divergent round 0, proactive proposals, and
documents written after every round. This file is the long form of SKILL.md's method. Lessons
behind each rule are in `lessons.md`, with the round that taught them.

## 1. Before the first question

### Distil the owner

Read what describes them, in this order, and stop when new sources stop adding signals:

1. Their own words about themselves (persona notes, an about page, a profile).
2. Their memory index and recent answered asks: budgets, policies, what they already decided.
3. Their own productions: the rules they kept, the look they built, what they cut.
4. Their design system and file names. A palette or a state already named after a place is a
   stronger signal than a stated interest.
5. The brief that started this session.

Write `owner-taste.md` (template: `templates/owner-taste.md`). Every row has an id (`T`, `A`, `G`,
`X`) and a source key. Cite the source that actually says it: a signal that comes from the brief is
sourced to the brief, not to a persona file that does not contain it. Signals handed over in a
brief are verified, not copied. Include "Against the grain" (what goes against them) and "Open"
(what no source answers, and the round where it will be asked).

### Separate decided from proposed

At the top of `decisions.md`, list:

- **Already decided**: each with the ledger and ask id that answered it. Never re-ask these.
- **Open**: spec proposals, earlier sessions' ideas, names in drafts, assets on disk. A rule in a
  spec or a note is decided only when an answered ask backs it. A spec saying "lab remixes are
  non-canon" is a proposal until the owner answers it.

Inventory what is on disk in `evidence.md`: path, what it is, how it was made. Nothing there is a
default.

### Read the target formats

Every field skene's library and content-engine's templates need is a leaf of the tree
(`output-contract.md`). Read the cost anchors too: unit prices from the production tool, dated.
They change the pitches (motion transfer can cost many times what original motion costs).

## 2. Round 0: diverge

Pitch 4 to 6 genuinely different worlds. Check the facts each hook depends on before pitching
it (a creature that lives at that depth, an event that really happens daily): an owner builds on a
pitch, and a false premise found later costs a rebuild. Each seed card:

| Field | What it says |
|---|---|
| Premise | one line |
| Hook | why someone stops scrolling, in the first second |
| Why it fits | taste ids (`T1`, `A2`) |
| Why it suits short-form | recurring situations; a day-to-day and an extraordinary mode; crossovers. Grade every mechanic it leans on |
| Cost | sets, cast, motion, from the cost anchors |
| Main risk | the main way it fails |
| Recommendation | build on it / keep as an ingredient / drop it |

- At least one seed stretches past the obvious; one goes deliberately against the owner's taste
  (mark it in its title, or `**Stretch:** yes`). The owner may build on it: keep it honest, not a
  straw man.
- Ask **one question per seed** with three options (Build on it / Keep as an ingredient / Drop
  it). A ledger ask allows 2–4 options, and per-seed answers let the owner mix seeds without a
  separate "which combination" question.
- Ask the **shape question** in the same round, framed conditionally ("if you build on several,
  should they share one world?"). Owners tend to answer the shape before the parts. Offer more
  than one world and many worlds: a universe of a few shared laws, where each account is a world
  of its own genre and audience, is a shape owners pick.
- Propose how the seeds could combine, as a proposal, not a premise.

A seed ask, in ledger form:

```yaml
- id: r0-seed-<slug>
  headline: "World seed 2, <name>: <premise in a few words>. Build on it?"
  options:
  - id: build
    label: Build on it
    consequence: It becomes the core, or one of the cores, of the world; round 1 asks its tone and rules.
    reversible: true
    recommended: true
  - id: ingredient
    label: Keep it as an ingredient
    consequence: Its places, characters or formats can be borrowed by the chosen world.
    reversible: true
  - id: drop
    label: Drop it
    consequence: It leaves the bible.
    reversible: true
  class: decision
```

## 3. Rounds 1..N: converge

Recompute the frontier after every round: every decision whose prerequisites are settled. Ask all
of it at once, about 8 questions. A question whose answer depends on another open question waits.

Before asking, gather the facts the recommendations lean on (dispatch a research subagent) and
record them in a "Facts gathered" table with a verdict (true, partly, false) and a source. A
"partly" changes the wording of the question, not just a footnote.

Each question: a number, the ask id, the question with its options, the recommendation, and a
one-line reason tied to a taste id or a gathered fact.

Keep **Other** open on every early-round ask. An Other answer to a narrow question can reframe the
world; the owner's words are then the decision, read as written and never mapped onto an option.

After the answers land:

- **Look for a direction.** When the owner's departures from your recommendations all lean one
  way (more freedom per part, more of the against-taste register), move the next round's
  recommendations that way.
- **Reconcile, don't overwrite.** When a later answer pulls against an earlier one, record both
  verbatim, mark the affected canon facts `review: open — <ask id>`, and ask one reconciliation
  question with a recommended synthesis. Resolve the field when it is answered.
- **Ask back on a slip.** A dictated answer can carry a slip. Ask with the best reading
  recommended; never guess silently.

### The design tree

| # | Node | Leaves (what must be settled) |
|---|---|---|
| 1 | Seed and premise | the shape (one world or many), the seeds built on, the premise sentence |
| 2 | Tone, genre, rating, audience | one tone or a register per part; who it is for; spoken or wordless |
| 3 | World rules | the one rule every post leans on; physics; magic or technology; who lives there; time model |
| 4 | Setting and geography | the map; real or invented; named on screen or not |
| 5 | Factions | who wants what against whom |
| 6 | Cast | per character: species and body (character template), want, flaw, voice, look, relationships, accounts |
| 7 | Visual DNA | render style, palette roles in hex, the light rule, camera package, grade, texture, the NO list |
| 8 | Sound | music, sound logo, SFX palette, how characters speak |
| 9 | Language | spoken language, captions, signage, invented words |
| 10 | Channels, formats, hooks | accounts and their roles; formats; hooks; graded mechanics; one-character-per-account exceptions |
| 11 | Timeline and arcs | dated canon events; season arcs; the recurring calendar |
| 12 | The nexus | how accounts connect; always disclosed as fiction |
| 13 | Names and handles | working titles become names |
| 14 | Canon governance | tiers and who may write each; whether lab or parody content is ever canon |
| 15 | The asset manifest | every library entry; stills per character; the estimate |

Visual DNA comes after cast because a light rule often belongs to a character ("never in full
light until…"). Names come late because a name chosen early anchors everything after it.

### Proposals

Each round may close with ideas the owner did not ask for, each with why it fits. Include one
against the grain. A proposal is not a question: it needs no answer until it is asked, and it enters
canon as `draft`. Once it is asked and answered, it is a decision like any other and
can lock a fact.

### Evidence grades for short-form mechanics

Research claims about what works on short-form platforms vary in strength. Every mechanic a seed
or format leans on carries a grade (`accounts.md`, W19):

| Grade | Means |
|---|---|
| measured | counted on real posts, with a method and a sample |
| reported | a credible source states it; not measured here |
| heuristic | a low-confidence pattern (a keyword count, a few examples) |
| proposal | someone's idea, including a spec's |

Never call a mechanic "proven" unless it is measured.

## 4. The asks channel

When the owner answers through Maestro on a phone:

- One ledger per world arc, `.control/asks/<arc>.yaml`, written to `DECISION-LAYER.md`: one ask
  per question, 2–4 options, exactly one recommended (the reversible one), `headline` ≤ 100
  characters ending in "?", `stakes` and `why_you` one sentence each.
- Stamp it so answers route back: `python3 scripts/ask_ledger.py stamp <ledger> --agent-id
  "$PASEO_AGENT_ID" --cwd "$PWD" --provider claude --session <name> --claude-session
  "$CLAUDE_CODE_SESSION_ID"`, then `validate`.
- Post the same round in the session as well.
- Read answers from the ledger file. Relayed messages trail it; a relay that matches a recorded
  answer needs only an acknowledgement. Read `answer_note` (a condition on the choice) and
  `answer_other` (none of the options: the owner's words are the decision, do not map them onto an
  option) before acting.

## 5. Document as you go

After each round's answers land, before the next round goes out:

1. Copy every answer verbatim into `decisions.md` (the answers table or `**Answer:**` lines).
2. Say what the round settles and what it opens.
3. Add or lock the facts in `canon.yaml`; update `bible.md` and every sheet the round touched.
4. Add `### Method notes`: what worked and what did not in the *process*, and what changes next
   round. These are how the skill learns.
5. Run `world_check.py check <world>`.

## 6. Finish

- The frontier is empty, `world_check.py check <world> --complete` passes, and the owner says the
  world is complete.
- Write a self-contained HTML summary for a human reader.
- Land the world in the owner's repository. Each asset in the manifest becomes a skene library
  entry when production starts; every run there is the owner's to approve.
