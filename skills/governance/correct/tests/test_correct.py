#!/usr/bin/env -S python3 -I
"""Tests for scripts/correct.py: init on a repository, and check through the wrapper.

Every case builds a throwaway git repository and runs the real command against it, with the
home directory and the host name fixed (RULES_CHECK_HOME, RULES_CHECK_HOST) so the machine's
own settings are never read. The cases that break the enforcer or its registration are the
proof that the replay can fail: a setup command whose check passes whatever is installed
would pass all of the others too.

  python3 -I tests/test_correct.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import site
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
CORRECT = SKILL / "scripts" / "correct.py"
if site.getusersitepackages() not in sys.path:  # PyYAML lives in user site-packages
    sys.path.append(site.getusersitepackages())
import yaml  # noqa: E402

sys.path.append(str(HERE))
sys.path.append(str(SKILL / "scripts"))
import correct  # noqa: E402
import vendored  # noqa: E402

ALLOW_ALL = "#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n"
BLOCK_ALL = ("#!/usr/bin/env python3\nimport sys\n"
             "print('Branch first: git checkout -b <name>; git branch -f main origin/main; "
             "Edit the copy', file=sys.stderr)\nsys.exit(2)\n")


def tree(root: Path) -> dict[str, str]:
    """Every file outside .git and bytecode caches, by content hash."""
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"))
            if p.is_file() and ".git" not in p.relative_to(root).parts and "__pycache__" not in p.parts}


class CorrectCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.repo = self.tmp / "repo"
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True, capture_output=True)
        self.env = dict(os.environ, RULES_CHECK_HOME=str(self.tmp / "home"), RULES_CHECK_HOST="ci-runner")
        for key in ("RULES_CHECK_ROOT", "BSTACK_ALLOW_MAIN_EDIT"):
            self.env.pop(key, None)

    def run_correct(self, *args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-I", str(CORRECT), *args], cwd=str(cwd or self.repo),
                              env=env or self.env, capture_output=True, text=True, timeout=600)

    def rows(self) -> tuple[int, dict[str, dict]]:
        proc = self.run_correct("check", "--json")
        return proc.returncode, {r["id"]: r for r in json.loads(proc.stdout)}

    def init(self) -> subprocess.CompletedProcess:
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc


class Init(CorrectCase):
    def test_a_fresh_repository_gets_a_registry_whose_replay_passes(self) -> None:
        self.init()
        for rel in (".control/rules.yaml", ".control/policy.yaml", ".claude/settings.json",
                    *(f"scripts/{name}" for name in correct.SCRIPT_FILES)):
            self.assertTrue((self.repo / rel).is_file(), rel)
        self.assertTrue(os.access(self.repo / "scripts" / correct.ENFORCER, os.X_OK))
        code, rows = self.rows()
        self.assertEqual(code, 0, rows)
        self.assertEqual({k: v["status"] for k, v in rows.items()},
                         {"branch-first": "PASS", "registry-completeness": "PASS"})

    def test_dry_run_writes_nothing(self) -> None:
        proc = self.run_correct("init", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("would write  .control/rules.yaml", proc.stdout)
        self.assertEqual(tree(self.repo), {})

    def test_a_second_init_changes_nothing(self) -> None:
        self.init()
        before = tree(self.repo)
        again = self.run_correct("init")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("already has a registry", again.stdout)
        self.assertEqual(tree(self.repo), before)

    def test_an_existing_registry_is_never_replaced_even_with_force(self) -> None:
        (self.repo / ".control").mkdir()
        (self.repo / ".control" / "rules.yaml").write_text("version: 1\nrules: []\n")
        before = tree(self.repo)
        proc = self.run_correct("init", "--force")
        self.assertEqual(tree(self.repo), before)
        # Nothing written, and the answer is the replay's: an empty registry is not a pass.
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("Nothing written", proc.stdout)
        self.assertIn("no rules", proc.stderr)

    def test_an_existing_registry_that_does_not_hold_makes_init_exit_1(self) -> None:
        self.init()
        (self.repo / "scripts" / correct.ENFORCER).write_text(ALLOW_ALL)
        before = tree(self.repo)
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("expected block, enforcer said allow", proc.stdout)
        self.assertEqual(tree(self.repo), before)

    def test_dry_run_on_an_existing_registry_does_not_replay(self) -> None:
        (self.repo / ".control").mkdir()
        (self.repo / ".control" / "rules.yaml").write_text("version: 1\nrules: []\n")
        proc = self.run_correct("init", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("replaying", proc.stdout)

    def test_a_file_where_a_directory_must_go_stops_init_before_anything_is_written(self) -> None:
        (self.repo / ".claude").write_text("my file")
        before = tree(self.repo)
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn(".claude is a file", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(tree(self.repo), before)

    def refused_with_nothing_written(self, needle: str, *args: str, env: dict | None = None) -> None:
        before = tree(self.repo)
        proc = self.run_correct("init", *args, env=env)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn(needle, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(tree(self.repo), before)

    def settings(self, value: object) -> None:
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude" / "settings.json").write_text(json.dumps(value))

    def test_settings_whose_pretooluse_is_not_a_list_are_refused(self) -> None:
        self.settings({"hooks": {"PreToolUse": {"matcher": "Edit"}}})
        self.refused_with_nothing_written("`hooks.PreToolUse` is not a list")
        self.settings({"hooks": "not-a-dict"})
        self.refused_with_nothing_written("`hooks.PreToolUse` is not a list")

    def test_settings_that_are_not_a_json_object_are_refused(self) -> None:
        self.settings([])
        self.refused_with_nothing_written("is not a JSON object")

    def test_a_dangling_symlink_where_a_file_goes_is_refused(self) -> None:
        outside = self.tmp / "outside-target"
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / correct.ENFORCER).symlink_to(outside)
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn(f"scripts/{correct.ENFORCER} is a symlink", proc.stderr)
        self.assertFalse(outside.exists())
        self.assertFalse((self.repo / ".control").exists())

    def test_force_does_not_write_through_a_symlinked_file(self) -> None:
        victim = self.tmp / "victim"
        victim.write_text("theirs")
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / correct.ENFORCER).symlink_to(victim)
        proc = self.run_correct("init", "--force")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(victim.read_text(), "theirs")
        self.assertFalse(os.access(victim, os.X_OK))

    def test_a_governance_directory_that_is_a_symlink_is_refused(self) -> None:
        outside = self.tmp / "outside-gov"
        outside.mkdir()
        (self.repo / ".control").symlink_to(outside, target_is_directory=True)
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn(".control/ is a symlink", proc.stderr)
        self.assertEqual(list(outside.iterdir()), [])

    def test_only_the_hook_and_the_fixtures_are_made_executable(self) -> None:
        self.init()
        modes = {name: os.access(self.repo / "scripts" / name, os.X_OK) for name in correct.SCRIPT_FILES}
        self.assertEqual(modes, {"branch-first-hook.py": True, "rules_fixtures.py": True,
                                 "governance_paths.py": False, "rules_case_data.py": False})

    def test_a_hook_that_is_the_skills_copy_but_not_executable_is_made_executable(self) -> None:
        (self.repo / "scripts").mkdir()
        hook = self.repo / "scripts" / correct.ENFORCER
        hook.write_bytes((SKILL / "scripts" / correct.ENFORCER).read_bytes())
        hook.chmod(0o644)
        self.init()  # without --force: the bytes are the skill's, only the mode was missing
        self.assertTrue(os.access(hook, os.X_OK))

    def test_settings_with_a_malformed_pretooluse_entry_are_refused(self) -> None:
        self.settings({"hooks": {"PreToolUse": ["Edit"]}})
        self.refused_with_nothing_written("is not {matcher, hooks: [...]}")
        self.settings({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": ["x"]}]}})
        self.refused_with_nothing_written("is not {matcher, hooks: [...]}")

    def test_an_entry_that_only_names_the_enforcer_is_refused_not_kept(self) -> None:
        self.settings({"hooks": {"PreToolUse": [dict(correct.HOOK_GROUP, hooks=[
            {"type": "command", "command": f"echo {correct.HOOK_COMMAND}", "timeout": 10}])]}})
        self.refused_with_nothing_written("in another form")

    def test_the_enforcer_entry_on_fewer_tools_is_refused_not_kept(self) -> None:
        self.settings({"hooks": {"PreToolUse": [dict(correct.HOOK_GROUP, matcher="Write")]}})
        self.refused_with_nothing_written("in another form")

    def test_a_read_only_settings_file_is_refused_and_left_as_it_is(self) -> None:
        self.settings({})
        path = self.repo / ".claude" / "settings.json"
        path.chmod(0o444)
        self.addCleanup(path.chmod, 0o644)
        self.refused_with_nothing_written(".claude/settings.json is read-only")
        self.assertEqual(path.read_text(), "{}")

    def test_a_directory_that_cannot_be_written_is_refused(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root writes into any directory")
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude").chmod(0o555)
        self.addCleanup((self.repo / ".claude").chmod, 0o755)
        self.refused_with_nothing_written(".claude/ is not writable")

    def without_yaml(self) -> dict:
        home = self.tmp / "no-yaml-home"
        home.mkdir(exist_ok=True)
        env = dict(self.env, HOME=str(home))
        probe = "import site, sys; sys.path.append(site.getusersitepackages()); import yaml"
        if subprocess.run([sys.executable, "-I", "-c", probe], env=env, capture_output=True).returncode == 0:
            self.skipTest("PyYAML is installed outside the user site here, so it cannot be hidden")
        return env

    def test_without_pyyaml_init_writes_nothing_and_says_what_to_install(self) -> None:
        self.refused_with_nothing_written("PyYAML is not importable", env=self.without_yaml())

    def test_without_pyyaml_check_exits_2(self) -> None:
        self.init()
        proc = self.run_correct("check", env=self.without_yaml())
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("PyYAML is not importable", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_a_repository_with_the_other_governance_directory_gets_its_registry_there(self) -> None:
        (self.repo / ".broomva").mkdir()
        self.init()
        self.assertTrue((self.repo / ".broomva" / "rules.yaml").is_file())
        self.assertTrue((self.repo / ".broomva" / "policy.yaml").is_file())
        self.assertFalse((self.repo / ".control").exists())

    def test_a_script_that_is_already_the_skills_copy_is_kept_without_force(self) -> None:
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "governance_paths.py").write_bytes((SKILL / "scripts" / "governance_paths.py").read_bytes())
        proc = self.init()
        self.assertIn("keep   scripts/governance_paths.py (already this version)", proc.stdout)

    def test_a_scripts_directory_that_is_a_symlink_is_refused(self) -> None:
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.repo / "scripts").symlink_to(outside, target_is_directory=True)
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("scripts/ is a symlink", proc.stderr)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.repo / ".control").exists())

    def test_a_settings_file_that_is_a_symlink_is_refused(self) -> None:
        theirs = self.tmp / "their-settings.json"
        theirs.write_text("{}")
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.json").symlink_to(theirs)
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn(".claude/settings.json is a symlink", proc.stderr)
        self.assertEqual(theirs.read_text(), "{}")
        self.assertFalse((self.repo / "scripts").exists())

    def test_the_registry_is_the_last_file_written(self) -> None:
        writes, _kept, _conflicts = correct.plan(self.repo)
        self.assertEqual(writes[-1][0], self.repo / ".control" / "rules.yaml")

    def test_a_write_that_fails_midway_leaves_the_repository_not_set_up(self) -> None:
        real, calls = correct.write_file, []

        def failing(path: Path, content: bytes, executable: bool) -> None:
            calls.append(path)
            if len(calls) == 3:
                raise OSError("disk full")
            real(path, content, executable)

        correct.write_file = failing
        self.addCleanup(setattr, correct, "write_file", real)
        with self.assertRaises(correct.Refused) as caught:
            correct.init(self.repo, [])
        self.assertIn("disk full", str(caught.exception))
        self.assertIn("Written before it: scripts/branch-first-hook.py, scripts/governance_paths.py",
                      str(caught.exception))
        self.assertFalse((self.repo / ".control" / "rules.yaml").exists())
        correct.write_file = real
        again = self.run_correct("init")  # the next run sets it up; what was written is kept as is
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)

    def test_a_written_file_replaces_the_old_one_whole(self) -> None:
        target = self.tmp / "dir" / "settings.json"
        correct.write_file(target, b"one", False)
        correct.write_file(target, b"two", True)
        self.assertEqual(target.read_bytes(), b"two")
        self.assertTrue(os.access(target, os.X_OK))
        self.assertEqual([p.name for p in target.parent.iterdir()], ["settings.json"])  # no temp file left

    def test_a_replaced_file_keeps_its_permissions(self) -> None:
        (self.repo / ".claude").mkdir()
        path = self.repo / ".claude" / "settings.json"
        path.write_text("{}")
        path.chmod(0o600)
        self.init()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertIn("branch-first-hook.py", path.read_text())
        self.assertEqual((self.repo / ".control" / "rules.yaml").stat().st_mode & 0o777, 0o644)  # a new file

    def test_a_registry_path_that_is_a_directory_is_refused(self) -> None:
        (self.repo / ".control" / "rules.yaml").mkdir(parents=True)
        self.refused_with_nothing_written(".control/rules.yaml exists and is not a regular file")

    def test_without_git_the_command_says_so(self) -> None:
        empty = self.tmp / "empty-path"
        empty.mkdir()
        for command in ("init", "check"):
            proc = self.run_correct(command, env=dict(self.env, PATH=str(empty)))
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("git could not be run", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_a_write_that_cannot_land_leaves_no_temporary_file(self) -> None:
        parent = self.tmp / "dir"
        (parent / "taken" / "inside").mkdir(parents=True)  # a non-empty directory where the file must go
        with self.assertRaises(OSError):
            correct.write_file(parent / "taken", b"x", False)
        self.assertEqual([p.name for p in parent.iterdir()], ["taken"])

    def test_a_differing_script_stops_init_before_anything_is_written(self) -> None:
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "governance_paths.py").write_text("# the repository's own\n")
        before = tree(self.repo)
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("scripts/governance_paths.py exists and differs", proc.stderr)
        self.assertIn("--force", proc.stderr)
        self.assertEqual(tree(self.repo), before)
        forced = self.run_correct("init", "--force")
        self.assertEqual(forced.returncode, 0, forced.stdout + forced.stderr)
        self.assertEqual((self.repo / "scripts" / "governance_paths.py").read_bytes(),
                         (SKILL / "scripts" / "governance_paths.py").read_bytes())

    def test_existing_settings_keep_their_keys_and_hooks(self) -> None:
        (self.repo / ".claude").mkdir()
        mine = {"permissions": {"allow": ["Bash(ls:*)"]},
                "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}
        (self.repo / ".claude" / "settings.json").write_text(json.dumps(mine))
        self.init()
        got = json.loads((self.repo / ".claude" / "settings.json").read_text())
        self.assertEqual(got["permissions"], mine["permissions"])
        self.assertEqual(got["hooks"]["SessionStart"], mine["hooks"]["SessionStart"])
        self.assertEqual(got["hooks"]["PreToolUse"], [correct.HOOK_GROUP])

    def test_settings_that_already_run_the_enforcer_are_left_alone(self) -> None:
        (self.repo / ".claude").mkdir()
        text = json.dumps({"hooks": {"PreToolUse": [correct.HOOK_GROUP]}})
        (self.repo / ".claude" / "settings.json").write_text(text)
        self.init()
        self.assertEqual((self.repo / ".claude" / "settings.json").read_text(), text)

    def test_unreadable_settings_stop_init_before_anything_is_written(self) -> None:
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.json").write_text("{not json")
        before = tree(self.repo)
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("not readable JSON", proc.stderr)
        self.assertEqual(tree(self.repo), before)

    def test_a_gate_the_repository_already_has_and_no_row_proves_makes_init_exit_1(self) -> None:
        (self.repo / ".control").mkdir()
        (self.repo / ".control" / "policy.yaml").write_text(
            "gates:\n  hard:\n    - id: no-force-push\n      pattern: 'git push --force'\n")
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("policy gate no-force-push has a pattern but no row", proc.stdout)
        self.assertIn("the files are written", proc.stderr)
        self.assertTrue((self.repo / ".control" / "rules.yaml").is_file())
        self.assertIn("no-force-push", (self.repo / ".control" / "policy.yaml").read_text())  # theirs, untouched

    def test_a_directory_below_the_top_of_the_checkout_is_refused(self) -> None:
        (self.repo / "sub").mkdir()
        proc = self.run_correct("init", "--root", str(self.repo / "sub"))
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("not the top of a git checkout", proc.stderr)

    def test_an_unknown_init_option_is_refused(self) -> None:
        proc = self.run_correct("init", "--frce")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(tree(self.repo), {})


class CheckCanFail(CorrectCase):
    """Break what init installed, one piece at a time; each break must turn the replay red."""

    def setUp(self) -> None:
        super().setUp()
        self.init()

    def test_an_enforcer_that_allows_everything_fails_its_proofs(self) -> None:
        (self.repo / "scripts" / correct.ENFORCER).write_text(ALLOW_ALL)
        code, rows = self.rows()
        self.assertEqual(code, 1)
        self.assertEqual(rows["branch-first"]["status"], "FAIL")
        self.assertTrue(any("expected block, enforcer said allow" in f for f in rows["branch-first"]["fails"]))

    def test_an_enforcer_that_refuses_everything_fails_its_controls(self) -> None:
        (self.repo / "scripts" / correct.ENFORCER).write_text(BLOCK_ALL)
        code, rows = self.rows()
        self.assertEqual(code, 1)
        self.assertEqual(rows["branch-first"]["status"], "FAIL")
        self.assertTrue(any(f.startswith("control") or f.startswith("live control")
                            for f in rows["branch-first"]["fails"]), rows["branch-first"]["fails"])

    def test_a_missing_hook_entry_fails_the_row(self) -> None:
        (self.repo / ".claude" / "settings.json").write_text('{"hooks": {}}')
        code, rows = self.rows()
        self.assertEqual(code, 1)
        self.assertTrue(any("not registered" in f for f in rows["branch-first"]["fails"]), rows["branch-first"]["fails"])

    def test_a_hook_entry_that_only_names_the_enforcer_fails_the_row(self) -> None:
        settings = {"hooks": {"PreToolUse": [dict(correct.HOOK_GROUP, hooks=[
            {"type": "command", "command": f"echo {correct.HOOK_COMMAND}", "timeout": 10}])]}}
        (self.repo / ".claude" / "settings.json").write_text(json.dumps(settings))
        code, rows = self.rows()
        self.assertEqual(code, 1)
        self.assertEqual(rows["branch-first"]["status"], "FAIL")
        # The reason is the registration, not only the behaviour of `echo`.
        self.assertTrue(any("not registered" in f for f in rows["branch-first"]["fails"]), rows["branch-first"]["fails"])

    def test_an_emptied_registry_is_not_a_pass(self) -> None:
        (self.repo / ".control" / "rules.yaml").write_text("version: 1\nrules: []\n")
        proc = self.run_correct("check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no rules", proc.stderr)


class Wrapper(CorrectCase):
    def test_check_outside_a_checkout_exits_2_and_says_what_to_pass(self) -> None:
        proc = self.run_correct("check", cwd=self.tmp)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--root DIR", proc.stderr)

    def test_root_can_be_named_by_flag_or_by_environment(self) -> None:
        self.init()
        by_flag = self.run_correct("check", "--root", str(self.repo), "--only", "branch-first", cwd=self.tmp)
        self.assertEqual(by_flag.returncode, 0, by_flag.stdout + by_flag.stderr)
        by_equals = self.run_correct("check", f"--root={self.repo}", "--only", "branch-first", cwd=self.tmp)
        self.assertEqual(by_equals.returncode, 0, by_equals.stdout + by_equals.stderr)
        by_env = self.run_correct("check", "--only", "branch-first", cwd=self.tmp,
                                  env=dict(self.env, RULES_CHECK_ROOT=str(self.repo)))
        self.assertEqual(by_env.returncode, 0, by_env.stdout + by_env.stderr)

    def test_the_runner_status_comes_through_unchanged(self) -> None:
        self.init()
        unknown = self.run_correct("check", "--only", "no-such-rule")
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("unknown rule id", unknown.stderr)

    def test_check_before_init_exits_2_and_says_to_run_init(self) -> None:
        proc = self.run_correct("check")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("there is no registry at", proc.stderr)
        self.assertIn("run init first", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_an_empty_root_is_refused_and_does_not_fall_back(self) -> None:
        self.init()
        for args in (("--root", ""), ("--root=",)):
            proc = self.run_correct("check", *args, env=dict(self.env, RULES_CHECK_ROOT=str(self.repo)))
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("empty value", proc.stderr)

    def registry_text(self, version_line: str) -> str:
        """The installed registry with its `version: 1` line replaced (or removed, for "")."""
        text = (self.repo / ".control" / "rules.yaml").read_text()
        self.assertEqual(text.count("\nversion: 1\n"), 1)
        return text.replace("\nversion: 1\n", f"\n{version_line}")

    def test_a_registry_of_another_version_is_refused_not_replayed(self) -> None:
        self.init()
        registry = self.repo / ".control" / "rules.yaml"
        for line in ("version: 2\n", "version: true\n", ""):  # a later version, a wrong type, none
            registry.write_text(self.registry_text(line))
            for command in ("check", "init"):
                proc = self.run_correct(command)
                self.assertEqual(proc.returncode, 2, (line, command, proc.stdout + proc.stderr))
                self.assertIn("this copy of the skill replays version 1", proc.stderr)
                self.assertNotIn("PASS", proc.stdout)
            registry.write_bytes((SKILL / "assets" / "templates" / "rules.yaml").read_bytes())

    def test_the_registry_named_with_a_flag_is_the_one_whose_version_is_checked(self) -> None:
        self.init()
        other = self.tmp / "other.yaml"
        other.write_text(self.registry_text("version: 2\n"))
        for args in (("--registry", str(other)), (f"--registry={other}",)):
            proc = self.run_correct("check", *args)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("other.yaml says `version: 2`", proc.stderr)
        absent = self.run_correct("check", "--registry", str(self.tmp / "absent.yaml"))
        self.assertEqual(absent.returncode, 2, absent.stdout + absent.stderr)
        self.assertIn("there is no registry at", absent.stderr)

    def test_canary_runs_the_canary_not_the_runner(self) -> None:
        self.init()
        proc = self.run_correct("canary", "--help")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("usage: rules_canary.py", proc.stdout)

    def test_an_unknown_command_exits_2(self) -> None:
        proc = self.run_correct("chek")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("init, check or canary", proc.stderr)

    def test_a_root_that_is_not_a_directory_exits_2(self) -> None:
        proc = self.run_correct("check", "--root", str(self.tmp / "absent"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("is not a directory", proc.stderr)


class VendoredCheckCanFail(unittest.TestCase):
    """tests/vendored.py is a gate CI runs. Each case tampers with a COPY of the shipped files
    and requires the gate to go red; a gate never seen failing proves nothing."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.copy = Path(self._tmp.name).resolve() / "skill"
        shutil.copytree(SKILL / "scripts", self.copy / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        (self.copy / "tests").mkdir()
        shutil.copy(HERE / "vendored.py", self.copy / "tests" / "vendored.py")

    def gate(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-I", str(self.copy / "tests" / "vendored.py"), *args],
                              capture_output=True, text=True, timeout=120)

    def test_the_untouched_copy_passes(self) -> None:
        proc = self.gate()
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))

    def test_a_changed_file_fails_and_is_named(self) -> None:
        with (self.copy / "scripts" / "rules_fixtures.py").open("a") as handle:
            handle.write("# edited\n")
        proc = self.gate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("rules_fixtures.py: differs from the hash in VENDORED.json", proc.stderr)
        self.assertNotIn("rules_canary.py", proc.stderr)

    def test_a_missing_file_fails_and_is_named(self) -> None:
        (self.copy / "scripts" / "rules_case_data.py").unlink()
        proc = self.gate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("rules_case_data.py: recorded in VENDORED.json and not shipped", proc.stderr)

    def test_write_records_the_new_hash_and_the_unexplained_difference_still_fails(self) -> None:
        manifest = self.copy / "scripts" / "VENDORED.json"
        source_before = json.loads(manifest.read_text())["files"]["rules_fixtures.py"]["source_sha256"]
        with (self.copy / "scripts" / "rules_fixtures.py").open("a") as handle:
            handle.write("# edited\n")
        self.assertEqual(self.gate("--write").returncode, 0)
        entry = json.loads(manifest.read_text())["files"]["rules_fixtures.py"]
        self.assertEqual(entry["source_sha256"], source_before)  # --write never touches the source hash
        self.assertNotEqual(entry["shipped_sha256"], source_before)
        proc = self.gate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn('rules_fixtures.py: differs from its source and VENDORED.json "changes" does not say how',
                      proc.stderr)
        data = json.loads(manifest.read_text())
        data["changes"].append({"file": "rules_fixtures.py", "what": "a comment added, for this test"})
        manifest.write_text(json.dumps(data))
        self.assertEqual(self.gate().returncode, 0)

    def test_an_unknown_argument_exits_2(self) -> None:
        self.assertEqual(self.gate("--wrte").returncode, 2)


class Shipped(unittest.TestCase):
    def test_the_vendored_files_are_the_recorded_ones(self) -> None:
        self.assertEqual(vendored.mismatches(), [])

    def test_the_manifest_covers_every_runner_file_init_or_check_uses(self) -> None:
        recorded = set(json.loads(vendored.MANIFEST.read_text())["files"])
        self.assertEqual(recorded, {"rules_check.py", "rules_canary.py", *correct.SCRIPT_FILES})
        self.assertEqual(len(correct.SCRIPT_FILES), 4)  # SKILL.md says "the four files under scripts/"
        self.assertIn("the four files under\n  `scripts/`", (SKILL / "SKILL.md").read_text())

    def test_the_starter_row_and_the_hook_entry_agree(self) -> None:
        data = yaml.safe_load((SKILL / "assets" / "templates" / "rules.yaml").read_text())
        (row,) = data["rules"]
        self.assertEqual(row["enforcer"]["path"], f"scripts/{correct.ENFORCER}")
        self.assertEqual(row["enforcer"]["registered"]["event"], "PreToolUse")
        self.assertEqual("|".join(row["enforcer"]["registered"]["tools"]), correct.HOOK_GROUP["matcher"])
        # SKILL.md states these counts; a changed template must change the sentence too.
        self.assertEqual((len(row["proofs"]), len(row["controls"]), len(row["known_misses"])), (10, 3, 2))
        self.assertIn("ten proofs, three\n  controls and two recorded known misses", (SKILL / "SKILL.md").read_text())
        self.assertTrue(row["canary"]["none"] and row["canary"]["ticket"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
