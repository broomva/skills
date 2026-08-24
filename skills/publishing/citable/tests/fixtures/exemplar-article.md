I spent part of this year running a coding agent unattended. Not "AI-assisted". Actually
unattended: it pulled a ticket from Linear, wrote the code, opened a pull request, and
waited for CI. Nine iterations, nine merged pull requests.

CI went green on effectively all of them.

Then I put a second model in front of the diff, with instructions to refute rather than
approve. It found a genuine blocking defect in seven.

That gap is the whole subject of this piece. Not "AI writes buggy code", which everyone
already knows. The thing worth writing down is that my test suite was not the safety net I
believed it was, and I only found out because I built something whose job was to disagree
with it.

## What green actually certified

The defects the second model caught were not exotic. They shared a shape. The change did
exactly what the test asserted, and the test asserted the wrong thing.

The clearest case was my own mutation-testing script, the thing whose entire purpose is
checking that tests notice when you break the code. It reverted each mutation with
`git checkout -- <file>` before applying the next one. Sensible, except it also ran that
revert before the *first* mutation, against a working tree holding uncommitted
implementation work. That work was destroyed silently. Every mutation afterwards patched a
reverted file, so the whole "killed N of M" report was measuring nothing. Green, and
entirely noise.

Two more traps in the same tool, both of which I walked into.

A stale regex that no longer matches anything does not raise. It quietly no-ops, the code
is never mutated, pytest passes, and you record a false SURVIVED. That reads as "the tests
missed this" when in fact nothing was ever changed.

The inverse is worse because it flatters you. A mutant that crashes the program turns the
suite red, and red reads as KILLED. But the tests did not detect a behavioural change. They
detected a stack trace. Mutate a value rather than a branch, or you are only measuring
whether your code is capable of crashing.

## The failure mode underneath

There is a general version of this, and naming it changed how I build gates.

A check almost never observes the property you care about. It observes a proxy, and the gap
between the proxy and the property is where everything hides. "Tests pass" is a proxy for
"the code is correct". "The tree is clean" is a proxy for "I have committed my work".

That second one cost me a day. This workspace sets `core.fsmonitor=true` for speed. When
the filesystem monitor daemon dies, and it does, `git status --porcelain` and `git diff`
both report a completely clean tree while modified files sit on disk. Every guard I had
written that asserted a clean tree before proceeding passed happily. They were reading a
dead sensor and reporting the world as fine. Forcing `git -c core.fsmonitor=false` is the
workaround. Noticing at all was the hard part, and I only noticed because a downstream
result was impossible.

## What actually worked

Three things.

**A reviewer that cannot see your reasoning.** The value of the second model is not that it
is smarter than the first. It is that it has not just spent an hour convincing itself the
design was right. I run Claude on one side and a different vendor's model on the other,
prompted to refute rather than review, told to default to "this is broken" under
uncertainty. A reviewer who shares your context shares your blind spot.

**Prove the fix, do not assert it.** The pattern I hit most across review rounds was not a
missed bug. It was that the *previous* round's fix had never executed. Patched at one call
site out of three. Guarded behind a condition that never fired. So now every fix ships with
a mutation proving it: break the thing the fix protects, watch the gate fail, restore,
watch it pass. If you cannot make a gate fail on demand, you have not shown that it works.
You have shown that it is quiet.

**Know when to stop.** One review thread ran to twelve rounds before I closed it unmerged.
The scores stopped climbing around round eight and I kept going, because every round
surfaced *something* and surfacing something feels like progress. It is not. When the
findings stop being about the product and start being about your own measurement apparatus,
the loop has become the work. I once burned three review rounds hardening a gate I had
built to measure an existing test suite. My gate caught 30 of 60 planted defects. The
pytest suite it was auditing caught 57, and not one of my gate's findings was unique. The
correct move was to delete it, not improve it.

## Why this gets harder as the models get better

The instinct is that stronger models make this obsolete. I think the opposite is true.

A weak agent fails visibly. The code does not compile, the test errors, you notice in
seconds. A strong agent fails *plausibly*. It produces something that reads correctly,
passes the checks you happened to write, and is wrong in a way you need domain knowledge to
see. Better models do not remove the review burden. They move it from the compiler to you.

Which means the binding constraint on how much autonomy you can safely hand over is not the
agent's capability at all. It is the reliability of whatever evaluates it. Agent freedom is
capped by evaluator reliability, and no amount of model improvement raises that ceiling.
It is your ceiling, not the model's.

So if you are letting agents write code unattended, the question is not whether the model is
good enough. It is: what does your green check actually certify, when did you last make it
fail on purpose, and would you notice if it had quietly stopped watching?

I halted my governor loop in July. Not because it failed. Because it worked well enough
that I stopped reading the diffs carefully, and that is a worse failure mode than any bug
it ever shipped.