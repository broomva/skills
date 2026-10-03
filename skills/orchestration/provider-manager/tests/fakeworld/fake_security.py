#!/usr/bin/env python3
"""A scratch stand-in for macOS `/usr/bin/security`, backed by a JSON file.

Both provider-manager and Claude Code call `security` by name, so putting this script first on
PATH gives a test (or the real-binary drill) a keychain of its own. It implements only what those
two callers use: find/add/delete-generic-password, `-i` (commands on stdin), show-keychain-info.

It refuses to run without FAKE_SECURITY_DB, so a misconfigured test can never fall through to the
login keychain.

Fault injection (set in the DB under "faults"): {"read_error": [service, ...],
"write_error": [service, ...]}.
"""

import fcntl
import json
import os
import shlex
import sys
import time

NOT_FOUND_RC = 44
NOT_FOUND_MSG = "security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain."


def _die(msg, rc):
    sys.stderr.write(msg + "\n")
    sys.exit(rc)


DB_PATH = os.environ.get("FAKE_SECURITY_DB")
if not DB_PATH:
    _die("fake security: FAKE_SECURITY_DB is unset; refusing to run (test guard)", 99)


class _Db:
    def __enter__(self):
        self.lock = open(DB_PATH + ".lock", "a+")
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("items", {})
        self.data.setdefault("faults", {})
        self.data.setdefault("log", [])
        self.dirty = False
        return self

    def log(self, op, svc, acct, ok):
        self.data["log"].append({"op": op, "svc": svc, "acct": acct, "ok": ok, "pid": os.getppid(), "ts": time.time()})
        self.data["log"] = self.data["log"][-2000:]
        self.dirty = True

    def __exit__(self, *exc):
        if self.dirty:
            tmp = DB_PATH + ".tmp.%d" % os.getpid()
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
            os.replace(tmp, DB_PATH)
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        self.lock.close()


def _key(svc, acct):
    return "%s\x00%s" % (svc, acct)


def _parse(args, value_flags, bool_flags):
    opts = {}
    i = 0
    while i < len(args):
        a = args[i]
        if a in value_flags:
            if i + 1 >= len(args):
                _die("security: option %s requires an argument" % a, 2)
            opts[a] = args[i + 1]
            i += 2
        elif a in bool_flags:
            opts[a] = True
            i += 1
        else:
            i += 1
    return opts


def _find(db, svc, acct):
    for k, v in db.data["items"].items():
        s, a = k.split("\x00", 1)
        if (svc is None or s == svc) and (acct is None or a == acct):
            return s, a, v
    return None


def cmd_find(args):
    opts = _parse(args, {"-s", "-a", "-l", "-D", "-c", "-C"}, {"-w", "-g"})
    svc, acct = opts.get("-s"), opts.get("-a")
    with _Db() as db:
        if svc in db.data["faults"].get("read_error", []):
            db.log("find", svc, acct, False)
            _die("security: SecKeychainSearchCopyNext: User interaction is not allowed.", 36)
        hit = _find(db, svc, acct)
        db.log("find", svc, acct, bool(hit))
    if not hit:
        _die(NOT_FOUND_MSG, NOT_FOUND_RC)
    s, a, v = hit
    if opts.get("-w"):
        sys.stdout.write(v + "\n")
    else:
        sys.stdout.write('keychain: "%s"\nclass: "genp"\nattributes:\n    "acct"<blob>="%s"\n    "svce"<blob>="%s"\n' % (DB_PATH, a, s))
    return 0


def cmd_add(args):
    opts = _parse(args, {"-s", "-a", "-w", "-X", "-l", "-D", "-j", "-c", "-C", "-T"}, {"-U", "-A"})
    svc, acct = opts.get("-s"), opts.get("-a", "")
    if svc is None:
        _die("security: add-generic-password requires -s", 2)
    if "-X" in opts:
        try:
            value = bytes.fromhex(opts["-X"]).decode("utf-8")
        except ValueError:
            _die("security: -X expects hex", 2)
    elif "-w" in opts:
        value = opts["-w"]
    else:
        _die("security: add-generic-password requires -w or -X in this fake", 2)
    with _Db() as db:
        if svc in db.data["faults"].get("write_error", []):
            db.log("add", svc, acct, False)
            _die("security: SecKeychainItemCreateFromContent: write refused (fault)", 1)
        k = _key(svc, acct)
        if k in db.data["items"] and not opts.get("-U"):
            db.log("add", svc, acct, False)
            _die("security: SecKeychainItemCreateFromContent: The specified item already exists in the keychain.", 45)
        db.data["items"][k] = value
        db.log("add", svc, acct, True)
    return 0


def cmd_delete(args):
    opts = _parse(args, {"-s", "-a", "-l"}, set())
    svc, acct = opts.get("-s"), opts.get("-a")
    with _Db() as db:
        hit = _find(db, svc, acct)
        if hit:
            del db.data["items"][_key(hit[0], hit[1])]
        db.log("delete", svc, acct, bool(hit))
    if not hit:
        _die(NOT_FOUND_MSG, NOT_FOUND_RC)
    return 0


COMMANDS = {
    "find-generic-password": cmd_find,
    "add-generic-password": cmd_add,
    "delete-generic-password": cmd_delete,
    "show-keychain-info": lambda args: 0,
}


def run(argv):
    if not argv:
        _die("usage: security <command>", 2)
    if argv[0] == "-i":
        rc = 0
        for line in sys.stdin.read().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = shlex.split(line)
            fn = COMMANDS.get(parts[0])
            if fn is None:
                _die("security: unknown command %s" % parts[0], 2)
            rc = fn(parts[1:]) or rc
        return rc
    fn = COMMANDS.get(argv[0])
    if fn is None:
        _die("security: unknown command %s (fake)" % argv[0], 2)
    return fn(argv[1:])


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
