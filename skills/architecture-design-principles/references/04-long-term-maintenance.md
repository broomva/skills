# Long-Term Maintenance: The 8-Year View

The talk's most underrated section. Most architecture content focuses on
greenfield decisions; this section is about what those decisions look like
five years later.

## The core observation

> "Building something is easy. Changing it and making sure that you can
> still change it over time is difficult. Because as you change things,
> it slowly becomes harder to change. Things start to get coupled, and
> all of a sudden when you change something in one area, it affects
> another, and you have to deal with the task of detangling something."

This is the single most important sentence in the talk. The shape of code
quality is not a stable plateau — it's an exponential decay unless
actively fought. Every change creates some coupling; the integral over
many changes is a system that resists further change.

## Churn as a smell

> "The area that churns becomes predictable where all the churn is going
> to be at a certain stage. And once you notice that there is some churn,
> it's sort of a smell. It is — it's an indication that part of the
> service or project is going to keep increasing in size or complexity."

**Mechanism**: a file that keeps changing is doing too many jobs.
Each new requirement adds another condition, another branch, another
flag — because the existing shape doesn't naturally accommodate the
requirement, you patch around it. The patches compound.

**Detection**:

```bash
# Top 20 files by commit count in the last year
git log --since="1 year ago" --name-only --pretty=format: \
  | sort | uniq -c | sort -rn | head -20
```

Files at the top of this list are your churn hotspots. Don't refactor
all of them — pick the ones that *also* show up frequently in incidents
or in code review comments.

**The action when you find churn**:

1. **Read the recent commit messages on that file.** What kept changing?
2. **Is there a missing abstraction?** Often the churn is because N
   slightly-different things share one file. Split into N+1 files (the
   common shape + N variants).
3. **Is there a missing extension point?** Often the churn is because
   every new requirement adds a flag. Replace flags with a plugin / strategy
   pattern.
4. **Document the invariant.** Sometimes the file is just inherently
   complex. Capture the invariant so future authors don't break it
   accidentally.

**When *not* to act on churn**: the file is still in active development.
A new feature's main file will always churn during build-out. Churn is a
smell on *finished* features that keep changing.

## Build vs Maintain are distinct skills

The talk implies a hierarchy:

- **Building** — write code that solves the problem for *now*. Most
  bootcamp/CS curriculum stops here.
- **Maintaining** — write code that *can be changed* for problems you
  don't yet know about. Requires modeling future change.
- **Operating** — write code that someone *else* can change, debug, and
  diagnose during incidents. Requires anticipating who that someone is
  and what they'll know.

A senior engineer is differentiated by maintain + operate. A junior engineer
typically only builds.

**Implication for hiring and team composition**: a team of all-builders
will produce a system that nobody can maintain after the original authors
leave. Atlassian's eight-year tenure across this team is what produced the
maintenance perspective — without that retention, the maintenance lessons
are externalised onto whoever inherits the codebase, usually badly.

## Operator-centric documentation

> "When [people] become on call, they know where to look, what could go
> wrong, where do things break essentially. So you know, that's whether
> that's knowing what kind of what particular log messages mean, what
> sort of metrics to check when something is going wrong and what those
> metrics could allude to, how to resolve those particular expected
> problems if they're not automated away."

**The four artifacts** every long-lived service needs:

1. **Log message catalog**. For every distinct log line in the system,
   what does it mean? What does it imply for operator action? Critical
   ones should include a runbook link.
2. **Metric catalog**. What metrics matter? What's the normal range? What
   does a deviation imply? What dashboard shows it?
3. **Failure mode catalog**. What can break? What's the symptom? What's
   the resolution? Common entries: "AWS region outage", "SQS unavailable",
   "DynamoDB throttling", "bad config pushed".
4. **Recovery procedures**. For each failure mode that isn't auto-healed,
   what does an on-call engineer do?

**At Atlassian**: the talk lists exactly these — "Amazon could have an
outage and the database isn't accessible... SQS stops working... a proxy
receives bad configuration... configuration that's valid but destroys the
traffic." Each of these is a runbook entry.

**Anti-pattern**: a 50-page architecture document that doesn't tell on-call
what to do at 3am. Architecture docs are for *new* engineers; runbooks are
for *on-call* engineers. Different audience, different format.

## Onboarding is recurring, not one-shot

> "Over time people come and go. People get hired. People leave for other
> jobs. And so you get you have to do that onboarding again obviously.
> But you should have more people that are able to do that onboarding
> collectively."

**The lemma**: every piece of operational knowledge that lives only in
one person's head is a single point of failure. The cure is *distributed
knowledge production*, not heroic individual documentation.

**Tactics**:

- **Pair on-call**. Junior + senior share shifts. Junior asks questions
  during incidents. Senior captures answers as runbook updates.
- **Rotate ownership**. Code areas should have at least two owners.
  Mandate this in code review (no PR to an area with one owner approves
  itself).
- **Documentation as part of "done"**. A feature isn't done until the
  runbook entry is written. This is the only durable countermeasure to
  "we'll document it later".
- **Periodic re-onboarding drills**. Every quarter, ask a senior engineer
  to follow the onboarding docs from scratch. They will find rot.

## Coupling accretes silently

> "Things start to get coupled, and all of a sudden when you change
> something in one area, it affects another."

Coupling is the dual of churn: churn is the symptom, coupling is the
mechanism. A change that "shouldn't" affect another area but does is
evidence of hidden coupling.

**Two kinds of coupling worth distinguishing**:

1. **Compile-time / type coupling**. Shared types, shared interfaces.
   The compiler catches incompatibilities. This is the *good* kind.
2. **Runtime / behavioral coupling**. One module depends on the *behavior*
   of another (timing, order, side effects). The compiler doesn't catch
   this. This is the *bad* kind.

**Tactics to reduce behavioral coupling**:

- **Pure functions where possible.** No side effects, no implicit state.
- **Idempotent operations**. Calling twice should produce the same result.
- **Explicit contracts**. If module A depends on B doing X first, that
  ordering should be in code (call B then A) not in custom (call them in
  the right order).

## The AI-coupling risk

> "It'll be interesting with all these vibe coded apps and AI assisted
> apps to see how we handle that. When we have people that are not really
> familiar with what they've created, and the maintenance burdens appear.
> They don't appear at the beginning. There's just not enough going
> through. It hasn't been around for long enough. There hasn't been
> enough changes."

The 2026 version of the maintenance problem: code authored by AI, supervised
by a human who may not fully understand what was written.

**The risk model**:

- Building with AI is *fast*. You ship features faster than ever.
- Maintenance with AI requires the same understanding maintenance always
  required, but now the original author had less of it.
- When the system breaks, the AI that wrote it isn't on-call. A human is.
  That human reads code they didn't fully understand to start with.

**Counter-tactics (not in the talk, but the natural extension)**:

- **AI must write tests too**. The test suite encodes the assumptions; if
  it's complete, maintenance is tractable.
- **AI must write docs too**. The intent should be captured; the human
  reviewer should verify the docs match the code.
- **Pull-request review by a *different* AI**. Cross-model adversarial
  review catches what the writer-model missed (analogous to the bstack
  P20 Cross-Review primitive).
- **Stronger types**. The type system catches what the human doesn't.
  Rust > Python here.

The cautious read: AI-authored code amplifies the maintenance burden in
exactly the way the talk warns about. The hopeful read: AI-assisted
detangling may be the cure: "you might be able to find these areas quite
quickly, get an LLM to perform the detangling for you. I think if we can
do that, that's fantastic. But I don't want to be too optimistic just in
case."

## The maintenance budget

A useful frame the talk doesn't name explicitly: **every team has a
maintenance budget**, measured in engineer-weeks per year. If you spend
more than that on maintenance, no new features ship. If you spend less,
the maintenance debt compounds.

Healthy ratios (rough rules of thumb):
- **Building**: 50-70% of team time
- **Maintaining**: 20-30% of team time (refactors, doc, churn reduction)
- **Operating**: 10-20% of team time (on-call, incident response, runbook
  updates)

Teams that spend 95% on building are accumulating maintenance debt.
Teams that spend 95% on maintaining are not shipping. The talk's tone
suggests Atlassian's load-balancing platform team eventually settled
somewhere around the middle.
