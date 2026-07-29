# Probing a mechanism — does it actually fire?

Adjudication tier 1 says: the prose is decorative because a mechanism enforces
the rule regardless, so deleting the prose is free. That claim rests on two
separate facts about the mechanism, and the audit script establishes neither.

| Question | Name | Who answers it |
|---|---|---|
| Does it produce a signal at all? | **efficacy** | this procedure |
| Is that signal outside the governed actor's reach? | **independence** | `keel` |
| Does the file exist? | *neither* | `context_audit.py` |

Existence is what the script can see, and existence is the weakest of the three.
A mechanism can be present, registered, scheduled, and genuinely independent —
and emit nothing. So a section marked `anchored_candidate` with `Fires? ?` is an
open question, not a soft yes. Probe it before you cut the prose it makes free.

## The procedure

Three legs, all three required.

**(a) Trip it.** Feed the mechanism an event that *should* fire it, through the
real path the real caller uses. Confirm the signal appears where the consumer
reads it.

Span the input space it branches on. A gate that checks command length, file
extension, tool name, or payload size has a branch per dimension, and one benign
trigger only proves the branch you happened to hit.

**(b) Leave it alone.** Feed an event that should *not* fire it. Confirm silence.
A mechanism that fires on everything is noise the consumer learns to ignore, and
it is indistinguishable from one that is stuck on.

**(c) Neuter it and watch your check go red.** Break the mechanism deliberately —
rename its script, invert its predicate, unregister it — and re-run (a). Your
check must now fail.

Leg (c) is the one people skip and the only one that separates *the gate works*
from *my test passes*. Without it, every green in (a) is consistent with the gate
being dead and something else — a sibling mechanism, a default, your own test
harness — producing the outcome you attributed to it. Restore the mechanism
afterwards and re-run (a) to confirm you put it back.

Observe the signal **at the consumer, not at the producer**. A hook that prints a
block payload has not blocked anything; a job that logs a failure has not failed
the build. What counts is what the thing downstream actually did.

## Three that passed existence and failed the probe

All three ran in `~/broomva`. All three were registered, fired on schedule, and
were independent of the agent they governed. All three produced no signal, and
all three would read as `anchored_candidate: true` today.

### 1. The gate with a length-shaped hole — leg (a) must span the branches

`scripts/control-gate-hook.sh` ran on every Bash call and blocked destructive
commands. It also opened with a length guard:

```sh
if [ "$CMD_LEN" -lt 500 ]; then   # only check short commands
```

Every check sat inside that branch. A `git reset --hard` under 500 characters was
blocked; the same command padded past 500 with a trailing comment ran. One probe
with a short destructive command passes and certifies a gate with a hole in it
wide enough for anything an agent composes.

The probe that catches it runs (a) twice — once inside the branch, once outside —
because the mechanism's own source names the dimension it branches on. Read the
mechanism before designing the trigger.

### 2. The hook that never blocked anything — observe at the consumer

`scripts/check-file-write-safety.py` was a `PreToolUse` write gate, and was a
total no-op from the day it was written. Two independent defects, either alone
sufficient:

- its policy patterns were repo-relative (`.claude/settings.json`) and matched
  against `tool_input.file_path`, which the harness always sends **absolute**, so
  no pattern ever matched;
- its block path returned `EXIT_BLOCK = 8`, and in Claude Code only exit 2 blocks
  a tool call. Every other code is advisory.

Note what a producer-side probe reports here. Pipe a crafted event with a
repo-relative path into the script and it prints a block payload and exits 8 —
which reads as *fired*. Both defects survive that probe. Only the consumer-side
question — *was the write actually stopped?* — sees the truth.

The governance file's row for this hook read **"Read-before-Edit enforcement"**:
prose describing a behavior nothing implemented. Under an existence predicate,
unhobble would have recommended deleting that row as free.

### 3. The dead refresh — leg (c) and the redundant sibling

`scripts/knowledge-catalog-refresh-hook.sh` fired on every session end, spent
136 ms, and did nothing for eight days. A monorepo reorg had moved
`bookkeeping.py`, and the hook's early guard —

```sh
if [ ! -f "$BOOKKEEPING_PY" ]; then   # skip if bookkeeping isn't installed
```

— turned a missing dependency into a silent exit 0. Exit 0 is the signature to
distrust: *ran and returned success* is indistinguishable from *did the job*
unless you check the landed side effect.

It went unnoticed for eight days because a second hook refreshed the same index.
The observable outcome stayed correct the entire time. Legs (a) and (b) both pass
here — the catalog does update after a session. Only (c) separates them: neuter
this hook, and the catalog still updates, which says the signal you are about to
delete prose against is coming from somewhere else entirely.

## Recording the result

A probe is a runtime act; a static analyser can only read its receipt. Write one
per mechanism, keyed by the exact backticked reference as it appears in the prose:

```json
{
  "probes": {
    "control-gate-hook.sh": {
      "covers": ["Control gate blocks destructive bash"],
      "fires_on_trigger": true,
      "silent_on_non_trigger": true,
      "neutered_check_went_red": true,
      "date": "2026-07-28",
      "evidence": "padded and unpadded `git reset --hard`; renamed the hook and re-ran"
    }
  }
}
```

### `covers` is not optional

**A receipt with no `covers` promotes nothing.** It names the rules the probe
actually covers — section headings, or `path#heading` when two audited files
share one.

The probe is per *mechanism*; the deletion verdict is per *rule*. One gate is
cited by a destructive-bash rule, a secrets rule, and a PII rule; a probe of the
`rm -rf` branch is evidence about the first and silence about the other two.
Without scoping, that one receipt promotes all three to "delete the prose,
keep the mechanism. Free" — and the two you never tested lose the only thing
carrying them.

That is this skill's own citation trap, relocated. SKILL.md says a rule that
*cites* a mechanism is not thereby anchored; true for `.md` refs, and it would
become false for `.sh` refs the moment citing were enough to reach `yes`. So an
unscoped receipt fails **closed** — `unscoped`, never `fires`. The report says
how many, so the omission is never silent.

The one exception: a **negative** finding (`fires_on_trigger: false`) applies
without `covers`. It never promotes anything, and discarding an honest "this
does not fire" over paperwork would throw away the most valuable receipt in the
file.

A `covers` entry naming no section — a heading renamed since the probe — stops
promoting, which is safe, and is reported so it is not silent either.

```bash
python3 scripts/context_audit.py CLAUDE.md --repo-root . --probe-receipts probes.json
```

**The key is the literal backticked string in the surface**, not the path you
know the mechanism by. `control-gate-hook.sh` and `scripts/control-gate-hook.sh`
are different keys, and only the one the prose actually contains matches. A key
that matches nothing leaves its section UNRESOLVED — the safe direction — and
the report says so, because a receipt file that applied to nothing would
otherwise render exactly like no receipt file:

```
**Probe receipts** — 1 of 3 matched a reference in the audited surface(s).
**2 key(s) matched nothing and did nothing**:
- `scripts/control-gate-hook.sh` — did you mean `control-gate-hook.sh`?
- `scripts/knowledge-catalog-refresh-hook.sh` — no unambiguous near match
```

Read that line every run, and read it as *matched*, not *applied* — a key can
match a reference and still change nothing. Four ways a receipt accomplishes
nothing while looking fine, each reported rather than left to inference: the key
names no reference, the reference is not a live mechanism, the receipt carries
no `covers`, or its `covers` names no section. `--fail-on-unmatched-receipts`
turns the first and last into an exit code when you want CI to hold the line.

The near-match hint stays silent when two references share a basename. A
confident wrong suggestion is worse than none: take it, and the section you did
*not* probe is the one that gets freed.

The `Fires?` column resolves to `yes` only when all three legs are `true`. A
receipt missing `neutered_check_went_red` reads `incomplete`, not `yes` — a probe
without a negative control has not demonstrated anything. `fires_on_trigger:
false` reads `DEAD`, which is a finding in its own right: prose the mechanism was
supposed to make redundant is the only thing carrying that behavior.

Nothing infers these values. Without a receipt the answer stays UNRESOLVED, which
is the honest state.

## A receipt is an attestation, not a verification

Read that last paragraph again, because it stops one step short. `context_audit.py`
reads the booleans; it cannot check them. Nothing in the script observes the
probe, re-runs it, or compares the claim against anything. Its only options are
to believe the file or ignore it.

Which matters entirely because of who is usually holding the pen. The rule
governing this column is that a regex inferring firing would be *guessing in a
confident voice* — and a hand-written receipt is the same guess with better
manners. An agent that wants a section deleted can type three `true`s, collect
`fires`, and take the free-to-delete tier without ever tripping the mechanism.
The producer of the signal is then the actor being governed, the column is
satisfiable by construction, and the audit reads *more* rigorous than the
existence predicate it replaced while carrying the same risk. That shape has a
name and a tool: it is exactly the independence question `keel` asks, arriving
one level up, about the receipt instead of the mechanism.

So the rule is: **a receipt should be emitted by a runner, from a real run.**
Not typed.

The intended producer is **BRO-2036** — a mutation-proof runner landing in
`skills/governance/cross-review/`, which performs the neuter leg and emits
`neutered_check_went_red` from the result it actually observed. Legs it did not
exercise are left **absent** rather than defaulted, so a partial run reads
`incomplete` and promotes nothing. (Forward reference only; nothing in
`context_audit.py` depends on it, and receipts stay readable without it.)

Until it lands, a hand-written receipt is a placeholder — reasonable for
recording a probe you genuinely ran and can point at, worthless as evidence to
anyone who was not standing behind you. Two habits keep it honest:

- **Fill `evidence`.** Exit codes, the exact commands, what the consumer did,
  when — as a string, or as the object a runner emits. A receipt with no
  `evidence` renders `yes*` instead of `yes`, and the report says why. A bare
  `"evidence": true` counts as no evidence, because asserting that evidence
  exists is not showing it. The script cannot verify an evidence string either —
  the star marks the difference between a record someone can be held to and a
  bare claim, which is the most an unverified channel can offer.

  The star is **per receipt, not per leg**. Two legs typed by hand alongside one
  a runner observed produce a single unstarred `yes`, and the typed pair
  inherits the runner's credibility. Per-leg attribution is the refinement, and
  it belongs with the runner that knows which legs it actually ran.
- **Separate the hands.** Do not write the receipt for a mechanism whose prose
  you are cutting in the same pass. Different agent, different session, or wait
  for the runner.

## What a passing probe still does not buy you

- **A verified claim.** `yes` means *attested*, not proven — the section above.
  The audit trusts the receipt; the receipt's worth is whatever its producer's
  is.
- **Independence.** A mechanism can fire reliably and still be one the governed
  actor can edit, disable, or feed. That is `keel`'s question; run it when the
  actor has write access anywhere near the producer.
- **Durability.** The probe is a point-in-time observation. Example 3 fired
  correctly for months before a directory move killed it, and nothing noticed.
  A receipt is evidence, not a warranty; re-probe when the mechanism, its
  registration, or the paths it depends on change.
