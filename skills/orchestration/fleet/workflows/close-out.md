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
fails or times out is NOT FINISHED, never zero (`tests/test_layout.py` runs
this block). A session with no work of its own (HEAD already in the
remote's default branch) is finished without a PR.

```bash
python3 - <wt> <owner/repo> <branch> <id> <<'PY'
import glob, json, os, subprocess, sys
wt, repo, branch, agent = sys.argv[1:5]
def run(*argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        sys.exit("NOT FINISHED: %s timed out after 60 s" % " ".join(argv[:3]))
def read(*argv):
    r = run(*argv)
    if r.returncode:
        sys.exit("NOT FINISHED: %s failed: %s" % (" ".join(argv[:3]), r.stderr.strip()[:200]))
    return r.stdout
if read("git", "-C", wt, "status", "--porcelain").strip():
    sys.exit("NOT FINISHED: uncommitted changes in %s" % wt)
head = read("git", "-C", wt, "rev-parse", "HEAD").strip()
r = run("git", "-C", wt, "rev-parse", "--abbrev-ref", "origin/HEAD")
base = r.stdout.strip() if r.returncode == 0 else "origin/main"
inside = lambda rev: run("git", "-C", wt, "merge-base", "--is-ancestor", rev, base).returncode == 0
if inside(head) and (branch == "HEAD" or inside(branch)):   # the branch too: a worktree moved off it
    done = "no work of its own: HEAD %s is in %s" % (head[:12], base)
else:
    prs = json.loads(read("gh", "pr", "list", "-R", repo, "--head", branch, "--state", "all",
                          "--json", "number,state,headRefOid") or "[]")
    at = [p for p in prs if p.get("headRefOid") == head]   # the PR carries every local commit
    if not at:
        sys.exit("NOT FINISHED: HEAD %s is in no PR on %s and not in %s (unpushed, never opened, "
                 "or the PR moved on GitHub)" % (head[:12], branch, base))
    if not any(p.get("state") == "MERGED" for p in at):
        sys.exit("NOT FINISHED: PR #%s is %s (CLOSED counts only if the owner closed it)"
                 % (at[0].get("number"), at[0].get("state")))
    done = "PR merged at %s" % head[:12]
kids = []
for f in glob.glob(os.path.expanduser("~/.paseo/agents/*/*.json")):
    try:
        a = json.load(open(f))
    except (OSError, ValueError) as exc:
        sys.exit("NOT FINISHED: registry file %s unreadable (%s)" % (f, exc))
    if not a.get("archivedAt") and str((a.get("labels") or {}).get("paseo.parent-agent-id", "")).startswith(agent):
        kids.append(str(a.get("id"))[:8])
if kids:
    sys.exit("NOT FINISHED: live children %s would be archived with it (clear their label first)" % kids)
print("FINISHED: %s; tree clean; no live child" % done)
PY
```

It checks base §6 items 1 and 2 and the cascade. Items 3 to 5 (follow-ups
ticketed, decisions in a ledger, the Maestro card) are read from the final
message and the card. A PR the owner closed unmerged also counts as finished
(item 1); the script can't tell who closed it, so it says NOT FINISHED and
names the state: the owner's close is the override, recorded on the ticket.
A detached HEAD has no branch: pass `HEAD`, and only the no-work path can
pass it.
