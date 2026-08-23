---
name: prove-the-negative
description: Verify a claim whose evidence is an ABSENCE — blocked, denied, unreachable, isolated, not-logged, no-longer-present. Enforces that every denial is paired with a positive control that must SUCCEED, because "everything is denied" and "nothing ran at all" are the same observation. Ships a verdict gate that returns INVALID (exit 2) rather than PASS when the controls did not fire. USE WHEN validating a security boundary or sandbox, writing an eval whose passes are denials, confirming a capability was removed, checking that data is unreachable, or concluding from a probe that returned nothing. NOT FOR claims whose evidence is a presence (an output, a value, a rendered page) — those fail loudly on their own and need no control.
tier: D
---

# prove-the-negative

A negative result is evidence **only if a positive control proves the apparatus
was live**. Without one, a suite of denials reports its healthiest possible
result at the exact moment its subject is switched off.

This is not a hypothetical failure mode. It is the one that keeps happening.

## The inference this refuses

> every probe returned "denied" → the boundary holds

Invalid, always. `denied` and `never ran` are the **same observation** through
the instrument you are using. A run that cannot tell them apart has not
measured the boundary; it has measured nothing, and reported success.

## The three rules

**1. Every denial needs a control that must SUCCEED.**
Not a second denial — a case that fails loudly if the apparatus is dead.
`echo HELLO` passing is what licenses `curl` being blocked to mean anything.

**2. The subject's own account is never the verdict.**
A model that declines a probe on its own judgment has told you about its
disposition, not about its cage. Compute the verdict from literal output, from
outside, in code. Where possible check the filesystem or process table rather
than asking — *"did the file appear?"* beats *"were you able to write it?"*

**3. A crashed probe is never a pass — including for a denial.**
An assertion that errored proves nothing about what its subject cannot reach.
Fail it. The tempting shortcut — *"it didn't succeed, so the denial held"* — is
rule 1 again, one case down.

## Verdicts are three-valued

`PASS` / `FAIL` / **`INVALID`**, and the third is the point.

| | means | exit |
|---|---|---|
| PASS | controls fired, assertions held | 0 |
| FAIL | controls fired, an assertion broke — **a real finding** | 1 |
| INVALID | controls did not fire — **you learned nothing** | 2 |

Collapsing INVALID into FAIL re-creates the bug at the reporting layer: "we
measured nothing" starts reading as "we found a problem", and gets triaged as
noise. Keep them distinct or the discipline dissolves.

## Use

```bash
python3 scripts/verdict.py cases.json     # or:  … verdict.py -   (stdin)
```

```json
[
  {"name": "bash executes",        "kind": "control",   "outcome": "pass"},
  {"name": "cwd is the tenant dir","kind": "control",   "outcome": "pass"},
  {"name": "write outside denied", "kind": "assertion", "outcome": "pass"},
  {"name": "egress denied",        "kind": "assertion", "outcome": "pass"}
]
```

Drop the two controls and the same input returns `INVALID`, exit 2. That is the
whole skill.

`parse_cases` **rejects** an unknown `kind` or `outcome` rather than coercing
one. Defaulting an unrecognised outcome to `pass` greens a run silently;
defaulting a mistyped `kind` to `assertion` drops the only control and makes the
suite unfalsifiable without saying so.

## Designing the control (the judgment part)

The verdict is mechanical; choosing the control is not.

- It must exercise **the same apparatus** as the denials. A control that runs
  through a different path certifies the wrong thing — a `Read`-tool control
  says nothing about whether the Bash sandbox is alive.
- It must **fail** when the apparatus is dead. If your control passes with the
  subject switched off, it is decoration.
- Prefer a control that is **boring and unconditional**: `echo`, `touch ./x`,
  `pwd`. Anything cleverer acquires its own failure modes and starts producing
  INVALID runs for reasons that are not about the subject.

## Where this came from

Eight instances in one session, each a negative read as evidence:

| observed | concluded | actually |
|---|---|---|
| every sandbox probe BLOCKED | confinement works | bubblewrap could not start; nothing ran |
| `--strict-mcp-config mcp list` listed everything | the flag is broken | the subcommand ignores it; the session honours it |
| `ps \| head -1` showed the flag | operator lost MCP — regression | grabbed a different process |
| agent declined a cross-tenant read (×3) | boundary held | a refusal by judgment is not enforcement |
| `chmodSync` returned success | sticky bit set | bun silently dropped it; `stat` disagreed |
| `max<=0` test asserted `allowed == false` | the guard is covered | `Math.min(...[])` → `Infinity`, still false |
| `$?` after `\| tail` was 0 | the build passed | that was `tail`'s status |

Every row is the same shape: an absence accepted without an apparatus check.

## Related

- `unslop` — the sibling discipline for claims whose evidence is a *presence*.
- `skillify` — the gate this skill was distilled through.
