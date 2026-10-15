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
- A session replaced by a [rollover](rollover.md) successor: a driven
  session once its successor is launched (base §11); the coordinator only
  through its successor, once that one verifies (the overlay).

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

Before archiving agent `<id>` (its 8-hex prefix), with `<wt>` its worktree,
`<owner/repo>` its repo and `<branch>` its branch. One script, one verdict:
`FINISHED` and exit 0, or `NOT FINISHED: <why>` and exit 1. Any read that
fails is NOT FINISHED, never zero (`tests/test_layout.py` runs this block).

```bash
python3 - <wt> <owner/repo> <branch> <id> <<'PY'
import glob, json, os, subprocess, sys
wt, repo, branch, agent = sys.argv[1:5]
def read(*argv):
    r = subprocess.run(argv, capture_output=True, text=True)
    if r.returncode:
        sys.exit("NOT FINISHED: %s failed: %s" % (" ".join(argv[:3]), r.stderr.strip()[:200]))
    return r.stdout
if read("git", "-C", wt, "status", "--porcelain").strip():
    sys.exit("NOT FINISHED: uncommitted changes in %s" % wt)
head = read("git", "-C", wt, "rev-parse", "HEAD").strip()
prs = json.loads(read("gh", "pr", "list", "-R", repo, "--head", branch, "--state", "all",
                      "--json", "number,state,headRefOid") or "[]")
at = [p for p in prs if p.get("headRefOid") == head]   # the PR carries every local commit
if not at:
    sys.exit("NOT FINISHED: no PR on %s at HEAD %s (never pushed, never opened, or commits after it)" % (branch, head[:12]))
if not any(p.get("state") == "MERGED" for p in at):
    sys.exit("NOT FINISHED: PR #%s is %s (CLOSED counts only if the owner closed it)" % (at[0].get("number"), at[0].get("state")))
kids = []
for f in glob.glob(os.path.expanduser("~/.paseo/agents/*/*.json")):
    a = json.load(open(f))
    if not a.get("archivedAt") and str((a.get("labels") or {}).get("paseo.parent-agent-id", "")).startswith(agent):
        kids.append(a["id"][:8])
if kids:
    sys.exit("NOT FINISHED: live children %s would be archived with it (clear their label first)" % kids)
print("FINISHED: PR merged at %s, tree clean, no live child" % head[:12])
PY
```

It checks base §6 items 1 and 2 and the cascade. Items 3 to 5 (follow-ups
ticketed, decisions in a ledger, the Maestro card) are read from the final
message and the card. A PR the owner closed unmerged also counts as finished
(item 1); the script can't tell who closed it, so it says NOT FINISHED and
names the state.
