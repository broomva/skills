#!/usr/bin/env python3
"""Mutation check: remove each protection in turn; the test that pins it must fail.

A test suite that stays green when the lock blocks, when free text is stored
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
CTX, HOOK, SH = "scripts/ctx.py", "scripts/ctx_hook.py", "scripts/ctx-hook.sh"
T = "tests/"
# (name, file, original, mutant, pytest args selecting the pinning test)
MUTANTS = [
    ("blocking flock", CTX,
     "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n            return True",
     "fcntl.flock(fd, fcntl.LOCK_EX)\n            return True",
     [T + "test_lock_contention.py::test_a_held_lock_skips_the_append_and_the_hook_returns_in_time"]),
    ("board rewritten under the lock", CTX, "        LAST_LOCK_HOLD = time.monotonic() - held\n",
     "        write_board(scope, rebuild(scope.id, read_log(scope)))\n        LAST_LOCK_HOLD = time.monotonic() - held\n",
     [T + "test_lock_contention.py::test_the_lock_is_held_only_for_the_append"]),
    ("free text stored from Stop", CTX, '        payload = _extract_arc(data.get("last_assistant_message"))',
     '        payload = {"text": data.get("last_assistant_message")}',
     [T + "test_guard.py::test_a_prose_message_stores_nothing_of_itself"]),
    ("error text stored", CTX,
     '    return {"error": cls if isinstance(cls, str) and ERROR_RE.match(cls) else "unknown"}',
     '    return {"error": cls if isinstance(cls, str) else "unknown"}',
     [T + "test_hooks.py::test_stop_failure_reads_the_documented_shape_and_rejects_non_class_values"]),
    ("StopFailure reads only the documented shape", CTX,
     '    cls = data["error_type"] if isinstance(data.get("error_type"), str) else data.get("error")',
     '    cls = data.get("error_type")',
     [T + "test_hooks.py::test_stop_failure_stores_the_error_class_and_nothing_else"]),
    ("loose ARC shape", CTX, "        if line.startswith(ARC_PREFIX):\n            rest = line[len(ARC_PREFIX):]",
     "        if ARC_PREFIX in line:\n            rest = line[line.index(ARC_PREFIX) + len(ARC_PREFIX):]",
     [T + "test_hooks.py::test_stop_keeps_only_a_strict_arc_status_line"]),
    ("no guard", CTX, '    """True when `value` may be stored."""\n    low = value.lower()',
     '    """True when `value` may be stored."""\n    return True\n    low = value.lower()',
     [T + "test_guard.py", "-k", "drops_the_line"]),
    ("guard matches inside words", CTX, "            if i == 0 or not low[i - 1].isalnum():",
     "            if True:", [T + "test_guard.py::test_ordinary_text_passes"]),
    ("guard after the cut", CTX,
     '    line = _flat(line).rstrip()\n    if guard_ok(line):\n        out["arc_line"] = line[:ARC_LINE_MAX]',
     '    line = _flat(line).rstrip()[:ARC_LINE_MAX]\n    if guard_ok(line):\n        out["arc_line"] = line',
     [T + "test_guard.py::test_the_guard_sees_the_whole_line_before_the_cut"]),
    ("free text accepted on read", CTX,
     '    return guard_ok(ev["session_id"]) and _valid_payload(ev["type"], ev["payload"])', "    return True",
     [T + "test_guard.py", "-k", "hand_written"]),
    ("flattening keeps newlines", CTX,
     '_FLAT = {c: " " for c in list(range(0x20)) + list(range(0x7F, 0xA0)) + [0x2028, 0x2029]}',
     '_FLAT = {c: " " for c in [0x09]}',
     [T + "test_hooks.py::test_no_field_can_start_a_line_of_its_own_in_another_sessions_brief"]),
    ("no missing-file guard in the wrapper", SH, '[ -f "$hook" ] || exit 0\n', "",
     [T + "test_hooks.py::test_the_wrapper_exits_0_when_the_hook_script_is_gone"]),
    ("no self-deadline", HOOK,
     "        signal.setitimer(signal.ITIMER_REAL, max(0.001, budget - (time.monotonic() - _T0)))\n", "",
     [T + "test_fail_open.py", "-k", "hangs and never_escapes"]),
    ("the alarm armed past the deadline", HOOK,
     "max(0.001, budget - (time.monotonic() - _T0)))\n",
     "max(0.001, budget - (time.monotonic() - _T0)) + 0.5)\n",
     [T + "test_fail_open.py", "-k", "hangs and never_escapes"]),
    ("a bail that hangs past the wall", HOOK, "    os._exit(0)\n\n\ndef _read_stdin():",
     "    time.sleep(1.5)\n    os._exit(0)\n\n\ndef _read_stdin():",
     [T + "test_fail_open.py", "-k", "hangs and never_escapes"]),
    ("an error path that waits for the deadline", HOOK,
     "    except BaseException:\n        pass\n    os._exit(0)\n\n\nif __name__",
     "    except BaseException:\n        time.sleep(1)\n    os._exit(0)\n\n\nif __name__",
     [T + "test_fail_open.py", "-k", "raises and never_escapes"]),
    ("stdout not guarded", HOOK, "        sys.stdout = sys.stderr = devnull\n", "",
     [T + "test_fail_open.py", "-k", "prints and never_escapes"]),
    ("no deadline-miss record", HOOK, "        _record_miss((", "        ((",
     [T + "test_fail_open.py::test_a_hook_that_runs_out_of_time_leaves_a_breadcrumb"]),
    ("lock skip not recorded", CTX, '        _missed("lock")', "        pass",
     [T + "test_lock_contention.py::test_a_skipped_append_is_recorded_as_a_miss"]),
    ("no board cap", CTX,
     "        if cap is not None and scope.board_path.stat().st_size > cap:\n            raise BoardTooBig()\n", "",
     [T + "test_hook_deadline.py::test_a_board_over_the_cap_is_not_parsed_and_the_cut_off_is_recorded"]),
    ("SessionStart folds the whole tail", CTX,
     "        board, complete = read_board(scope, fold_cap=FOLD_CAP, board_cap=HOOK_BOARD_CAP,",
     "        board, complete = read_board(scope, fold_cap=None, board_cap=HOOK_BOARD_CAP,",
     [T + "test_rebuild_determinism.py::test_session_start_catches_a_stale_cache_up_across_runs"]),
    ("no tail signature check", CTX,
     '            if off > size or _tail_sig(_pread_all(fd, n, off - n)) != board.get("log_tail"):',
     "            if off > size:",
     [T + "test_rebuild_determinism.py::test_a_replaced_log_is_detected_by_the_tail_signature"]),
    ("torn-line heal removed", CTX,
     "            if size and os.pread(fd, 1, size - 1) != b\"\\n\":\n                line = b\"\\n\" + line\n", "",
     [T + "test_rebuild_determinism.py::test_a_torn_line_is_skipped_and_healed"]),
    ("unscoped falls back to a default scope", CTX, "    sid = scopes.by_repo.get(where.common_dir)\n",
     "    sid = scopes.by_repo.get(where.common_dir) or 'broomva'\n",
     [T + "test_scope_isolation.py::test_unscoped_repo_is_a_silent_noop"]),
    ("crm cwd not excluded", CTX, '    if sid is None or not guard_ok(where.cwd + "/"):', "    if sid is None:",
     [T + "test_scope_isolation.py::test_crm_and_credential_shaped_cwds_are_never_written"]),
    ("worktree common dir ignored", CTX,
     "    return Where(d, cur, _common_of(git_dir), _read_branch(git_dir, cur, timeout))",
     "    return Where(d, cur, os.path.realpath(git_dir), _read_branch(git_dir, cur, timeout))",
     [T + "test_scope_isolation.py::test_the_filesystem_resolver_agrees_with_git"]),
    ("git not time-bounded", CTX, "        out, _ = proc.communicate(timeout=timeout)",
     "        out, _ = proc.communicate()",
     [T + "test_hook_deadline.py::test_hooks_do_not_run_git_and_a_hanging_git_is_killed"]),
    ("doctor silent on a broken config", CTX,
     "            if problems:  # a broken config is reported from anywhere", "            if False:",
     [T + "test_hooks.py::test_doctor_reports_a_broken_config_from_any_directory"]),
    ("compare passes below the bar", "scripts/ctx_compare.py",
     '"pass": evidence and b >= THRESHOLD and s >= THRESHOLD', '"pass": evidence',
     [T + "test_compare.py::test_every_reason_in_its_order_and_the_pass_bar_is_the_raw_sets"]),
    ("compare writes the board", "scripts/ctx_compare.py",
     '    rows = ctx.rebuild(scope_id, ctx.read_log(sc))["sessions"]\n',
     '    _b = ctx.rebuild(scope_id, ctx.read_log(sc))\n    ctx.write_board(sc, _b)\n    rows = _b["sessions"]\n',
     [T + "test_compare.py::test_a_run_changes_none_of_the_store_files_and_appends_one_summary"]),
    ("compare calls every listed death continued", "scripts/ctx_compare.py",
     'reason = "died-then-continued" if died is not None and entry is not None and entry > died else "died"',
     'reason = "died-then-continued"',
     [T + "test_compare.py::test_every_reason_in_its_order_and_the_pass_bar_is_the_raw_sets"]),
    ("compare passes on no evidence", "scripts/ctx_compare.py",
     "    evidence = b is not None and s is not None",
     "    evidence = True\n    b = 1.0 if b is None else b\n    s = 1.0 if s is None else s",
     [T + "test_compare.py::test_no_evidence_is_not_a_pass"]),
    ("compare reads the session side from mtime", "scripts/ctx_compare.py",
     "if not f or f[0] < window or (last(sid) or 0.0) < window:", "if not f or f[0] < window:",
     [T + "test_compare.py::test_every_reason_in_its_order_and_the_pass_bar_is_the_raw_sets"]),
    ("compare accepts a second registration time", "scripts/ctx_compare.py",
     "    if registered and on_file and registered != on_file:", "    if False:",
     [T + "test_compare.py::test_the_registration_time_is_kept_in_the_first_line"]),
    ("compare reads the first tail window only", "scripts/ctx_compare.py",
     "TAIL_WINDOWS = (128 * 1024, 2 * 1024 * 1024, 16 * 1024 * 1024)", "TAIL_WINDOWS = (128 * 1024,)",
     [T + "test_compare.py::test_a_last_entry_larger_than_the_first_window_is_still_found"]),
    ("compare runs on the prototype's line", "scripts/ctx_compare.py",
     "    if first is None or is_prototype(first):", "    if False:",
     [T + "test_compare.py::test_the_prototypes_first_line_is_refused_until_the_owner_moves_it"]),
    ("compare drops a whole first line at the window's edge", "scripts/ctx_compare.py",
     "fh.seek(max(0, start - 1))", "fh.seek(start)",
     [T + "test_compare.py::test_a_window_that_starts_exactly_on_a_line_keeps_that_line"]),
    ("compare crashes without a line on a logic error", "scripts/ctx_compare.py",
     "    except Exception as exc:", "    except (CompareError, OSError, ValueError) as exc:",
     [T + "test_compare.py::test_a_comparison_that_raises_is_written_as_an_error_line"]),
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
