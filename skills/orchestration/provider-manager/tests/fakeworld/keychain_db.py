"""Direct access to the fake keychain DB (same file and lock as fake_security.py)."""

import fcntl
import json
import os
from contextlib import contextmanager


@contextmanager
def db(path):
    with open(path + ".lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                data = {}
            data.setdefault("items", {})
            data.setdefault("faults", {})
            data.setdefault("log", [])
            yield data
            tmp = path + ".tmp.%d" % os.getpid()
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, path)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def key(svc, acct):
    return "%s\x00%s" % (svc, acct)


def read_raw(path, svc, acct):
    with db(path) as d:
        return d["items"].get(key(svc, acct))


def read_json(path, svc, acct):
    raw = read_raw(path, svc, acct)
    return json.loads(raw) if raw is not None else None


def write_json(path, svc, acct, value):
    with db(path) as d:
        d["items"][key(svc, acct)] = json.dumps(value)


def update_json(path, svc, acct, fn):
    """Read-modify-write one item atomically under the DB lock."""
    with db(path) as d:
        raw = d["items"].get(key(svc, acct))
        cur = json.loads(raw) if raw is not None else None
        new = fn(cur)
        d["items"][key(svc, acct)] = json.dumps(new)
        return new


def set_faults(path, **faults):
    with db(path) as d:
        d["faults"] = faults


def log(path):
    with db(path) as d:
        return list(d["log"])
