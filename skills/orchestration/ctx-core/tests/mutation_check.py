#!/usr/bin/env python3
"""Mutation check: remove each protection in turn; the test that pins it must fail.

A test suite that stays green when the lock blocks, when redaction is skipped
or when SessionStart re-parses the log proves nothing about those properties.
Each mutant below edits one place in a scratch copy of the skill and runs the
ONE test that pins that protection (a node id, or a -k expression), so a timing
flake elsewhere in the file cannot pass for a kill. Exit 1 on any mutant that
survives, whose anchor is gone (STALE), or whose run errored.

    python3 tests/mutation_check.py
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

SKILL = pathlib.Path(__file__).resolve().parents[1]
CTX, HOOK = "scripts/ctx.py", "scripts/ctx_hook.py"
T = "tests/"
# (name, file, original, mutant, pytest args selecting the pinning test)
MUTANTS = [
    ("blocking flock", CTX,
     "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n            return True",
     "fcntl.flock(fd, fcntl.LOCK_EX)\n            return True",
     [T + "test_lock_contention.py::test_a_held_lock_skips_the_append_and_the_hook_returns_in_time"]),
    ("no redaction of the payload", CTX, '    event["payload"] = redact(payload)\n',
     '    event["payload"] = payload\n',
     [T + "test_redaction.py::test_nothing_secret_reaches_the_log_through_the_stop_hook"]),
    ("clip before redact", CTX, "return _flat(redact_text(value))", "return redact_text(_flat(value))",
     [T + "test_redaction.py::test_a_token_straddling_the_clip_is_redacted_before_the_cut"]),
    ("pre-cap keeps a partial token", CTX, '            value = re.sub(r"\\S*$", "", value[:PRECAP])',
     "            value = value[:PRECAP]",
     [T + "test_redaction.py::test_the_pre_cap_leaves_no_partial_token"]),
    ("quadratic key prefix", CTX, "[a-z0-9_.-]{0,40}?", "[a-z0-9_.-]*?",
     [T + "test_redaction.py", "-k", "quadratic"]),
    ("flattening keeps newlines", CTX, 're.sub(r"[\\x00-\\x1f\\x7f-\\x9f\\u2028\\u2029]", " ", str(s))',
     're.sub(r"[\\x00-\\x08\\x0b-\\x1f\\x7f]", " ", str(s))',
     [T + "test_hooks.py::test_no_field_can_start_a_line_of_its_own_in_another_sessions_brief"]),
    ("identifiers redacted like free text", CTX, "            event[key] = _flat(event[key], 1024)",
     "            event[key] = redact(event[key])",
     [T + "test_hooks.py::test_a_secret_shaped_branch_name_still_matches_its_peers"]),
    ("no self-deadline", HOOK,
     "        signal.setitimer(signal.ITIMER_REAL, max(0.001, budget - (time.monotonic() - _T0)))\n", "",
     [T + "test_fail_open.py", "-k", "hangs and never_escapes"]),
    ("stdout not guarded", HOOK, "        sys.stdout = sys.stderr = devnull\n", "",
     [T + "test_fail_open.py", "-k", "prints and never_escapes"]),
    ("no deadline-miss record", HOOK, "        _record_miss((", "        ((",
     [T + "test_fail_open.py::test_a_hook_that_runs_out_of_time_leaves_a_breadcrumb"]),
    ("lock skip not recorded", CTX, '        _missed("lock")', "        pass",
     [T + "test_lock_contention.py::test_a_skipped_append_is_recorded_as_a_miss"]),
    ("no board cap", CTX,
     "        if cap is not None and scope.board_path.stat().st_size > cap:\n            raise BoardTooBig()\n", "",
     [T + "test_hook_deadline.py::test_a_board_over_the_cap_is_not_parsed_and_the_cut_off_is_recorded"]),
    ("SessionStart full rebuild", CTX,
     "            board = load_board(scope, HOOK_BOARD_CAP)  # the cached board; the log is never parsed here",
     "            board = rebuild(scope.id, read_log(scope))",
     [T + "test_rebuild_determinism.py::test_session_start_reads_the_cached_board_and_never_the_whole_log"]),
    ("no fold cap in hooks", CTX,
     "    if cap is not None and size > cap:\n        return None\n    board = rebuild(", "    board = rebuild(",
     [T + "test_rebuild_determinism.py::test_session_start_reads_the_cached_board_and_never_the_whole_log"]),
    ("no tail signature check", CTX,
     "            prior = _pread_all(fd, n, off - n)\n            if _tail_sig(prior) == board.get(\"log_tail\"):",
     "            prior = _pread_all(fd, n, off - n)\n            if True:",
     [T + "test_rebuild_determinism.py::test_a_replaced_log_is_detected_by_the_tail_signature"]),
    ("torn-line heal removed", CTX,
     "            if size and os.pread(fd, 1, size - 1) != b\"\\n\":\n                line = b\"\\n\" + line\n", "",
     [T + "test_rebuild_determinism.py::test_a_torn_line_is_skipped_and_healed"]),
    ("unscoped falls back to a default scope", CTX, "    sid = scopes.by_repo.get(where.common_dir)\n",
     "    sid = scopes.by_repo.get(where.common_dir) or 'broomva'\n",
     [T + "test_scope_isolation.py::test_unscoped_repo_is_a_silent_noop"]),
    ("crm cwd not excluded", CTX, "    if sid is None or excluded_path(where.cwd):\n", "    if sid is None:\n",
     [T + "test_scope_isolation.py::test_crm_and_secret_shaped_cwds_are_never_written"]),
    ("worktree common dir ignored", CTX,
     "    return Where(d, cur, _common_of(git_dir), _read_branch(git_dir, cur, timeout))",
     "    return Where(d, cur, os.path.realpath(git_dir), _read_branch(git_dir, cur, timeout))",
     [T + "test_scope_isolation.py::test_the_filesystem_resolver_agrees_with_git"]),
    ("git not time-bounded", CTX, "        out, _ = proc.communicate(timeout=timeout)",
     "        out, _ = proc.communicate()",
     [T + "test_hook_deadline.py::test_hooks_do_not_run_git_and_a_hanging_git_is_killed"]),
    ("StopFailure reads only the documented shape", CTX,
     "        cls, detail = data.get(\"error\"), data.get(\"error_details\")",
     "        cls, detail = data.get(\"error_type\"), data.get(\"error\")",
     [T + "test_hooks.py::test_stop_failure_publishes_died_from_the_payload_claude_code_sends"]),
    ("doctor silent on a broken config", CTX,
     "            if problems:  # a broken config is reported from anywhere", "            if False:",
     [T + "test_hooks.py::test_doctor_reports_a_broken_config_from_any_directory"]),
]


def main() -> int:
    bad = 0
    for name, rel, old, new, args in MUTANTS:
        with tempfile.TemporaryDirectory() as d:
            dst = pathlib.Path(d) / "ctx-core"
            shutil.copytree(SKILL, dst, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
            f = dst / rel
            text = f.read_text(encoding="utf-8")
            if text.count(old) != 1:
                print("STALE    %s: the original text is not in %s exactly once" % (name, rel))
                bad += 1
                continue
            f.write_text(text.replace(old, new), encoding="utf-8")
            r = subprocess.run([sys.executable, "-m", "pytest", *args, "-q", "-x", "-p", "no:cacheprovider"],
                               cwd=str(dst), capture_output=True, text=True, timeout=900)
            # pytest exit codes: 1 = tests failed. 2-5 are an interrupted run, an
            # internal error, a usage error, or no tests collected: the protection
            # was not shown to matter, so they fail the gate rather than count.
            verdict = {0: "SURVIVED", 1: "KILLED  "}.get(r.returncode, "ERROR   ")
            bad += verdict != "KILLED  "
            print("%s %s  (%s)%s" % (verdict, name, " ".join(args),
                                     "" if r.returncode in (0, 1) else "  pytest exit %d" % r.returncode), flush=True)
    print("not killed: %d of %d" % (bad, len(MUTANTS)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
