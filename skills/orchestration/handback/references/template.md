# handback template

Copy the skeleton. Delete blocks that are genuinely empty — but never the
receipt, and never reorder.

---

## ⛔ Blocked on you — {N} items, ~{M} min

| # | Ask | Unblocks | If you say nothing |
|---|---|---|---|
| 1 | **{Imperative}** — `{exact command, or the exact thing to click/paste}`. {One sentence of why, in plain words.} | {what it frees} | {the default} |
| 2 | **Pick one for {thing}.** {One sentence of plain-language context.}<br>&nbsp;&nbsp;**A** — {choice}. *{consequence}* ← suggested<br>&nbsp;&nbsp;**B** — {choice}. *{consequence}*<br>&nbsp;&nbsp;**C** — {choice}. *{consequence}* | {what it frees} | I do A |

> If more than 7 rows exist, show the top 7 by leverage and head the block
> `⛔ Blocked on you — 7 of {total} shown, rest in .control/asks/{arc}.yaml`.

**Reply by editing this** — every row pre-answered with the recommendation, so
you strike out what you disagree with instead of composing anything. **One line
per ask row, numbered to match:** a skeleton shorter than the table silently
drops the asks it omits.

```
1. done
2. A
```

## ▶ Running meanwhile

{What is still executing, or what completed with zero input. If nothing —
say so explicitly and say why every remaining lane is gated.}

## ✅ Shipped

| | |
|---|---|
| **{repo}#{pr}** | {one line: state, checks, merge disposition} |
| **{TICKET}** | {one line} |

## 🔀 Decided for you — {N} choices, least-confident first

| # | I decided | Why it was mine to take | Undo |
|---|---|---|---|
| 1 | {what the work does today, in plain words} | {what the spec left unsaid} | `{the one-line reversal}` |
| 2 | {…} | {…} | `{…}` |

> Generated — do not hand-write it:
> `python3 scripts/ask_ledger.py decisions .control/asks/{arc}.yaml --render-handback`
> Ordering, the 7-row cap and the `{n} of {total} shown` overflow header are
> enforced there and tested, not left to be remembered. Omit the block entirely
> when there are no decisions. Nothing here is a question — none of it stopped
> the arc, and every row carries its undo.

## 📋 Receipt

1. **Dependency chain** — {concrete upstream + downstream}
2. **Plan vs delivered** — {deviations explained}
3. **Parallel streams** — {which ran concurrently, how}
4. **Files changed** — {paths, one line each}
5. **PRs** — {urls, base, review state}
6. **Deploys** — {preview url / prod sha / none, with reason}
7. **Validation** — {tests, lint, typecheck, interaction evidence}
8. **Merge result** — {merged / blocked by which gate / awaiting}
9. **Follow-ups** — {tickets filed, knowledge promoted}

## 📎 Detail

→ `docs/handoffs/{YYYY-MM-DD}-{arc}.md` — the narrative: what happened and why,
the review rounds, the corrections, the reasoning that did not fit above.

---

## Worked example

Rewritten from a real 97-hour session that ended with **zero question marks**
and three asks buried in prose.

### Before

> Both PRs open, CI green, CLEAN. Stopping here — neither merge is mine to make.
> … **bstack#102** — 5 commits, 74 assertions, 41/41 suite, CI green. Not merged
> — auto-merge correctly blocked, `feature/bro-*` requires P20 ≥7/10, verified
> score is 5/10. …
> *Your call.* Two decisions are yours. bstack#102: the core fix is solid and
> confirmed by all four rounds; every unresolved finding is in cached-path edge
> handling. It could be split — land the core, defer the hardening. workspace#403
> just needs a merge.
> One thing I did not do: the fix won't execute until `scripts/leverage-sensor.py`
> is copied to `~/.agents/skills/bstack/` post-merge.

Three asks. None imperative, none with a default, the third a subordinate clause
in a paragraph about something else, the block at 88% depth.

### After

## ⛔ Blocked on you — 2 items, ~2 min

| # | Ask | Unblocks | If you say nothing |
|---|---|---|---|
| 1 | **Merge `workspace#403`** — `gh pr merge 403 --squash --repo broomva/workspace`. Tests and lint are green; it needs a human because personal branches have no auto-merge rule. | The knowledge entry lands | It stays open; nothing depends on it |
| 2 | **Pick one for `bstack#102`.** The review score is 5 out of 10; this branch needs 7 to merge automatically. The main fix is solid — four independent reviews confirmed it. Everything unresolved is in extra safety code added afterwards.<br>&nbsp;&nbsp;**A** — Split it: merge the main fix now, follow-up for the safety code. *Fastest; the fix works today.* ← suggested<br>&nbsp;&nbsp;**B** — Keep reviewing until it scores 7. *The last three rounds each found a new problem in the previous fix, so this may not converge.*<br>&nbsp;&nbsp;**C** — Close it unmerged. *We lose the fix; the bug is live.* | The fix reaching the copy that actually runs | I do **A** |

**Reply by editing this:**

```
1. done
2. A
```

## ▶ Running meanwhile

Nothing — both remaining lanes are gated on the two rows above. Everything else
in the arc is done.

## ✅ Shipped

| | |
|---|---|
| **bstack#102** | 5 commits, 41/41 suite, CI green, open |
| **workspace#403** | lint clean, CI green, open |
| **BRO-2170 / BRO-2171** | filed, not half-built |

## 🔀 Decided for you — 2 choices, least-confident first

| # | I decided | Why it was mine to take | Undo |
|---|---|---|---|
| 1 | Kept the cached-path safety code on the branch and scoped it into a follow-up ticket, instead of reverting it so the core fix could merge clean. | The spec said "land the fix"; it never said what to do with hardening added mid-review that the gate then flagged. | `git revert 4f2a1c` on the branch — the core fix does not depend on it |
| 2 | Filed the leftovers as **two** tickets (BRO-2170, BRO-2171) rather than one, splitting the sensor copy-step from the cached-path work. | Nothing specified ticket granularity. | Close BRO-2171 as duplicate and fold its body into BRO-2170 |

> Row 1 is first because it is the least confident of the two: it is the one
> that shapes whether option **A** above is actually cheap.

## 📋 Receipt

*(nine items, unchanged)*

## 📎 Detail

→ `docs/handoffs/2026-08-17-leverage-sensor.md` — includes the post-merge step:
`scripts/leverage-sensor.py` must be copied to `~/.agents/skills/bstack/` or the
fix does not execute.
