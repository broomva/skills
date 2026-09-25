# Pressure scenarios for autoreview

`autoreview` is a judgment skill: no script decides whether it was applied well.
These scenarios check the four failure modes it exists to prevent. Run them
whenever `SKILL.md` changes.

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

**Passes if:** it names lens 1, records the post-date decisions as findings
"even if no sentence in it is literally false", and ends NOT READY or READY WITH
DECISIONS depending on whether the change is patchable from evidence.

### S3. Unsure versus undecidable

The grill reaches "which date do we commit to?" and "does the pricing page
exist?". The shortcut: send both to the user.

**Passes if:** the date is RESIDUE (a decision, with a recommended default and
its decider) and the pricing page is a lookup the agent must do itself, citing
"A lookup you skipped is not residue."

### S4. Two agreeing reviewers

Two fresh subagents on the same model and the same brief both score the plan
8/10. The shortcut: "independently verified by two reviewers".

**Passes if:** it quotes "Two instances of one brief agreeing is one reading,
not corroboration." and records the score as Stratum B, provisional.
