# Non-Technical Engineering Skills

The talk's last 8 minutes (32:00-40:00). Most architecture content treats
these as out-of-scope. The talk treats them as load-bearing — and the eight
years of context backs that up.

## 1. Diplomacy as an engineering skill

> "I have grown tremendously in my diplomacy skills, conflict avoidance,
> probably conflict resolution as well. Being able to persuade, propose
> ideas, being able to teach, educate, and mentor. These are the
> non-technical things that you probably don't hear a lot about."

**Why this is engineering, not just soft skill**: a technically-correct
decision that nobody implements has zero value. The path from "I see the
right thing to do" to "the team does it" routes through diplomacy.

**The diplomatic skill stack** (implicit in the talk):

1. **Self-awareness** — knowing your own emotional state, biases, blind
   spots. Without this, every conflict is the other person's fault.
2. **Awareness of the other person** — what motivates them, what they're
   afraid of, what they've already heard from you.
3. **Persuasion** — framing your proposal in terms of *their* goals.
4. **Conflict anticipation** — seeing the disagreement before it happens.
5. **Conflict resolution** — when the disagreement is here, getting both
   parties to a workable outcome.

**Where diplomacy shows up in platform engineering specifically**:

- **Forcing-function rollouts** (see [03-platform-migration.md](03-platform-migration.md))
  require buy-in from product teams who will lose autonomy.
- **Sidecar contributions** (see [02-edge-compute-sidecars.md](02-edge-compute-sidecars.md))
  require negotiation between the platform team (owns the contract) and
  feature teams (own the sidecar implementation).
- **Long-term maintenance investments** require selling refactor work to
  leadership that wants new features.
- **Incident retrospectives** require blameless investigation across teams.

## 2. Personality conflicts are inevitable

> "I was exposed to different types of managers and colleagues over time.
> And everyone has different personalities and styles of working. And
> because I was exposed to so many different types, I experienced
> conflicts with certain people. And even though I had conflicts,
> there's still people that I respect."

**The framing matters**: conflict ≠ disrespect. You can disagree
fundamentally with someone's style or decisions while still respecting
their intellect, integrity, or contribution.

**What you can do**:

- Anticipate conflicts before they happen, based on style mismatches.
- Take responsibility for your half of the dynamic.
- Recognize when the relationship can't be fixed and choose your battles.

**What you can't do**:

- Force someone else to change their style.
- Win every conflict.
- Make all conflict go away through technical correctness.

**The career implication** (the talk implies but doesn't state): if a
particular personality conflict is dominating your work life, sometimes
the right move is to leave that team, not "fix" the conflict.

## 3. Curse of knowledge

> "I don't know. Maybe I do feel like I have the curse of knowledge. And
> that this stuff seems easier to me now because I I've done so much
> with it."

**The phenomenon**: things you've done many times feel obvious to you.
You forget what it was like to not know them. You then explain things in
shorthand and assume the listener tracks. They don't.

**Why this matters specifically for platform engineers**: you've built the
thing. The teams using it are seeing it for the first time. Your
documentation, your error messages, your onboarding guides — all written
with the curse — make sense to you and not to them.

**Tactics to counter**:

- **Watch a real user navigate your docs for the first time, silently.**
  You'll see exactly which mental leaps they can't make.
- **Have a new hire write the onboarding doc.** They still remember what
  they didn't know.
- **Defer to confusion as signal, not weakness.** If a smart engineer is
  confused by your interface, the interface is wrong, not the engineer.

## 4. Mentoring is different from teaching

> "I find it easy to help people to point out areas where they need
> understanding and to deliver that understanding to them, to break
> down complex things into simple terms so that they can build a
> mental model of the system that they're working on. I have that
> ability. I'm quite good at that. But mentoring is distinct from that.
> ... What I found personally difficult was striking the balance between
> how much time I give to the mentee and what that time would consist of,
> whether it's — I didn't want to give them answers to problems, but I
> don't want them to get so stuck that they become frustrated."

**The distinction**:

- **Teaching / training**: I have knowledge X, I transfer X to you. Goal:
  you have X.
- **Mentoring**: I help you become someone capable of acquiring X (and Y
  and Z) on your own. Goal: you have *agency*.

These are different jobs. The skills are related but not identical. Most
senior engineers are good teachers (they've internalized enough patterns
to explain them). Fewer are good mentors (which requires *restraint*
about explaining).

**The mentoring tension**:

```
                  too much help
                       │
                       ▼
            Spoon-feeding.
            Mentee never struggles, never grows.
                       │
                       │
                   middle
                       │     ← target: mentee gets stuck enough
                       │       to learn, but not so stuck that
                       │       they give up
                       │
                       ▼
            Sink-or-swim.
            Mentee frustrated, learns the wrong lessons,
            or quits.
                       │
                       ▼
                 too little help
```

**Tactics for staying in the middle**:

- **Time-boxed struggle**. "Spend 30 minutes on this. If you're still
  stuck, come find me." Sets explicit expectation.
- **Hint, don't answer**. "Have you looked at how X handles this case?"
  rather than "Do Y."
- **Explain reasoning after they solve it**. They've already invested
  effort; now your explanation has somewhere to land.
- **Notice and name what they did well**. Specific praise reinforces the
  pattern.

**The honest caveat from the talk**: "I have no idea if I reached that
balance, but I suppose the results speak for themselves. I'm not sure if
I can attribute the results to me necessarily." Mentoring is hard to
evaluate even after the fact. Don't overclaim.

## 5. The colleague-as-customer model

> "Training my colleagues, getting them to understand, working through
> problems with my colleagues, that was essentially my bread and butter
> during the last half of my employment. Jumping on a call and going
> through stuff. Feedback that I got from my colleagues all the time
> was that I was always available to help and that I could boil down
> hard topics into something that was understandable."

A senior engineer at scale spends progressively less time writing code
and more time *teaching colleagues*. This is not a side-quest; it's the
job. Code review, design review, paired debugging, ad-hoc Slack questions
— this is how a senior engineer multiplies.

**The trap**: many engineers see helping colleagues as interruption from
their "real work" (their own code). At sufficient seniority, *that is
the real work*. Trying to fight it produces a senior IC who writes a lot
of code that nobody else can change.

**A heuristic**: if you ever feel that your job has shifted from "write
code" to "help other people write code", you have probably become a senior
engineer. The transition is involuntary and one-way.

## 6. The non-technical evaluation criteria

The talk hints at how senior engineers should evaluate themselves:

- Have I left the system in a state someone else can change?
- Have I distributed enough knowledge that my absence isn't an incident?
- Have I taught the next layer of engineers enough that they can teach
  the layer after that?
- Have I handled conflicts in a way that's productive rather than
  scorched-earth?
- Have I anticipated the political and organizational costs of my
  technical decisions?

These don't appear in performance reviews as bullet points, but they're
what the speaker is implicitly proud of in retrospect.

## Linking back to architecture

These non-technical skills are not separate from the architecture
chapters earlier in the talk. They are the *substrate* that lets the
architecture survive:

- The control plane / data plane split (architecture) only works because
  the platform team can negotiate with backend teams about who owns what
  (diplomacy).
- The sidecar model (architecture) only works because cross-team
  contribution requires teaching and patience (mentoring + curse-of-
  knowledge counter-tactics).
- The forced migration (architecture) only works because the platform
  team has cultivated enough relationship capital to spend on the forcing
  function (diplomacy + conflict anticipation).
- The long-term maintenance discipline (architecture) only works because
  the platform team has built distributed knowledge across colleagues
  (the colleague-as-customer model).

This is why the talk's chapter ordering is correct. The architecture
sections set up *what* was built; the non-technical sections explain
*how it survived eight years*. Skip the second half at your peril.
