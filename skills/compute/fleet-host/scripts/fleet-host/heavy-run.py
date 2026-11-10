#!/usr/bin/env python3
"""GCP fleet host heavy-work runner (BRO-3651). Usage: fleet-heavy-run <label> <cmd> [args...]

Port of the Mac's ~/.cache/sti4322/heavy-run.py to a counting semaphore:
- N slots, each an fcntl exclusive flock on /var/lib/fleet/heavy/slot-<i>.lock. The kernel releases a
  lock when its holder exits or crashes, so a slot can never go stale.
- N comes from /etc/fleet/heavy-slots (written by startup.sh), default 1.
- Waits while this host's own reading is red (MemAvailable < 15% or load1/cpu > 1.5).
- Runs the command in its own process group and kills the whole group on exit or signal.
- slot-<i>.owner names the holder, for humans only (it is not the lock; idle-stop probes the locks).
"""
import fcntl, os, signal, subprocess, sys, time
from datetime import datetime, timezone

DIR = os.environ.get("FLEET_HEAVY_DIR", "/var/lib/fleet/heavy")
SLOTS_FILE = "/etc/fleet/heavy-slots"


def slots():
    try:
        return max(1, int(open(SLOTS_FILE).read().strip()))
    except (OSError, ValueError):
        return 1


def red():
    try:
        mem = dict(l.split(":", 1) for l in open("/proc/meminfo"))
        avail = int(mem["MemAvailable"].split()[0]) / int(mem["MemTotal"].split()[0])
        return avail < 0.15 or os.getloadavg()[0] / (os.cpu_count() or 1) > 1.5
    except (OSError, KeyError, ValueError):
        return False


def acquire(label):
    os.makedirs(DIR, exist_ok=True)
    announced = False
    while True:
        while red():
            print("fleet-heavy-run: host red, waiting 60s", flush=True)
            time.sleep(60)
        for i in range(slots()):
            f = open(os.path.join(DIR, f"slot-{i}.lock"), "a")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                f.close()
                continue
            with open(os.path.join(DIR, f"slot-{i}.owner"), "w") as o:
                o.write(f"{label} {datetime.now(timezone.utc).isoformat()} pid={os.getpid()}\n")
            return i, f
        if not announced:
            print(f"fleet-heavy-run: all {slots()} slots busy, waiting ({label})", flush=True)
            announced = True
        time.sleep(5)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    label, cmd = sys.argv[1], sys.argv[2:]
    slot, lock = acquire(label)
    print(f"fleet-heavy-run: slot {slot} acquired ({label})", flush=True)
    proc = None

    def group_alive(pgid):
        try:
            os.killpg(pgid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def end_group(pgid):
        """SIGTERM the whole group, give it 30 s, then SIGKILL. Returns only once no member is left, so the
        slot is never released while any part of the job still runs (P20 r1 #6). No waitpid here: the
        signal handler below must not contend with the main wait() for Popen's internal lock."""
        for sig, grace in ((signal.SIGTERM, 30.0), (signal.SIGKILL, 10.0)):
            if not group_alive(pgid):
                return
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                return
            deadline = time.time() + grace
            while time.time() < deadline and group_alive(pgid):
                proc.poll()  # reaps the leader once it exits, so a zombie does not count as alive
                time.sleep(0.2)

    def on_signal(*_):
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)  # only signal here; main() waits and escalates
            except ProcessLookupError:
                pass
        raise SystemExit(143)

    for s_ in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s_, on_signal)
    try:
        proc = subprocess.Popen(cmd, start_new_session=True)  # inside try: a bad command still frees the slot
        return proc.wait()
    except FileNotFoundError:
        print(f"fleet-heavy-run: command not found: {cmd[0]}", file=sys.stderr)
        return 127
    finally:
        for s_ in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(s_, signal.SIG_IGN)  # finish cleanup even if signalled again
        if proc is not None:
            end_group(proc.pid)
        try:
            open(os.path.join(DIR, f"slot-{slot}.owner"), "w").close()
        except OSError:
            pass
        lock.close()


if __name__ == "__main__":
    sys.exit(main())
