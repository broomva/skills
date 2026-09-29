#!/usr/bin/env python3
"""Mutation check: remove each protection in turn; the named tests must go red.

A test suite that stays green when the lock blocks, when redaction is skipped
or when SessionStart re-parses the log proves nothing about those properties.
Each mutant below edits one line in a scratch copy of the skill, runs the test
file that should catch it, and must be KILLED (tests fail). Exit 1 on any
survivor.

    python3 tests/mutation_check.py
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

SKILL = pathlib.Path(__file__).resolve().parents[1]
# (name, file, original, mutant, test file that must fail)
MUTANTS = [
    ("blocking flock", "scripts/ctx.py",
     "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n            return True",
     "fcntl.flock(fd, fcntl.LOCK_EX)\n            return True", "tests/test_lock_contention.py"),
    ("no redaction in make_event", "scripts/ctx.py", "    return redact(event)\n", "    return event\n",
     "tests/test_redaction.py"),
    ("clip before redact", "scripts/ctx.py", "return _flat(redact_text(value[: 8 * MAX_STR]))",
     "return redact_text(_flat(value))", "tests/test_redaction.py"),
    ("flattening keeps newlines", "scripts/ctx.py", 're.sub(r"[\\x00-\\x1f\\x7f\\u2028\\u2029]", " ", str(s))',
     're.sub(r"[\\x00-\\x08\\x0b-\\x1f\\x7f]", " ", str(s))', "tests/test_hooks.py"),
    ("no self-deadline", "scripts/ctx_hook.py",
     "        signal.setitimer(signal.ITIMER_REAL, max(0.001, budget - (time.monotonic() - _T0)))\n", "",
     "tests/test_fail_open.py"),
    ("stdout not guarded", "scripts/ctx_hook.py", "        sys.stdout = sys.stderr = devnull\n", "",
     "tests/test_fail_open.py"),
    ("no deadline-miss record", "scripts/ctx_hook.py", "        _record_miss((", "        ((",
     "tests/test_fail_open.py"),
    ("SessionStart full rebuild", "scripts/ctx.py",
     "            board = load_board(scope)  # the cached board; the log is never parsed here",
     "            board = rebuild(scope.id, read_log(scope))", "tests/test_rebuild_determinism.py"),
    ("no fold cap in hooks", "scripts/ctx.py",
     "    if cap is not None and size > cap:\n        return None\n    board = rebuild(", "    board = rebuild(",
     "tests/test_rebuild_determinism.py"),
    ("no tail signature check", "scripts/ctx.py",
     "            prior = _pread_all(fd, n, off - n)\n            if _tail_sig(prior) == board.get(\"log_tail\"):",
     "            prior = _pread_all(fd, n, off - n)\n            if True:", "tests/test_rebuild_determinism.py"),
    ("torn-line heal removed", "scripts/ctx.py",
     "            if size and os.pread(fd, 1, size - 1) != b\"\\n\":\n                line = b\"\\n\" + line\n", "",
     "tests/test_rebuild_determinism.py"),
    ("unscoped falls back to a default scope", "scripts/ctx.py",
     "    sid = scopes.by_repo.get(where.common_dir)\n",
     "    sid = scopes.by_repo.get(where.common_dir) or 'broomva'\n", "tests/test_scope_isolation.py"),
    ("crm cwd not excluded", "scripts/ctx.py",
     "    if sid is None or excluded_path(where.cwd):\n", "    if sid is None:\n",
     "tests/test_scope_isolation.py"),
    ("worktree common dir ignored", "scripts/ctx.py",
     "    return Where(d, cur, _common_of(git_dir), _read_branch(git_dir, cur, timeout))",
     "    return Where(d, cur, os.path.realpath(git_dir), _read_branch(git_dir, cur, timeout))",
     "tests/test_scope_isolation.py"),
    ("git not time-bounded", "scripts/ctx.py", "        out, _ = proc.communicate(timeout=timeout)",
     "        out, _ = proc.communicate()", "tests/test_hook_deadline.py"),
    ("StopFailure reads only the documented shape", "scripts/ctx.py",
     "        cls, detail = data.get(\"error\"), data.get(\"error_details\")",
     "        cls, detail = data.get(\"error_type\"), data.get(\"error\")", "tests/test_hooks.py"),
    ("doctor silent on a broken config", "scripts/ctx.py",
     "            if problems:  # a broken config is reported from anywhere", "            if False:",
     "tests/test_hooks.py"),
]


def main() -> int:
    survivors = 0
    for name, rel, old, new, test in MUTANTS:
        with tempfile.TemporaryDirectory() as d:
            dst = pathlib.Path(d) / "ctx-core"
            shutil.copytree(SKILL, dst, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
            f = dst / rel
            text = f.read_text()
            if text.count(old) != 1:
                print("STALE    %s: the original line is no longer in %s" % (name, rel))
                survivors += 1
                continue
            f.write_text(text.replace(old, new))
            r = subprocess.run([sys.executable, "-m", "pytest", test, "-q", "-x", "-p", "no:cacheprovider"],
                               cwd=str(dst), capture_output=True, text=True, timeout=900)
            # pytest exit codes: 1 = tests failed. 2-5 are an interrupted run, an
            # internal error, a usage error, or no tests collected: the protection
            # was not shown to matter, so they fail the gate rather than count.
            verdict = {0: "SURVIVED", 1: "KILLED  "}.get(r.returncode, "ERROR   ")
            survivors += verdict != "KILLED  "
            print("%s %s  (%s)%s" % (verdict, name, test,
                                     "" if r.returncode in (0, 1) else "  pytest exit %d" % r.returncode), flush=True)
    print("survivors: %d of %d" % (survivors, len(MUTANTS)))
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
