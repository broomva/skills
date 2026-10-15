# fleet · close-out: archive only what is fully finished

> Workflow of the [`fleet`](../SKILL.md) skill. It is a procedure the standing
> coordinator runs, not code in this skill. **The canonical text is bstack's
> base protocol, §6.** Read it from git:
>
> ```bash
> git -C ~/broomva/bstack fetch -q origin main
> git -C ~/broomva/bstack show origin/main:references/orchestrator-tick.md   # §6 Close-out and archiving
> ```
>
> If this page and the base disagree, the base wins.

## Trigger

- A driven (`arc`) session's final message reads finished (base §5's
  "Finished" row).
- An `owner` session from the [census](census.md) has been idle more than
  12 h. At most 3 owner close-outs per tick, and only while usage allows (§7).
- A session replaced by a [rollover](rollover.md) successor, once the
  successor is verified.

## Steps

1. **Fully finished, all five** (base §6): the PRs are merged, or closed by the
   owner; the tree is clean, with no unpushed commit; every follow-up is a
   ticket; every owner decision it raised is in a `.control/asks` ledger; a
   Maestro card tracking it is in `review` or `done`. Any one missing → it is
   not closed out: drive it, or put the gap in `open`.
2. **Clear the cascade.** Archiving X archives every live agent labelled
   `paseo.parent-agent-id=X`. For each child that must survive:
   `update_agent <child> labels {"paseo.parent-agent-id": ""}`, then re-read the
   child's registry file.
3. **Archive with the right call:** `archive_agent` when the workspace holds
   other agents or the orchestrator; `archive_workspace` only for a worktree
   whose sole agent is the finished one; never `archive_workspace` on the
   shared main checkout. Never archive the orchestrator itself: that is the
   [rollover](rollover.md).

## Check

Before archiving `<id>` (its 8-hex prefix), with `<wt>` its worktree and
`<branch>` its branch:

```bash
git -C <wt> status --porcelain | wc -l                    # 0
git -C <wt> log --oneline @{u}..HEAD 2>/dev/null | wc -l  # 0: nothing unpushed
gh pr list --head <branch> --state open --json number -q length   # 0
python3 - <id> <<'PY'
import glob, json, os, sys
kids = [a for f in glob.glob(os.path.expanduser("~/.paseo/agents/*/*.json"))
        for a in [json.load(open(f))] if not a.get("archivedAt")
        and str((a.get("labels") or {}).get("paseo.parent-agent-id", "")).startswith(sys.argv[1])]
print([k["id"][:8] for k in kids])   # []: no live child would be archived with it
PY
```

All four must hold. A child listed in the last line is either cleared (step 2)
or archived with it on purpose.
