---
name: correct
tier: D
description: "Turn the mistakes agents keep repeating in a repo into checks that make them impossible. Find each mistake class (two occurrences make a class), fix it at the highest level that works (architecture, then types, then a lint or CI check whose error names the fix, then a test, then a hook, prose last), prove each check refuses a real past mistake and allows a nearby legitimate input, and keep a rule-to-enforcer registry. Ships the registry's runner: `scripts/correct.py init` gives a repository a registry with one proven rule, and `scripts/correct.py check` replays every row against its real enforcer. Use when the operator corrects an agent, says 'stop doing X', 'again?', '/correct', 'make this impossible', 'why does this keep happening', when a rule exists in docs that nothing enforces, or to set up or replay a rule registry ('rules check', 'is this rule enforced', 'add a rule registry')."
---

# correct

Adapted from Lauren Tan's `/correct` skill in pstack (`cursor/plugins`, MIT,
commit bf0c7cd), extended with what applying it to a governance workspace
taught: every proof needs a control, a crash is not a refusal, and a rule
registry must be replayed, not just written.

The operator keeps correcting agents in this repo for the same mistakes. Change
the repo so the next agent cannot make them.

## Commands

The method below is judgment. The registry it ends in is not: this skill ships
the runner, so "the check holds" is a command's exit status and not a claim.

```
python3 -I <skill>/scripts/correct.py init   [--root DIR] [--dry-run] [--force]
python3 -I <skill>/scripts/correct.py check  [--root DIR] [--ci] [--json] [--only ID ...] [--base REF]
python3 -I <skill>/scripts/correct.py canary [--root DIR] run | ...
```

`<skill>` is this skill's own directory, the folder this file is in (for example
`~/.claude/skills/correct`). The command stays in the skill; `init` does not copy
it into the repository. Run it with the repository as the current directory, or
name the repository with `--root`. It needs `python3`, `git` and PyYAML.

- **`init`** gives a repository its registry. It writes the registry
  (`assets/templates/rules.yaml`: one rule, branch first, with ten proofs, three
  controls and two recorded known misses), that rule's hook and the fixtures its
  cases use into the repository's `scripts/`, a governance policy file if there
  is none, and the hook entry in `.claude/settings.json`. Then it replays the
  registry and exits with the replay's status. Read this before running it: from
  then on an edit on `main` or `master` in that repository is refused, and the
  refusal names the fix (a branch); `BSTACK_ALLOW_MAIN_EDIT=<reason>` in the
  session's environment is the hook's documented exception. `--dry-run` lists
  what would be written and is refused wherever the real run is refused before
  it writes; it tries no write, so it cannot say that one will fail (the
  registry, on a filesystem that cannot link), nor whether the replay will pass
  afterwards. It
  never replaces an existing registry: a repository that has one gets nothing
  written and is replayed, with or without `--dry-run`, so an existing registry
  that does not hold still exits 1. It writes nothing when PyYAML is missing; when a file it would write
  exists with other content (`--force` replaces those) or is read-only; when a
  path it would write goes through a symlink or an unwritable directory; when a
  file sits where a directory must go; or when the settings already mention the
  hook in any form other than the entry `init` writes. It keeps only its own
  entry, compared value for value (so the same hook with another timeout, or its
  tools in another order, is refused too), and it does not judge whether another
  entry runs the hook; the replay does. When it adds its entry it rewrites
  `.claude/settings.json` with two-space indentation, keeping every key. The
  registry is the
  last file written, so a run that stops early leaves a repository the next run
  still sets up. It is created, never replaced: `init` links a finished file to
  the registry's name, which the filesystem refuses when the name is taken. Of
  two `init` runs at once, one writes the registry; the other finds it there,
  or finds its name taken when it comes to write, and either way writes none
  and replays the one that is there. A temporary file `init` cannot remove,
  whether it wrote the registry or found the name taken, is named on stderr,
  and the run goes on. On a filesystem that cannot link, `init` exits 2 at that
  write and says the link failed: the files before it are in place, the hook
  among them, and there is no registry; back out as follows. To back out, remove only what `init` added:
  the registry; each file its output listed as `write` that was not there
  before the run; and the `PreToolUse` entry that runs
  `scripts/branch-first-hook.py`, taken out of `.claude/settings.json`. Restore
  from version control any file `--force` replaced. A file listed as `keep` was
  there before the run and is not `init`'s to delete.
- **`check`** replays every row (`scripts/rules_check.py`): each proof and
  control goes through the hook entry the harness would run, and the row fails
  on a proof that is allowed, a control that is refused, a crash, or a missing
  registration. `--registry FILE` names another registry, read relative to the
  current directory. It also fails when a hard gate or a blocking hook has no row,
  and with `--base REF` when a row was lowered without a recorded reason. Exit 0
  means every row held; 1 means one did not; 2 means the command could not run
  (no repository, no registry yet, git or PyYAML missing, or a registry whose
  `version:` this copy of the skill does not replay: it replays version 1, and
  refuses a later one instead of passing rows it would only half read).
- **`canary`** runs real Claude Code sessions against the registered hooks
  (`scripts/rules_canary.py`) and writes a receipt the replay then requires. A
  row may say `canary: {none: reason, ticket}` instead; the replay then reports
  it as replayed and not certified on the real harness.

On a repository that already has hard gates or blocking hooks, `init` exits 1 and
lists each one that no row accounts for. That list is the work: a row for each, a
`gap` row with a ticket as the honest start.

**What the commands do not cover yet.**

- Hooks are read from Claude Code's settings only. A rule enforced through
  another harness's hook file is not replayed.
- The runner and the canary come from `broomva/workspace` with their code
  unchanged; one comment in the runner differs (`scripts/VENDORED.json` records
  the commit, each file's hash and that change). Two of the
  three state fixtures and the case environment keys are that workspace's own
  (BRO-4129).
- The mutation harness, the gardener and the pipe-status lint are planned
  (BRO-4127), as is a gate that runs from the skill's install path in any
  harness (BRO-4047).
- An installed copy of this skill can be older than the repository's rows.

Assume every contributor is an agent that sees only the files it opened, copies
the nearest example, and takes the shortest path that compiles. The codebase is
its largest input, so a workaround it can see is a workaround it will copy. Design
the repo so a change that looks right from one file is right for the whole repo.

## 1. Find the mistake classes

Read recent commits, reverts and fix-forwards, review comments, agent instruction
files (AGENTS.md, CLAUDE.md, memory), and comments that explain workarounds. Group
the mistakes into classes. **A class counts once it has happened twice.** An
irreversible outward action (publishing, deleting someone else's work) counts at
once: there is no second chance to learn from.

Search the registry first (step 5). If the rule is already written and nothing
enforces it, that is a **repeat**: fix it now, at the highest level, in the same
change.

## 2. Fix each class at the highest level that works

1. **Architecture.** Give each piece of state one owner and each task one
   supported way. Hide internals so the wrong import fails. Replace hand-synced
   lists with one source of truth. Make generated files derived (regenerated and
   verified, never hand-edited or hand-merged). Delete old ways an agent would copy.
2. **Types.** Make the bad state impossible to write.
3. **A lint or CI check whose error names the fix.** Not "blocked": the file,
   type, function or command to use instead. An agent that only hears "no" routes
   around the check; one told what to do goes through it. If the pattern is
   already common, ratchet: fail when a change adds one, and fail when the
   count drops until the baseline is lowered, so it only shrinks.
4. **A test** of the behavior. Fix or delete any test that still passes when the
   behavior breaks, or fails when only internals change.
5. **A hook** that refuses the action when it is taken (an agent command, a
   commit, a file write), for mistakes made outside the code.
6. **Prose last, for judgment calls only.** Nothing fails when an agent skips it.
   Write down why no check can decide it.

## 3. Prove each check

A check never seen failing proves nothing.

- **Proof:** replay the real past mistake (the actual command, diff, file or
  transcript text, with where it came from) against the enforcer only, or against
  a disposable copy of every target, and show the check refuses it.
- **Control:** replay a nearby legitimate input against the enforcer only, or
  against a disposable copy of every target, and show it is allowed. Without
  one, a check that refuses everything passes every proof.
- **Mutation:** break the check in a scratch copy and show its proof fails.
- **A refusal states its reason.** A crashing check also exits non-zero; require
  the refusal's output to name the mistake, and treat other exit codes as errors.
- **An unmeasured condition is "no data", never "clean".**

Run the same command locally and in CI. Exceptions go on the offending line with
a reason, an expiry date and a human's approval.

## 4. Fix the most frequent classes now

One commit per class, each carrying its proof, control and mutation result.

Before closing a class, **sweep the repository for sibling occurrences** of the
same mistake (the codebase is the next agent's largest input, so every remaining
copy teaches the mistake back). Fix every sibling you find, or ratchet the
remaining count explicitly.

## 5. Keep the registry

Keep one machine-readable table that pairs each rule with what enforces it: the
level, the enforcer's path, how it is reached (hook event, CI job), the dated
occurrences, the proofs and the controls. A runner replays every row against the
real enforcer (invoking only the enforcer or operating on disposable copies in a
scratch directory, never mutating live targets) and fails on any proof allowed
or control refused. A rule with no
enforcer is either a recorded judgment (with the reason) or a gap (with the
ticket that closes it). Drop a rule once its mistake cannot happen, and retire its
prose copy when it reaches a mechanism level.

`scripts/correct.py init` writes that table and `scripts/correct.py check` is that
runner. The field reference is the header of `scripts/rules_check.py`.

## Reply

Each class with its evidence, the level you picked and why a higher level did not
work, the proof and control replayed, the mutation that turned it red, the
sibling-sweep count (fixed or ratcheted), and the rows added to the registry.

## Anti-rationalization

| Excuse | Reality |
|---|---|
| "I'll add it to AGENTS.md." | That is the lowest level. Nothing fails when the next agent skips it. Try every level above first. |
| "It only happened once." | Then record it and wait for the second. An irreversible action is the exception. |
| "The check passes, so it works." | Show it failing on the real mistake, and passing on a control. |
| "The error says 'blocked'." | Name the fix. A refusal without one teaches the agent to route around it. |
| "The pattern is everywhere, the lint would be red for weeks." | Ratchet it: fail when a change adds one, and fail when the count drops until the baseline is lowered, so it only shrinks. |
| "I fixed the one instance that triggered the correction." | Agents copy the nearest file. Sweep the repo for sibling occurrences before closing the class; leave none unfixed or unratcheted. |
