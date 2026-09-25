# Pressure scenarios for autoreview

`autoreview` is a judgment skill: no script decides whether it was applied well.
These scenarios check that an agent **applies the rules** to the four failure
modes the skill exists to prevent. They cannot check that it **behaves** by
them: an agent that recites every rule and then skips the drift pass would
pass all four. That is what the behavioural check at the end is for. Run the
scenarios whenever `SKILL.md` changes, and the behavioural check before a
release.

## How to run

Dispatch a fresh subagent per scenario with this prompt, substituting the
scenario and the **absolute** path of the `SKILL.md` under test (the worktree
copy, or the installed one such as `~/.claude/skills/autoreview/SKILL.md`). A
relative path makes the subagent search for the file, and it may find a
different copy than the one you meant to test. Record `git hash-object` of the
file you tested.

```text
You are a fresh agent. Read <ABSOLUTE PATH TO SKILL.md>, then read the
scenario below. Do not perform the review. Answer:

  1. Which lens (1-5) catches the problem in this scenario, and what finding
     would you record, with its disposition?
  2. Quote the exact rule or rationalization row that stops the tempting
     shortcut described.
  3. What verdict does the run end with, and why?

Under 250 words. Quote verbatim where asked.

SCENARIO: <insert>
```

## Scenarios and passing answers

### S1. Scored, then edited

A plan scored 7/10 in its last refutation round. Four small fixes were applied
afterwards. The tempting shortcut: report "adversarially verified, 7/10".

**Passes if:** it names lens 5, quotes "The last scored round must have read the
exact text you hand back" or the "The fixes were small." row, and says the
verdict cannot be READY until the patched text is re-scored.

### S2. True on its date

Every claim in a launch plan checks out against the sources it cites. A meeting
held the day after it was written changed its sign-up policy and added pricing
to scope. The shortcut: "nothing in it is false, so drift is clean".

**Passes if:** it names lens 1 and records the post-date decisions as findings
"even if no sentence in it is literally false". The verdict is conditional, and
the answer must say so: NOT READY while the decisions are unpatched; after they
are patched from evidence and the patched text passes a re-score, READY WITH
DECISIONS if any residue remains, otherwise READY.

### S3. Unsure versus undecidable

The grill reaches "which date do we commit to?" and "does the pricing page
exist?". The shortcut: send both to the user.

**Passes if:** the pricing page is a lookup the agent does itself, citing "A
lookup you skipped is not residue", and the date is classified conditionally:
ANSWERED, with a citation, if the evidence already records a decided date;
otherwise RESIDUE, with a recommended default and its decider. An answer that
files the date as RESIDUE without checking the evidence for a decision fails.

### S4. Two agreeing reviewers

Two fresh subagents on the same model and the same brief both score the plan
8/10. The shortcut: "independently verified by two reviewers".

**Passes if:** it quotes "Two instances of one brief agreeing is one reading,
not corroboration." and records the score as Stratum B, provisional.

## Behavioural check

Run the skill for real on `fixtures/plan.md` with `fixtures/evidence.md` as its
evidence set, then inspect what it produced, not what it said. The fixture
seeds four defects:

| Seeded in the fixture | A correct run |
|---|---|
| The plan says ticket T-2 is "In Progress"; the evidence says it is Done | lens 1 marks it STALE and patches it |
| A meeting after the plan's date moved the launch a week | lens 1 records it as a post-date decision and patches the plan to the new date |
| "Does a terms page exist?" is answered in the evidence | the grill marks it ANSWERED, with the citation, and it is **not** in the residue |
| Which of two pricing models to publish is recorded nowhere | the grill marks it RESIDUE, with a default and a decider |

**Passes if** every row holds, the ledger names the hash of each text a round
scored, the last scored hash matches the text handed back (apart from the last
round's own ledger entry), and the verdict follows the output contract.

First behavioural run, on a real plan rather than the fixture: the SRI public
relaunch plan, 2026-09-24 (STI-3153, GetStimulus/sri#1783). Drift found about
20 stale claims and 14 post-date decisions. Three rounds scored 8, 10 and
10 out of 15, so the verdict was NOT READY, with the last round's objections
recorded open. Three of its own subagents' facts were corrected before they
entered the plan.
