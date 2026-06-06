---
# Publish inputs (you set these; CLI flags override). Drive `broomva handoff push`.
arc: <slug>                 # stable queue slug — re-pushing the same arc appends a version
specs: []                   # related spec handles → /d/<handle> (e.g. [maestro, relay-1b])
ticket: BRO-NNNN
priority: 0                  # higher floats up the queue
# --- managed by `broomva handoff push` — written back on push, do not hand-edit ---
# queue_id: <id>
# queue_slug: <slug>
# queue_version: 1
# queue_status: queued       # queued → in_progress → done | archived
# queue_url: https://broomva.tech/maestro/queue
# pushed_at: <iso8601>
---

# <Arc name> — <Stage / Phase / PR-arc identifier>

**TL;DR.** <One sentence: where we are + the single next action. End with the first action explicitly.>

---

## State of the world (P15 snapshot YYYY-MM-DD)

> Concrete current state across every repo + daemon the arc touches.
> NOT last-seen state. Run `git status` / `gh pr list` / `ps aux | grep <daemon>` while writing this section.

- **`<repo-1>`** — `<branch>`, ahead N / behind M vs `origin/main`. Recent commits include `<sha>` (`<topic>`), `<sha>` (`<topic>`). <Unpushed? Pushed but unmerged? Note the state.>
- **`<repo-2>`** — `<branch>` at `<sha>`, carrying the following merged PRs:
  ```
  <sha>  #<n>  <title>
  <sha>  #<n>  <title>
  ```
- **`<long-running daemon, if any>`** — STILL RUNNING (PID `<pid>`) on `<socket / port>`. <Config path>. **If it died: restart with**
  ```bash
  <exact restart command, with any required env vars>
  ```

---

## What <arc> delivered (so the next agent doesn't redo it)

| PR | Crate(s) / files | What it gave |
|----|------------------|--------------|
| #<n> @ `<sha>` | `<path>` + `<path>` | <One-line of what landed> |
| #<n> @ `<sha>` | `<path>` | <One-line of what landed> |

---

## E2E proof (re-runnable when prereqs hold)

```bash
<exact reproducible command, with cd if needed>
# Expected: <observable output, e.g. "Status(Completed)" or "200 OK">
```

If the prereqs don't hold (daemon down, env var missing, etc.), state which
prereq + how to restore it.

---

## First action

> ONE concrete next step. Exact command or file path. No "consider A or B" — pick A.

`<exact command>` OR Open `<exact file path>` and `<exact change to make>`.

If blocked, fall back to: `<one alternative, at most>`.

---

## Pickup state (open threads, ≤5)

- [ ] <open thread 1: include file paths / line numbers if known>
- [ ] <open thread 2>
- [ ] <open thread 3>

> If more than 5 open threads: aspirational scope. Move excess to a Linear backlog or `docs/plans/<arc>.html` and link from here.

---

## Related context

- **Lessons doc** (if any): `docs/<arc>-lessons.md`
- **Linear ticket**: BRO-NNNN
- **Prior handoff** (if mid-arc continuation): `docs/handoffs/<earlier-date>-<earlier-slug>.md`
- **Spec / plan** (if any): `docs/specs/<...>.html` or `docs/plans/<...>.html`
- **Conversation bridge index** (the session this handoff closes): `docs/conversations/session-YYYY-MM-DD-<hash>.md`

---

## Self-test (delete before publishing — or keep for first few handoffs as a training rail)

- [ ] TL;DR is ONE sentence and names the first action
- [ ] P15 snapshot covers every repo + daemon (run the commands; don't recall)
- [ ] PR table cites merge SHAs, not just PR numbers
- [ ] First action is concrete (exact command OR exact file + change)
- [ ] Pickup state has ≤5 open threads
