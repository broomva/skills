# Deconstruction card and script

## Deconstruction card: one per outlier

```markdown
# <ref-handle> · <url> · <ratio>x its normal (<views> vs <baseline>)

## Hook (0–2 s)
- Seen:   what is on screen in the first frame
- Said:   the first spoken line, verbatim
- Text:   the on-screen text, verbatim
- Why it stops a thumb: the gap, claim or contradiction it opens

## Hold (3 s)
Why someone is still watching at 3 s: the promise, the open loop, the visual change.

## Structure
1. beat (start–end s): what it does, not what it says
2. ...

## Turn
Where the payoff or twist lands, at what second.

## Ask
How it asks for the follow, comment, save or share, and the incentive.

## Shots
| # | start–end | shot | on-screen text |
```

Use `{{unknown}}` for anything you could not see or hear. Never guess a frame.

## Script: `runs/<date>/script-<n>.md`

```markdown
---
source: <url>          # structure source only
target_seconds: 28
---
## HOOK
1. <candidate> — rules met: H1, H3 — score 3
2. <candidate> — ...
3. <candidate> — ...   ← chosen

## STRUCTURE
The beats lifted from the reference, renamed for our topic.

## BODY
| s | line (our voice) | scene |
|---|---|---|

## CTA
One ask. If it asks for a comment, say what the commenter gets.
```

Timing: about 2.5 spoken words per second. A 28 s script is roughly 70 words.

## Starter hook rules: `rules/hooks.md`

These are a seed, not a method. Each account's rulebook grows from its own
winners (stage 11). A rule earns its place by winning at least 2 of 3 times and
loses it the same way.

- **H1:** The first frame alone is a complete thought. Muted, a viewer can tell
  what this is about.
- **H2:** The first spoken line is under 12 words and opens a gap: a result
  without its cause, or a claim against common sense.
- **H3:** The on-screen text does not repeat the spoken line. It adds a second hook.
- **H4:** Concrete beats abstract: a number, a name, a time ("at 3:55 a.m.").
- **H5:** Something changes on screen before 1.5 s.
- **H6:** The payoff the hook promises arrives before the last 20 % of the runtime.
