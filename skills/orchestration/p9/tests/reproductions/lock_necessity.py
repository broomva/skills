"""Race a supersede-writer against a guarded folder, with a REALISTIC state file.

The guarded read parses the whole log under the lock. With a large file that
read is slow, so an unlocked implementation has a wide window in which the
supersede lands between the folder's read and its write.
"""
import sys, os, time, multiprocessing as mp
SCRIPTS, HOME, NROWS = sys.argv[1], sys.argv[2], int(sys.argv[3])
REPO, PR = "broomva/test", 42

def _p9():
    sys.path.insert(0, SCRIPTS)
    os.environ.update(BROOMVA_P9_HOME=HOME, BROOMVA_P9_REPO=REPO, BROOMVA_P9_SESSION="S")
    for m in ("p9",): sys.modules.pop(m, None)
    import p9; return p9

def folder(q, barrier):          # w1's late, guarded fold
    p9 = _p9()
    barrier.wait()
    q.put(p9.append_state_event(p9.PRStateEvent(
        ts=p9._utcnow(), pr=PR, repo=REPO, from_state=p9.PRState.WATCHING.value,
        to_state=p9.PRState.ABANDONED.value, watcher_id="w1",
        session_id="S", extra={}), only_if_owner=True))

def superseder(barrier):       # --force takes the key, unguarded by design
    p9 = _p9()
    barrier.wait()
    time.sleep(0.05)            # land mid-read, not before it
    for frm, to, wid in ((p9.PRState.WATCHING.value, p9.PRState.ABANDONED.value, "watch-supersede"),
                         (p9.PRState.PUSHED.value, p9.PRState.WATCHING.value, "w2")):
        p9.append_state_event(p9.PRStateEvent(
            ts=p9._utcnow(), pr=PR, repo=REPO, from_state=frm, to_state=to,
            watcher_id=wid, session_id="S", extra={"pid": 2222}))

if __name__ == "__main__":
    p9 = _p9()
    # Realistic backlog: the real state.jsonl is 1.14 MB / 3508 rows.
    for i in range(NROWS):
        p9.append_state_event(p9.PRStateEvent(
            ts=p9._utcnow(), pr=100000+i, repo=REPO,
            from_state=p9.PRState.PUSHED.value, to_state=p9.PRState.WATCHING.value,
            watcher_id=f"bulk{i}", session_id="bulk", extra={}))
    p9.append_state_event(p9.PRStateEvent(
        ts=p9._utcnow(), pr=PR, repo=REPO, from_state=p9.PRState.PUSHED.value,
        to_state=p9.PRState.WATCHING.value, watcher_id="w1", session_id="S", extra={"pid":1111}))

    ctx = mp.get_context("spawn"); q = ctx.Queue()
    barrier = ctx.Barrier(2)
    a = ctx.Process(target=folder, args=(q, barrier))
    b = ctx.Process(target=superseder, args=(barrier,))
    a.start(); b.start()        # both fully warm, then release together
    a.join(30); b.join(30)
    wrote = q.get()

    rows, _ = p9.jsonl_read_all(p9.state_jsonl())
    tail = [(r["watcher_id"], r["to_state"]) for r in rows if r["pr"] == PR]
    live = [r for r in p9.open_prs("S") if r["watcher_id"] == "w2"]
    buried = (not live) and any(w == "w1" and s == "ABANDONED" for w, s in tail[1:])
    print(f"  rows={len(rows)}  fold_written={wrote}")
    print(f"  key history: {tail}")
    print(f"  w2 buried by a stale fold: {buried}")
    sys.exit(1 if buried else 0)
