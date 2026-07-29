# The ambiguity catalog

Every entry is one way a reader goes wrong, organized by the question they
cannot answer. Each gives the readings the text permits, the rewrite, and the
rule in ASD-STE100 Issue 9 that it comes from, so the source can be checked.

The rule numbers are pointers, not quotations. The standard is free at
[asd-ste100.org](https://www.asd-ste100.org).

`✓` marks a detector in `scripts/disambiguate.py`. The rest need judgment.

---

## A — Which thing?

Reference ambiguity. The text points at something without naming it, and more
than one thing is in reach.

### A1 · Bare pronoun or demonstrative ✓
*Rules GR-3, GR-4*

> If you engage the pins incorrectly with the seats, **they** can become damaged.

The pins, the seats, or both. Three different repairs. The standard's own
example, and it is instructive that the fix has three valid forms — the author
has to *decide*, which is the point.

Worse with a bare `this`, because a demonstrative can point at an entire
preceding clause:

> Make sure that the cover is not locked (**this** can cause damage to the probe).

Which causes the damage: the cover locked, or the cover unlocked? The
parenthetical inverts depending on your guess.

**Rewrite:** name the noun. `this` → `this <noun>`. Accept the repetition. A
document that is executed is not a document that is enjoyed.

### A2 · Noun stack of four or more ✓
*Rule 2.1*

> Runway light connection resistance calibration

Five words, one head noun (`calibration`), four modifiers, and no statement of
how any of them relate. The reader must hold four items and guess the bracketing
before the head arrives. Languages that put the head noun first make this worse.

**The insight:** a noun stack is a relation graph with the edges deleted.
Shortening it does not help. Restoring the edges does.

**Rewrite** with prepositions, then keep each group to three:

> Calibration **of** the resistance **of** the runway light connection

> ~~Remove the engine transmission housing attachment bolts.~~
> Remove the bolts **that attach** the transmission housing **to** the engine.

Note the second one recovers a *verb* that the stack had nominalized away. Noun
stacks hide actions as much as relations.

### A3 · Attachment ambiguity ✓ (advisory)
*Rule GR-2*

> Install the panel **with** the green fasteners.

1. Install the panel that has green fasteners.
2. Install the panel together with the green fasteners.
3. Use the green fasteners to install the panel.

Context usually resolves it. "Usually" is the problem. The standard's own
example of the failure mode is a joke when it fails:

> Lift the aircraft at the maximum takeoff weight **with passengers**.

**Rewrite:** if it is the instrument, keep the primary action verb and make the
instrument explicit (`Seal the opening with tool TS9867`, *not* `Use tool
TS9867 to seal the opening` — the primary action is `seal`, not `use`). If it
is a condition, move it to a leading `When …,` clause.

### A4 · Synonym drift ✓
*Rules 1.11, 9.4*

One item called `main body`, then `body`, then `body assembly` across three
steps. The reader concludes there are three parts and looks for two of them.

This extends past nouns to whole constructions. `Lubricate the two bolts with
oil` and `Apply a small quantity of oil to the threads of the two bolts` are
both fine, and using both for the same operation is not: the reader stops
recognizing the step and starts parsing it again.

**Rewrite:** pick one name and one phrasing per operation, and repeat it
exactly. In a codebase this is the same instinct that makes you name the
variable the same thing in every function.

### A5 · Word used with more than one meaning
*Rules 1.2, 1.3, 1.7, 1.13*

The core move of a controlled language: one word, one meaning, one part of
speech. `test the test`, `the display displays`, `monitor the monitor` — each
forces the reader to disambiguate a part of speech before they can parse.

In software specs the usual offenders are `support`, `handle`, `process`,
`manage`, `service`, and `check` — each a noun and a verb with several senses.

**Rewrite:** name the actual operation. `support SSO` → `accept a SAML
assertion from the configured IdP`.

---

## B — Who must, and must they?

Agency and modality. The sentence is grammatical and still does not say who
acts or whether they have to.

### B1 · Agentless passive ✓
*Rule 3.6*

> The data **is validated** before it is stored.

By what? The client, the API layer, the database constraint, the batch job?
Each is a different system. The passive reads as complete while naming nobody,
which is why it survives review.

**Rewrite:** name the actor and make it the subject. In an instruction, drop the
actor and use the command form: `Validate the data before you store it.`

**Not every passive.** With a named agent (`reviewed by the safety officer`)
the actor is present and this is a style cost only. The defect is the missing
owner, not the voice.

### B2 · Instruction not in the command form ✓
*Rule 5.3*

> The test can be continued.

The standard's rationale is the sharpest thing in it. A non-command
construction leaves **three** questions open simultaneously:

1. Is it important to do this step?
2. Did someone else already do it?
3. Must someone else do it later?

`Continue the test.` answers all three by construction.

**Rewrite:** imperative. And do not prefix `must` to an imperative (`you must
disconnect the hose` → `disconnect the hose`) except in a genuine safety
instruction, where the emphasis is the content.

### B3 · Obligation strength undefined ✓
*Rules 1.3, 5.3*

`should`, `may`, `might`, `could`, `would`. Two readers ship two systems and
both claim conformance, because both readings were licensed.

`shall` is not a fix. It carries a legal register some readers apply and others
do not.

**Rewrite:** `must` (mandatory), `can` (capability or permission), `will` (a
future fact). If it is genuinely optional, say so **and give the default** —
optionality without a default is a second undefined decision.

### B4 · Dropped subject ✓
*Rule 4.2*

> If installed, remove the shims.

What is installed? The shims, or something else that implies shims? Shorter to
write, slower to read.

> If **the shims are** installed, remove them.

Same class: dropped verbs (`Rotary switch to INPUT` → `Set the rotary switch to
INPUT`), dropped nouns (`Can be a maximum of five inches long` → `Cracks can
have a maximum length of five inches`), dropped articles (`Remove the bolt and
stop` — one object or two?).

**The principle:** you may not buy brevity with ellipsis. Every deletion the
reader has to undo costs more than the words saved.

---

## C — How do I know it is done?

Verifiability. The sentence describes a wish rather than an observation, so
nothing decides whether it has been met.

### C1 · State-assertion with no action ✓
*Rule 4.1*

> No leaks are permitted.

True of a desired world. Names no action and no observation, so the reader
cannot act on it and a test cannot express it.

> **Make sure that** there are no leaks.

**The move:** convert every desire into an observation someone can make. This
is the single highest-yield transformation in the catalog, and it is why the
standard's approved phrase for a check is a command (`make sure that`) rather
than a state (`shall be ensured`).

### C2 · Direction of change with no baseline ✓
*Rule 4.1*

> Different temperatures will change the cure time.

Not false. Unusable. The reader learns that a relationship exists and nothing
about its direction or size.

> When the temperature increases, the cure time decreases.
> The cure time is 2 hours at a temperature of 20 °C.

**The test:** if no state of the system makes the sentence false, it cannot
fail, so it cannot be tested, so it is not a requirement. `Makes the login
flow faster` fails this. `Reduces p95 login latency from 800 ms to 200 ms`
passes.

### C3 · Vague predicate ✓
*Rules 1.3, 4.1*

`appropriately`, `gracefully`, `robust`, `efficient`, `user-friendly`,
`as needed`, `where possible`, `reasonable`, `sufficient`.

Each defers the decision back to the reader without telling them how to decide.
The disagreement is not avoided. It is postponed to review, when it is
expensive.

**Rewrite:** name the observation you would actually make — a number, a
threshold, a named state, or a command whose output you can read. If you cannot,
that is a finding in itself: **say which fact is missing and who has it.**

### C4 · Risk without consequence ✓
*Rules 7.1, 7.3*

> CAUTION: EXTREME CLEANLINESS OF OXYGEN TUBES IS IMPERATIVE.

Abstract, no action, and the wrong risk level — oxygen and grease explode, so
this is a warning (injury or death), not a caution (damage to equipment).

> WARNING: MAKE SURE THAT THE OXYGEN TUBES ARE FULLY CLEAN. OXYGEN AND GREASE
> MAKE AN EXPLOSIVE MIXTURE. AN EXPLOSION CAN CAUSE INJURY OR DEATH.

**The safety triple**, and it generalizes to any constraint worth stating:

1. **Level** — from an actual risk analysis, not from how strongly you feel.
2. **Command or condition, first** — what to do, before the explanation.
3. **Consequence** — the named outcome. Stating it is what makes a person
   careful. `can cause corrosion` beats `is not recommended`.

In a spec, the analogue is: severity, the check, and what breaks if it fails.
A constraint with no stated consequence gets traded away in the first crunch,
because nobody recorded what it was buying.

### C5 · No verification named
*Rule 4.1*

A requirement that states an obligation and never says how satisfaction is
observed. Every requirement should be answerable by: *what would I run, read,
or look at to know?* If the answer is "ask the author", the reader who cannot
ask is stuck.

---

## D — Can I hold this?

Atomicity and cognitive load. Each unit must fit in one pass and mean one
thing.

### D1 · Over-length ✓
*Rules 5.1, 6.3, 8.4 – 8.7*

20 words for an instruction, 25 for a description.

**Why they differ, and it matters:** an instruction is executed under load, one
step at a time, by someone holding a tool. A description is read as a unit by
someone who can re-read. Applying the procedural ceiling to prose produces
choppy nonsense. Applying the descriptive ceiling to a procedure produces steps
people get halfway through.

The counting rules are not naive word-splitting. Each of these is **one word**:

- a parenthetical group — `Remove the safety pin (10).` is 5
- a quoted span — `Touch the "Service Overview" arrow…` counts the quote as 1
- a run set off by uppercase — `Release the SHORT-CIRCUIT TEST switch.` is 4
- a number, and a number with its unit — `The unit weighs 20 kg.` is 4
- an abbreviation or alphanumeric identifier — `No. 1`, `36L7`, `VPN`
- a hyphenated compound — `soap-and-water`, `trial-and-error`
- a title, placard, or proper noun you cannot change
- in a vertical list, the colon ends a sentence and each item starts a new one

**Rewrite:** split at the clause boundary, or lift the enumeration into a
vertical list. Never shorten by deleting articles, subjects, or verbs (see B4).

### D2 · Compound obligation ✓
*Rule 5.2*

> Set the TEST switch to the middle position **and** release the SHORT-CIRCUIT
> TEST switch.

A reader can do the first, stop, and still record the step as done. It is also
not separately testable: when it fails you do not know which half.

**The exception is ontological, not stylistic.** One sentence is correct when
the actions genuinely occur at the same time:

> Remove and discard the seal.
> Hold the panel in its open position and install the fastener.
> Slowly extend the rod fully and make sure that it does not touch other parts.

You cannot split those without lying about the work. So the test is not "does
it contain *and*" — it is **"can these be done at different times by different
people?"** If yes, split.

### D3 · Semicolon ✓
*Rule 8.1*

Banned outright. It joins two independent clauses, so the unit now holds two
statements: a reader can satisfy one and miss the other, and a test cannot
report which half failed. Every other standard English mark is allowed.

### D4 · Paragraph overrun ✓
*Rules 6.1, 6.4, 6.5, 6.6*

One topic per paragraph, at most six sentences, and information given
**gradually** — each sentence introducing one subject, the next building on it.
Past six, the reader stops holding the paragraph and starts re-reading it.

### D5 · Mode mixing ✓
*Rules 4.3, and section 6 generally*

Procedural and descriptive content in one list or one paragraph. Scanning it,
the reader cannot tell which items are their responsibility and which are
background.

Related, and often missed: in a list of prohibitions, the `DO NOT` belongs on
**each item**, not hoisted into the stem. The reader who reads exactly one
bullet must see the negation. **Write for partial, non-linear reading** — every
unit carries its own subject, condition, and polarity, because you cannot
assume the unit before it was read.

Also: every item must grammatically complete the stem. A list whose items do
not join cleanly to the text before the colon is a list the reader re-parses
per item.

---

## E — Can I parse it at all?

Construction traps. The grammar itself admits two readings, or the form is one
a reader with a different first language cannot resolve.

### E1 · `-ing` forms ✓
*Rule 3.5*

`Changing filters` is the act of changing, or the filters that change. English
collapses gerund, participle, and progressive into one suffix, and most languages
do not, so the reader has no cue to pick.

**Rewrite:** a finite verb for the action, a plain noun for the thing. `-ing`
is safe only inside an established technical term (`landing gear`).

### E2 · Dropped `that` ✓
*Rule GR-1*

> Make sure the valve is open.

Native speakers drop it in speech and it migrates into writing. It hides the
boundary between the main clause and the subordinate one, and most languages
cannot drop the equivalent word — so a translating reader stalls exactly there.

> Make sure **that** the valve is open.

Cheap to add, and it costs one word against the ceiling. Add it.

### E3 · Condition after the action ✓
*Rules 5.4, 7.2*

> Set the switch to NORMAL when the light comes on.

The reader meets the command first. Under load they act, then discover it did
not apply. The condition is the **applicability test** and must arrive first,
separated by a comma:

> When the light comes on, set the switch to NORMAL.

This generalizes well past technical writing — it is why `if` precedes its body
in every language you write, and why a guard clause reads better than a trailing
conditional.

**The comma is load-bearing**, and this is worth seeing:

> If the drive does not operate correctly, disconnect it from the gearbox.
> If the drive does not operate, correctly disconnect it from the gearbox.

Both grammatical. Different instructions. The comma decides which verb the
adverb modifies.

### E4 · Contractions ✓
*Rule 4.2*

`don't`, `isn't`, `won't`. The negation hides inside a suffix, and a reader
skimming a `do not` step can miss it entirely — when the negation *is* the whole
content of the step.

### E5 · Latin abbreviations ✓
*Rule GR-6*

`e.g.`, `i.e.`, `etc.` assume a shared education. Readers routinely swap the
first two, which inverts *example* and *definition*. Use `for example` and
`that is`. For `etc.`, either name the remaining items or end the list — an
open-ended list in a requirement is an unbounded obligation.

### E6 · Opaque phrasal verbs ✓
*Rule 9.3*

`carry out`, `bring about`, `deal with`, `sort out`. Non-compositional: the
meaning is not the sum of the parts, so it cannot be looked up word by word.
Use a single verb (`do`, `cause`, `process`, `correct`).

Not all particle verbs — many are perfectly clear and some are approved
vocabulary. The defect is opacity, not the particle.

### E7 · Slash conjunctions ✓

`and/or`, `input/output`, `he/she`. The slash does not say whether it means
and, or, or both. Write the conjunction you mean.

### E8 · False friends
*Rule GR-5*

A word that looks like one in the reader's first language and means something
else. English `disposition` against Spanish *disposición* or Italian
*disposizione* — the writer means "instruction", English does not.

Unlike the others, this one is not detectable from the text alone: it depends
on who is reading. If your readers share a first language, learn the specific
traps for that pair.

### E9 · Possessives and other structures with no equivalent
*Rule GR-8*

The Saxon genitive (`the manufacturer's instructions`) is permitted and often
misread, because many languages form possession differently. When in doubt,
use `of`: `the instructions of the manufacturer`. The same caution applies to
any structure whose relation is carried by a bound morpheme rather than a word.

---

## The meta-lessons

Four things the standard demonstrates by construction, which outlast any
particular rule.

**1. Clarity comes from a closed state space, not from advice.**
"Be clear" is unenforceable. "At most 20 words, one instruction, one meaning
per word, no semicolon" is checkable, and clarity falls out. Any rule you
cannot check is a preference. This is the same reason a type system beats a
naming convention.

**2. A prohibition without a substitute is a complaint.**
The standard never lists a disallowed word without an approved alternative, a
compliant example, **and** the non-compliant one beside it. Any linter, review
comment, or style guide that flags without substituting is offloading the work
back onto the person who already could not do it.

**3. Structure before vocabulary.**
A word-for-word replacement is frequently not enough, and reaching for one is
the tell that the sentence needs restructuring instead. Most real ambiguity is
architectural: a stack that deleted its relations, a sentence carrying two
obligations, a condition in the wrong place.

**4. Rules are incident-derived, or they are taste.**
Every rule in the standard closes an observed failure. That is what earns it
the right to constrain a writer, and it is the standard to hold your own
conventions to: *what went wrong that this prevents?* A rule with no failure
behind it is decoration, and it will be ignored the first time it is
inconvenient.
