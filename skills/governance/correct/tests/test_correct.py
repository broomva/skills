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

import contextlib
import copy
import errno
import hashlib
import io
import json
import os
import shutil
import site
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
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


def keep_temporary_names(name: object, *args: object, _real: object = os.unlink, **kwargs: object) -> None:
    """os.unlink, for a folder where the registry's temporary file cannot be removed."""
    if os.path.basename(os.fspath(name)).startswith(".rules.yaml."):
        raise PermissionError(errno.EACCES, "Permission denied")
    _real(name, *args, **kwargs)


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

    def test_dry_run_on_a_registry_of_another_version_stops_where_the_real_run_would(self) -> None:
        (self.repo / ".control").mkdir()
        (self.repo / ".control" / "rules.yaml").write_text("version: 2\nrules: []\n")
        proc = self.run_correct("init", "--dry-run")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("this copy of the skill replays version 1", proc.stderr)

    def test_dry_run_on_an_existing_registry_is_the_same_run_as_the_real_one(self) -> None:
        """Nothing is written either way, so the two cannot answer differently."""
        self.init()
        ok = self.run_correct("init", "--dry-run")
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertIn("PASS     hook         branch-first", ok.stdout)
        (self.repo / ".claude" / "settings.json").write_text('{"hooks": {"PreToolUse": []}}')
        before = tree(self.repo)
        dry, real = self.run_correct("init", "--dry-run"), self.run_correct("init")
        self.assertEqual((dry.returncode, real.returncode), (1, 1), dry.stdout + real.stdout)
        self.assertIn("not registered", dry.stdout)
        self.assertEqual(tree(self.repo), before)

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
        self.refused_with_nothing_written("in a form other than the entry init writes")

    def test_the_enforcer_entry_on_fewer_tools_is_refused_not_kept(self) -> None:
        self.settings({"hooks": {"PreToolUse": [dict(correct.HOOK_GROUP, matcher="Write")]}})
        self.refused_with_nothing_written("in a form other than the entry init writes")

    def test_inits_own_group_beside_another_mention_is_still_refused(self) -> None:
        self.settings({"hooks": {"PreToolUse": [correct.HOOK_GROUP, dict(correct.HOOK_GROUP, matcher="Bash")]}})
        self.refused_with_nothing_written("in a form other than the entry init writes")

    def test_an_entry_like_inits_but_not_equal_to_it_is_refused_not_kept(self) -> None:
        """init keeps only the group it writes, value for value. Each of these was read as
        "already there" by an earlier version and then failed the replay as not registered."""
        ours = correct.HOOK_GROUP["hooks"][0]
        for entry in (dict(ours, type="prompt"), dict(ours, **{"async": True}), dict(ours, timeout=30)):
            self.settings({"hooks": {"PreToolUse": [dict(correct.HOOK_GROUP, hooks=[entry])]}})
            self.refused_with_nothing_written("in a form other than the entry init writes")
        self.settings({"hooks": {"PreToolUse": [dict(correct.HOOK_GROUP, matcher="Edit|Write|MultiEdit|NotebookEdit")]}})
        self.refused_with_nothing_written("in a form other than the entry init writes")

    def test_an_unreadable_file_where_a_script_goes_is_refused(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root reads any file")
        (self.repo / "scripts").mkdir()
        hook = self.repo / "scripts" / correct.ENFORCER
        hook.write_text("x")
        hook.chmod(0o000)
        self.addCleanup(hook.chmod, 0o644)
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("could not read the repository's current state", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertFalse((self.repo / ".control").exists())

    def test_a_top_directory_that_cannot_be_written_is_refused_before_scripts_are_written(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root writes into any directory")
        (self.repo / "scripts").mkdir()  # writable, so the scripts alone could land
        self.repo.chmod(0o555)
        self.addCleanup(self.repo.chmod, 0o755)
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("the repository's top directory is not writable", proc.stderr)
        self.assertEqual(list((self.repo / "scripts").iterdir()), [])

    def test_a_read_only_top_directory_is_fine_when_nothing_is_created_in_it(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root writes into any directory")
        for name in ("scripts", ".claude", ".control"):
            (self.repo / name).mkdir()
        self.repo.chmod(0o555)
        self.addCleanup(self.repo.chmod, 0o755)
        self.init()

    def test_a_read_only_settings_file_is_refused_and_left_as_it_is(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root writes any file")
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

    def hide_yaml(self) -> None:
        """Make the PyYAML probe fail wherever PyYAML is installed (user site, system, a venv)."""
        self.addCleanup(setattr, correct, "YAML_PROBE", correct.YAML_PROBE)
        correct.YAML_PROBE = "import a_module_that_does_not_exist"

    def test_without_pyyaml_init_writes_nothing_and_says_what_to_install(self) -> None:
        self.hide_yaml()
        with self.assertRaises(correct.Refused) as caught:
            correct.init(self.repo, [])
        self.assertIn("PyYAML is not importable", str(caught.exception))
        self.assertIn("pip install --user pyyaml", str(caught.exception))
        self.assertEqual(tree(self.repo), {})

    def test_without_pyyaml_a_dry_run_stops_where_the_real_run_would(self) -> None:
        self.hide_yaml()
        with self.assertRaises(correct.Refused):
            correct.init(self.repo, ["--dry-run"])

    def test_without_pyyaml_check_and_canary_exit_2(self) -> None:
        self.init()
        self.hide_yaml()
        for argv in (["check", "--root", str(self.repo)], ["canary", "--root", str(self.repo), "run"]):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(correct.main(argv), 2)
            self.assertIn("PyYAML is not importable", err.getvalue())

    def test_the_pyyaml_probe_finds_pyyaml_the_way_the_runner_does(self) -> None:
        correct.need_yaml()  # raises when the real probe fails on a machine where the runner works

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
        self.assertIn("correct init: done.", proc.stdout)
        self.assertNotIn("back out", proc.stdout)  # the success text gives no undo steps (BRO-4212)
        self.assertNotIn("delete the registry", proc.stdout)

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

    def test_a_file_written_as_new_is_created_and_never_replaced(self) -> None:
        """write_file with `new`: a name that is taken is refused, what is there is kept, and no
        temporary file is left beside it."""
        target = self.tmp / "out" / "rules.yaml"
        self.assertIsNone(correct.write_file(target, b"first\n", False, new=True))
        with self.assertRaises(correct.Taken) as caught:
            correct.write_file(target, b"second\n", False, new=True)
        self.assertIsNone(caught.exception.left)
        self.assertEqual(target.read_bytes(), b"first\n")
        self.assertEqual([p.name for p in target.parent.iterdir()], ["rules.yaml"])

    def test_a_new_files_name_is_not_looked_at_before_the_link_or_after_it(self) -> None:
        """Written, taken, or the link refused: write_file asks the filesystem nothing about a
        new file's name but the link itself. Every stat of that name is counted here, so the
        test does not depend on which errors a Python's pathlib lets through."""
        real_stat, real_lstat, real_link = os.stat, os.lstat, os.link
        for outcome in ("written", "taken", "not linked"):
            with self.subTest(outcome=outcome):
                target = self.tmp / outcome.replace(" ", "-") / "rules.yaml"
                target.parent.mkdir()
                if outcome == "taken":
                    target.write_bytes(b"theirs\n")
                looks: list[str] = []

                def counted(real: object, name: str) -> object:
                    def look(path: object, *args: object, **kwargs: object) -> os.stat_result:
                        if isinstance(path, (str, os.PathLike)) and os.fspath(path) == os.fspath(target):
                            looks.append(name)
                        return real(path, *args, **kwargs)
                    return look

                def link(src: object, dst: object) -> None:
                    if outcome == "not linked":
                        raise OSError(errno.EOPNOTSUPP, "Operation not supported")
                    real_link(src, dst)

                with unittest.mock.patch.object(correct.os, "stat", counted(real_stat, "stat")), \
                        unittest.mock.patch.object(correct.os, "lstat", counted(real_lstat, "lstat")), \
                        unittest.mock.patch.object(correct.os, "link", link):
                    try:
                        correct.write_file(target, b"mine\n", False, new=True)
                        answer = "written"
                    except correct.Taken:
                        answer = "taken"
                    except correct.NotLinked:
                        answer = "not linked"
                self.assertEqual(answer, outcome)
                self.assertEqual(looks, [])

    @staticmethod
    def link_then_answer(error: OSError) -> object:
        """os.link, for a filesystem that makes the link and then answers with an error."""
        real = os.link

        def link(src: object, dst: object) -> None:
            real(src, dst)
            raise error
        return link

    def test_a_link_that_was_made_and_answers_with_an_error_is_reported_as_that_error(self) -> None:
        """link(2) can answer with an error for a link it made (its BUGS section: an NFS server
        that could not say so). write_file takes the answer as given and does not look again:
        the file is there, the call reports the error, and the temporary file is removed."""
        target = self.tmp / "out" / "rules.yaml"
        with unittest.mock.patch.object(correct.os, "link", self.link_then_answer(OSError(errno.EIO, "reply lost"))), \
                self.assertRaises(correct.NotLinked) as caught:
            correct.write_file(target, b"mine\n", False, new=True)
        self.assertIn("reply lost", str(caught.exception))
        self.assertIsNone(caught.exception.left)
        self.assertEqual(target.read_bytes(), b"mine\n")
        self.assertEqual([p.name for p in target.parent.iterdir()], ["rules.yaml"])

    def test_a_registry_whose_link_answers_with_an_error_is_refused_and_nothing_is_said_of_what_was_written(self) -> None:
        """init reports the link's error and the files it wrote before. It does not say whether
        the registry was written. Here it was, complete, and the next init finds it."""
        answered, registry = [], self.repo / ".control" / "rules.yaml"
        made = self.link_then_answer(OSError(errno.EIO, "reply lost"))

        def link(src: object, dst: object) -> None:
            answered.append(dst)
            made(src, dst)

        def no_looking(real: object) -> object:
            def look(path: object, *args: object, **kwargs: object) -> os.stat_result:
                if answered and os.fspath(path) == os.fspath(registry):  # the outage that lost the reply goes on
                    raise OSError(errno.EIO, "the name was looked at after the link answered")
                return real(path, *args, **kwargs)
            return look

        with unittest.mock.patch.object(correct.os, "link", link), \
                unittest.mock.patch.object(correct.os, "stat", no_looking(os.stat)), \
                unittest.mock.patch.object(correct.os, "lstat", no_looking(os.lstat)), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(correct.Refused) as caught:
            correct.init(self.repo, [])
        said = str(caught.exception)
        self.assertIn("the link that creates .control/rules.yaml answered with an error ([Errno", said)
        self.assertIn("reply lost). A registry may be at that name all the same: this run did not look. "
                      "Written before it: scripts/branch-first-hook.py, ", said)
        self.assertNotIn("looked at", said)  # the link's own error, and no look at the name after it
        self.assertTrue(said.endswith(" The starter hook and its settings entry are in place."), said)
        for claim in ("no registry", "not written", "wrote", "failed"):
            self.assertNotIn(claim, said)
        self.assertEqual(registry.read_bytes(), (SKILL / "assets" / "templates" / "rules.yaml").read_bytes())
        again = self.run_correct("init")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn(".control/rules.yaml exists, so this repository already has a registry", again.stdout)

    def lose_the_race(self, registry: Path, theirs: bytes, unlink: object = None) -> tuple[int, str, str]:
        """Run init in a repository where another init writes `theirs` at `registry` after this
        one has looked and before it writes its own. `unlink` stands in for os.unlink while
        this run (not the other) writes the registry. Returns (status, stdout, stderr)."""
        real = correct.write_file

        def late(path: Path, content: bytes, executable: bool, new: bool = False) -> str | None:
            if path != registry:
                return real(path, content, executable, new=new)
            real(path, theirs, False, new=True)  # the other init gets there first
            with unittest.mock.patch.object(correct.os, "unlink", unlink or os.unlink):
                return real(path, content, executable, new=new)

        out, err = io.StringIO(), io.StringIO()
        with unittest.mock.patch.object(correct, "write_file", late), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err), unittest.mock.patch.dict(os.environ, self.env):
            status = correct.init(self.repo, [])
        return status, out.getvalue(), err.getvalue()

    def test_an_init_that_loses_the_race_keeps_the_other_registry_and_exits_with_its_replay(self) -> None:
        """Two inits at once. Each looked and saw no registry. One writes it first. The other,
        when it comes to write, finds the name taken: it replaces nothing, says so, and
        replays the one that is there. Here that one does not hold (a gap row with no ticket),
        so the loser exits 1: its status is the replay's, not a success of its own."""
        registry = self.repo / ".control" / "rules.yaml"
        theirs = b"version: 1\nrules:\n- {id: theirs, rule: Theirs., level: gap}\n"
        status, out, err = self.lose_the_race(registry, theirs)
        self.assertEqual(status, 1, out + err)
        self.assertIn("correct init: the link that creates .control/rules.yaml answered that the name is taken. "
                      "What is there is kept. Written before it: scripts/branch-first-hook.py, ", out)
        self.assertNotIn("another init", out)  # what the link answered, and no guess at who took the name
        self.assertEqual(registry.read_bytes(), theirs)
        self.assertEqual([p.name for p in registry.parent.iterdir() if p.name.startswith(".rules")], [])
        self.assertNotIn("temporary file", err)

    def test_a_registry_of_another_version_that_takes_the_name_is_kept_and_not_replayed(self) -> None:
        """The loser treats what took the name as any existing registry: one this copy of the
        skill does not replay, by its version, is refused (exit 2), byte for byte as it was, and the runner is
        never started on it."""
        registry = self.repo / ".control" / "rules.yaml"
        starter = (SKILL / "assets" / "templates" / "rules.yaml").read_bytes()
        theirs = starter.replace(b"\nversion: 1\n", b"\nversion: 99\n")
        self.assertNotEqual(theirs, starter)
        with unittest.mock.patch.object(correct, "run_tool", side_effect=AssertionError("the runner started")), \
                self.assertRaises(correct.Refused) as caught:
            self.lose_the_race(registry, theirs)
        self.assertIn("this copy of the skill replays version 1", str(caught.exception))
        self.assertEqual(registry.read_bytes(), theirs)

    def test_a_name_taken_by_something_that_is_not_a_file_is_refused_by_that_name(self) -> None:
        """A folder, or a link to nothing, at the registry's name is not a registry. The loser
        says the name was taken and what it wrote, then says what it found, at the name it
        found it. It starts no replay and gives no advice."""
        for layout, folder in (("plain", ".control"), ("new", ".broomva")):
            for kind in ("folder", "dangling link"):
                with self.subTest(layout=layout, kind=kind):
                    repo = self.tmp / f"{layout}-{kind.replace(' ', '-')}"
                    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True)
                    if layout == "new":
                        (repo / ".broomva").mkdir()
                    registry = repo / folder / "rules.yaml"
                    real = correct.write_file

                    def late(path: Path, content: bytes, executable: bool, new: bool = False) -> str | None:
                        if path == registry:
                            registry.mkdir() if kind == "folder" else registry.symlink_to(repo / "nowhere")
                        return real(path, content, executable, new=new)

                    out = io.StringIO()
                    with unittest.mock.patch.object(correct, "write_file", late), contextlib.redirect_stdout(out), \
                            unittest.mock.patch.object(correct, "run_tool", side_effect=AssertionError("replayed")), \
                            self.assertRaises(correct.Refused) as caught:
                        correct.init(repo, [])
                    self.assertEqual(str(caught.exception), f"there is no regular file at {folder}/rules.yaml.")
                    self.assertIn(f"correct init: the link that creates {folder}/rules.yaml answered that the name "
                                  "is taken. What is there is kept. Written before it: scripts/branch-first-hook.py, ",
                                  out.getvalue())
                    self.assertNotIn("replay", out.getvalue())
                    self.assertTrue(registry.is_dir() if kind == "folder" else registry.is_symlink())
                    self.assertEqual([p.name for p in registry.parent.iterdir() if p.name.startswith(".rules")], [])

    def test_a_loser_that_cannot_remove_its_temporary_file_still_replays_the_registry_that_is_there(self) -> None:
        """The name is taken, and then the loser's temporary file cannot be removed. That is
        still a name that was taken: the loser says what it left and exits with the replay of
        the registry that is there. A review found the failed removal reported instead, as a
        registry that was not written, with no replay."""
        registry = self.repo / ".control" / "rules.yaml"
        theirs = (SKILL / "assets" / "templates" / "rules.yaml").read_bytes() + b"# written by the other init\n"
        status, out, err = self.lose_the_race(registry, theirs, unlink=keep_temporary_names)
        self.assertEqual(status, 0, out + err)
        self.assertIn("correct init: the link that creates .control/rules.yaml answered that the name is taken", out)
        self.assertIn("replaying the registry", out)
        self.assertEqual(registry.read_bytes(), theirs)
        left = [p.name for p in registry.parent.iterdir() if p.name.startswith(".rules.yaml.")]
        self.assertEqual(len(left), 1)
        self.assertIn(f"correct init: removing this run's temporary file .control/{left[0]} answered with an error.", err)

    def test_the_registry_init_creates_is_the_one_its_plan_writes(self) -> None:
        """With an empty new-style governance folder, init looks for a registry in the old folder
        (where one would be found) and writes it into the new one. The file created, and never
        replaced, is the one written. A review found the looked-at path compared instead, and
        a registry another init had written in the new folder replaced."""
        (self.repo / ".broomva").mkdir()
        registry = self.repo / ".broomva" / "rules.yaml"
        self.assertEqual(correct.plan(self.repo)[0][-1][0], registry)
        self.assertNotEqual(correct.governance_file(self.repo, "rules.yaml"), registry)
        theirs = (SKILL / "assets" / "templates" / "rules.yaml").read_bytes() + b"# written by the other init\n"
        status, out, err = self.lose_the_race(registry, theirs)
        self.assertEqual(status, 0, out + err)
        self.assertIn("correct init: the link that creates .broomva/rules.yaml answered that the name is taken", out)
        self.assertEqual(registry.read_bytes(), theirs)
        self.assertFalse((self.repo / ".control" / "rules.yaml").exists())

    def test_a_name_taken_anywhere_but_the_registry_is_an_ordinary_failed_write(self) -> None:
        """Only the registry is created as new. Any other write that stops on "File exists" (a
        file put where `scripts/` should be, after init planned its writes) is a write that
        failed, and is not called another init's registry."""
        real = correct.write_file

        def in_the_way(path: Path, content: bytes, executable: bool, new: bool = False) -> str | None:
            if path.name == correct.ENFORCER:
                raise FileExistsError(errno.EEXIST, "File exists", str(path.parent))
            return real(path, content, executable, new=new)

        out = io.StringIO()
        with unittest.mock.patch.object(correct, "write_file", in_the_way), contextlib.redirect_stdout(out), \
                self.assertRaises(correct.Refused) as caught:
            correct.init(self.repo, [])
        self.assertIn("could not write scripts/" + correct.ENFORCER, str(caught.exception))
        self.assertIn("Written before it: nothing", str(caught.exception))
        self.assertNotIn("answered that the name is taken", out.getvalue())

    def test_a_registry_whose_temporary_name_cannot_be_removed_is_written_and_said(self) -> None:
        """Once the link is made the registry is there. If the temporary name cannot then be
        removed, init says the registry is written and names what is left; it does not report
        a registry that was not written. A review found the opposite message."""
        out, err = io.StringIO(), io.StringIO()
        with unittest.mock.patch.object(correct.os, "unlink", keep_temporary_names), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err), unittest.mock.patch.dict(os.environ, self.env):
            status = correct.init(self.repo, [])
        self.assertEqual(status, 0, out.getvalue() + err.getvalue())
        registry = self.repo / ".control" / "rules.yaml"
        self.assertEqual(registry.read_bytes(), (SKILL / "assets" / "templates" / "rules.yaml").read_bytes())
        left = [p.name for p in registry.parent.iterdir() if p.name.startswith(".rules.yaml.")]
        self.assertEqual(len(left), 1)
        self.assertIn(f"correct init: removing this run's temporary file .control/{left[0]} answered with an error.",
                      err.getvalue())

    def test_a_temporary_file_that_is_already_gone_is_not_called_left(self) -> None:
        """Whatever the link answered: written, taken, or refused."""
        real_unlink, real_link = os.unlink, os.link

        def gone_first(name: object, *args: object, **kwargs: object) -> None:
            real_unlink(name, *args, **kwargs)
            real_unlink(name, *args, **kwargs)  # FileNotFoundError: something else removed it first

        for answer in ("written", "taken", "not linked"):
            with self.subTest(answer=answer):
                target = self.tmp / f"gone-{answer.replace(' ', '-')}" / "rules.yaml"
                target.parent.mkdir()
                if answer == "taken":
                    target.write_bytes(b"theirs\n")

                def link(src: object, dst: object) -> None:
                    if answer == "not linked":
                        raise OSError(errno.EOPNOTSUPP, "Operation not supported")
                    real_link(src, dst)

                with unittest.mock.patch.object(correct.os, "unlink", gone_first), \
                        unittest.mock.patch.object(correct.os, "link", link):
                    try:
                        left = correct.write_file(target, b"first\n", False, new=True)
                    except correct.NotCreated as why:
                        left = why.left
                self.assertIsNone(left)
                self.assertEqual([p.name for p in target.parent.iterdir() if p.name.startswith(".rules")], [])

    def test_the_registry_is_whole_at_the_instant_it_is_linked(self) -> None:
        """The reason for the link: no reader ever finds the registry short. At the moment the
        name appears, the file already holds every byte and its final mode. A review found the
        suite passing with the write moved after the link, when a second init read nothing.
        The template is larger than a write buffer and goes to the file at once; the short
        content stays in the buffer until the file is closed."""
        real, seen = os.link, []

        def link(src: object, dst: object) -> None:
            real(src, dst)
            seen.append((Path(dst).read_bytes(), os.stat(dst).st_mode & 0o777))

        umask = os.umask(0o022)
        self.addCleanup(os.umask, umask)
        for folder, content in (("template", (SKILL / "assets" / "templates" / "rules.yaml").read_bytes()),
                                ("short", b"version: 1\nrules: []\n")):
            with self.subTest(content=folder):
                target = self.tmp / folder / "rules.yaml"
                seen.clear()
                with unittest.mock.patch.object(correct.os, "link", link):
                    self.assertIsNone(correct.write_file(target, content, False, new=True))
                self.assertEqual(seen, [(content, 0o644)])
                self.assertEqual((target.read_bytes(), target.stat().st_mode & 0o777), (content, 0o644))

    def test_where_the_filesystem_cannot_link_no_registry_is_written(self) -> None:
        """No fallback to replacing: a registry init cannot create safely is not created. The
        refusal carries the link's error, what was written before, and what is in place."""
        def no_links(_src: str, _dst: object) -> None:
            raise OSError(errno.EOPNOTSUPP, "Operation not supported")

        self.addCleanup(setattr, correct.os, "link", os.link)
        correct.os.link = no_links
        with self.assertRaises(correct.Refused) as caught:
            correct.init(self.repo, [])
        said = str(caught.exception)
        self.assertIn("the link that creates .control/rules.yaml answered with an error ([Errno", said)
        self.assertIn("Operation not supported", said)
        self.assertIn("this run did not look. Written before it: scripts/branch-first-hook.py", said)
        # What this run did and what is in place; no steps, and no word on what the repository holds.
        self.assertTrue(said.endswith(" The starter hook and its settings entry are in place."), said)
        self.assertTrue((self.repo / "scripts" / correct.ENFORCER).is_file())
        self.assertIn(correct.ENFORCER, (self.repo / ".claude" / "settings.json").read_text())
        self.assertEqual([p.name for p in (self.repo / ".control").iterdir() if "rules" in p.name], [])

    def test_a_refused_link_whose_temporary_file_cannot_be_removed_says_both(self) -> None:
        def no_links(_src: str, _dst: object) -> None:
            raise OSError(errno.EOPNOTSUPP, "Operation not supported")

        err = io.StringIO()
        with unittest.mock.patch.object(correct.os, "link", no_links), \
                unittest.mock.patch.object(correct.os, "unlink", keep_temporary_names), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err), \
                self.assertRaises(correct.Refused) as caught:
            correct.init(self.repo, [])
        self.assertIn("the link that creates .control/rules.yaml answered with an error", str(caught.exception))
        left = [p.name for p in (self.repo / ".control").iterdir() if "rules" in p.name]
        self.assertEqual(len(left), 1)
        self.assertTrue(left[0].startswith(".rules.yaml."))
        self.assertIn(f"correct init: removing this run's temporary file .control/{left[0]} answered with an error.",
                      err.getvalue())

    def test_a_refused_link_says_nothing_about_a_registry_another_init_wrote_meanwhile(self) -> None:
        """This run's link is refused, and by then another init has written the registry. The
        refusal is about this run: it does not say the repository has no registry."""
        registry = self.repo / ".control" / "rules.yaml"
        theirs = (SKILL / "assets" / "templates" / "rules.yaml").read_bytes() + b"# written by the other init\n"

        def refused(_src: object, _dst: object) -> None:
            registry.write_bytes(theirs)  # the other init, on a mount that links
            raise PermissionError(errno.EPERM, "Operation not permitted")

        with unittest.mock.patch.object(correct.os, "link", refused), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(correct.Refused) as caught:
            correct.init(self.repo, [])
        said = str(caught.exception)
        self.assertIn("the link that creates .control/rules.yaml answered with an error ([Errno", said)
        self.assertNotIn("no registry", said)
        self.assertEqual(registry.read_bytes(), theirs)

    @unittest.skipIf(os.geteuid() == 0, "a folder with no permissions stops nobody who is root")
    def test_a_name_taken_by_something_that_cannot_be_read_is_a_refusal_not_a_traceback(self) -> None:
        """What took the name is a link into a folder this user may not enter, put there while the
        other files were being written, or at the instant of the link. Either way the link
        answers that the name is taken; asking what is there then raises, and that is a refusal
        that carries the error, after the line that lists what was written. One review found a
        traceback; the next found the first case told as a write that failed, because the name
        was looked at before the link."""
        for when in ("before the registry's write begins", "at the link"):
            with self.subTest(planted=when):
                tag = when.split()[0]
                repo, private = self.tmp / f"repo-{tag}", self.tmp / f"private-{tag}"
                subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True)
                private.mkdir()
                (private / "rules.yaml").write_text("version: 1\nrules: []\n")
                registry = repo / ".control" / "rules.yaml"
                real_link, real_write = os.link, correct.write_file

                def plant() -> None:
                    registry.parent.mkdir(parents=True, exist_ok=True)
                    os.symlink(private / "rules.yaml", registry)
                    private.chmod(0)

                def link(src: object, dst: object) -> None:
                    if when == "at the link":
                        plant()
                    real_link(src, dst)  # FileExistsError: the name is the symbolic link's

                def write(path: Path, content: bytes, executable: bool, new: bool = False) -> str | None:
                    if when != "at the link" and path == registry:
                        plant()
                    return real_write(path, content, executable, new=new)

                self.addCleanup(private.chmod, 0o700)
                out = io.StringIO()
                with unittest.mock.patch.object(correct.os, "link", link), \
                        unittest.mock.patch.object(correct, "write_file", write), contextlib.redirect_stdout(out), \
                        unittest.mock.patch.object(correct, "run_tool", side_effect=AssertionError("replayed")), \
                        self.assertRaises(correct.Refused) as caught:
                    correct.init(repo, [])
                self.assertIn("what is at .control/rules.yaml could not be read ([Errno", str(caught.exception))
                self.assertIn("answered that the name is taken. What is there is kept. Written before it: "
                              "scripts/branch-first-hook.py, ", out.getvalue())
                self.assertTrue(registry.is_symlink())

    def test_a_registry_that_takes_the_name_and_cannot_then_be_read_is_refused_with_the_error(self) -> None:
        """The registry another init wrote is a file, and reading it then fails (a stale handle on
        a network mount). The refusal carries that error, names that file, and no replay starts.
        The file read is the one at the plan's name: there is no second search for a registry,
        which on some Pythons answers "there is none" when a lookup fails. A review found that."""
        for layout, folder in (("plain", ".control"), ("new", ".broomva")):
            with self.subTest(layout=layout):
                self.repo = self.tmp / f"stale-{layout}"
                subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True, capture_output=True)
                if layout == "new":
                    (self.repo / ".broomva").mkdir()
                registry = self.repo / folder / "rules.yaml"
                theirs = (SKILL / "assets" / "templates" / "rules.yaml").read_bytes() + b"# written by the other init\n"
                real = Path.read_text

                def stale(path: Path, *args: object, **kwargs: object) -> str:
                    if path == registry:
                        raise OSError(errno.ESTALE, "Stale file handle")
                    return real(path, *args, **kwargs)

                with unittest.mock.patch.object(Path, "read_text", stale), \
                        unittest.mock.patch.object(correct, "run_tool", side_effect=AssertionError("replayed")), \
                        self.assertRaises(correct.Refused) as caught:
                    self.lose_the_race(registry, theirs)
                said = str(caught.exception)
                self.assertIn(f"{registry} is not readable YAML ([Errno", said)
                self.assertIn("Stale file handle", said)
                self.assertNotIn("there is no registry", said)
                self.assertEqual(registry.read_bytes(), theirs)

    def test_after_a_collision_the_file_at_the_plans_name_is_the_one_read(self) -> None:
        """A second search for the registry can answer "there is none" when a lookup fails (some
        Pythons turn the error into False). init does not search again: it reads the file at the
        name its link found taken. Here every such search would say the file is not there."""
        (self.repo / ".broomva").mkdir()
        registry = self.repo / ".broomva" / "rules.yaml"
        theirs = (SKILL / "assets" / "templates" / "rules.yaml").read_bytes() + b"# written by the other init\n"
        exists, is_file = Path.exists, Path.is_file

        def no_such(real: object) -> object:
            return lambda path, *args, **kwargs: False if path == registry else real(path, *args, **kwargs)

        with unittest.mock.patch.object(Path, "exists", no_such(exists)), \
                unittest.mock.patch.object(Path, "is_file", no_such(is_file)):
            status, out, err = self.lose_the_race(registry, theirs)
        self.assertEqual(status, 0, out + err)
        self.assertIn("the link that creates .broomva/rules.yaml answered that the name is taken", out)
        self.assertIn("replaying the registry", out)
        self.assertEqual(registry.read_bytes(), theirs)

    def test_after_a_collision_the_registry_replayed_is_the_one_at_the_plans_name(self) -> None:
        """The policy file is in the old folder, so the plan writes the registry there. By the
        time of the link a registry is at that name, and another is in the new folder (a
        checkout restoring both). The runner, left to search, would take the new folder's. init
        tells it which file: the one whose name the link found taken. That one does not hold
        here and the other does, so the status says which was replayed. A review found the
        other one replayed, and exit 0."""
        (self.repo / ".control").mkdir()
        (self.repo / ".control" / "policy.yaml").write_text(correct.POLICY)
        registry, other = self.repo / ".control" / "rules.yaml", self.repo / ".broomva" / "rules.yaml"
        self.assertEqual(correct.plan(self.repo)[0][-1][0], registry)
        theirs = b"version: 1\nrules:\n- {id: theirs, rule: Theirs., level: gap}\n"
        real = correct.write_file

        def late(path: Path, content: bytes, executable: bool, new: bool = False) -> str | None:
            if path == registry:
                registry.write_bytes(theirs)
                other.parent.mkdir()
                other.write_bytes((SKILL / "assets" / "templates" / "rules.yaml").read_bytes())
            return real(path, content, executable, new=new)

        out, err = io.StringIO(), io.StringIO()
        with unittest.mock.patch.object(correct, "write_file", late), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err), unittest.mock.patch.dict(os.environ, self.env):
            status = correct.init(self.repo, [])
        self.assertEqual(status, 1, out.getvalue() + err.getvalue())
        self.assertIn("the link that creates .control/rules.yaml answered that the name is taken", out.getvalue())
        self.assertIn(f"\ncorrect init: replaying the registry at {registry}\n", out.getvalue())
        self.assertEqual(registry.read_bytes(), theirs)
        self.assertEqual(self.run_correct("check", "--registry", str(registry)).returncode, 1)
        self.assertEqual(self.run_correct("check", "--registry", str(other)).returncode, 0)

    def test_a_link_that_was_made_and_answers_that_the_name_is_taken_is_replayed_as_a_registry_that_was_there(self) -> None:
        """A retried link request can find its own first attempt and answer "name taken". init
        takes the answer as given: it says the name was taken, keeps what is there (its own
        registry), replays it, and exits with the replay's status. SKILL.md says so."""
        out = io.StringIO()
        with unittest.mock.patch.object(correct.os, "link", self.link_then_answer(FileExistsError(errno.EEXIST, "File exists"))), \
                contextlib.redirect_stdout(out), unittest.mock.patch.dict(os.environ, self.env):
            status = correct.init(self.repo, [])
        self.assertEqual(status, 0, out.getvalue())
        self.assertIn("the link that creates .control/rules.yaml answered that the name is taken", out.getvalue())
        self.assertIn("replaying the registry", out.getvalue())
        registry = self.repo / ".control" / "rules.yaml"
        self.assertEqual(registry.read_bytes(), (SKILL / "assets" / "templates" / "rules.yaml").read_bytes())
        self.assertEqual([p.name for p in registry.parent.iterdir() if p.name.startswith(".rules")], [])

    def test_a_link_at_the_registrys_name_to_the_temporary_file_is_a_name_taken(self) -> None:
        """A symbolic link at the registry's name takes the name, whatever it points at: here, at
        this run's own temporary file. The link answers that the name is taken, and it is kept."""
        target = self.tmp / "out" / "rules.yaml"
        real = os.link

        def planted(src: object, dst: object) -> None:
            os.symlink(src, dst)
            real(src, dst)  # FileExistsError: the name is the symbolic link's

        with unittest.mock.patch.object(correct.os, "link", planted), self.assertRaises(correct.Taken):
            correct.write_file(target, b"mine\n", False, new=True)
        self.assertTrue(target.is_symlink())

    def test_a_registry_write_that_fails_before_the_link_is_an_ordinary_failed_write(self) -> None:
        """A full disk while the registry's temporary file is made is not a refused link, and is
        not called one: it gets the message any failed write gets."""
        real = tempfile.mkstemp

        def full(*args: object, **kwargs: object) -> tuple[int, str]:
            if str(kwargs.get("prefix", "")).startswith(".rules.yaml."):
                raise OSError(errno.ENOSPC, "No space left on device")
            return real(*args, **kwargs)

        with unittest.mock.patch.object(correct.tempfile, "mkstemp", full), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(correct.Refused) as caught:
            correct.init(self.repo, [])
        said = str(caught.exception)
        self.assertIn("could not write .control/rules.yaml ([Errno", said)
        self.assertIn("No space left on device", said)
        self.assertIn("The registry is written last and was not written", said)
        self.assertNotIn("the link that creates", said)
        self.assertEqual([p.name for p in (self.repo / ".control").iterdir() if "rules" in p.name], [])

    def test_a_write_that_fails_midway_leaves_the_repository_not_set_up(self) -> None:
        real, calls = correct.write_file, []

        def failing(path: Path, content: bytes, executable: bool, new: bool = False) -> None:
            calls.append(path)
            if len(calls) == 3:
                raise OSError("disk full")
            real(path, content, executable, new=new)

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
        other_name = self.tmp / "dir" / "the-old-file"
        os.link(target, other_name)  # a second name for the file as it was
        correct.write_file(target, b"two", True)
        self.assertEqual(target.read_bytes(), b"two")
        self.assertTrue(os.access(target, os.X_OK))
        # Replaced, not rewritten: the old file is untouched under its other name. A write in
        # place would have changed both, and an interrupted one would have left neither whole.
        self.assertEqual(other_name.read_bytes(), b"one")
        self.assertFalse(os.access(other_name, os.X_OK))
        self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ["settings.json", "the-old-file"])

    def test_a_private_hook_stays_private_when_it_is_made_executable(self) -> None:
        (self.repo / "scripts").mkdir()
        hook = self.repo / "scripts" / correct.ENFORCER
        hook.write_bytes((SKILL / "scripts" / correct.ENFORCER).read_bytes())
        hook.chmod(0o600)
        self.init()
        self.assertEqual(hook.stat().st_mode & 0o777, 0o700)

    def test_a_directory_where_a_file_goes_is_refused(self) -> None:
        (self.repo / ".claude" / "settings.json").mkdir(parents=True)
        self.refused_with_nothing_written(".claude/settings.json exists and is not a regular file")

    def test_the_registry_goes_beside_an_existing_policy_file(self) -> None:
        (self.repo / ".broomva").mkdir()  # the directory a new registry would otherwise go to
        (self.repo / ".control").mkdir()
        (self.repo / ".control" / "policy.yaml").write_text("gates:\n  hard: []\n")
        self.init()
        self.assertTrue((self.repo / ".control" / "rules.yaml").is_file())
        self.assertEqual(list((self.repo / ".broomva").iterdir()), [])

    def test_a_replaced_file_keeps_its_permissions(self) -> None:
        (self.repo / ".claude").mkdir()
        path = self.repo / ".claude" / "settings.json"
        path.write_text("{}")
        path.chmod(0o600)
        self.init()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertIn("branch-first-hook.py", path.read_text())
        umask = os.umask(0)
        os.umask(umask)
        self.assertEqual((self.repo / ".control" / "rules.yaml").stat().st_mode & 0o777, 0o666 & ~umask)  # a new file

    def test_a_policy_path_that_is_a_directory_is_refused(self) -> None:
        (self.repo / ".control" / "policy.yaml").mkdir(parents=True)
        self.refused_with_nothing_written(".control/policy.yaml exists and is not a regular file")

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

    def test_a_new_file_gets_what_the_callers_umask_allows(self) -> None:
        old = os.umask(0o077)
        self.addCleanup(os.umask, old)
        correct.write_file(self.tmp / "private" / "data", b"x", False)
        correct.write_file(self.tmp / "private" / "hook", b"x", True)
        self.assertEqual((self.tmp / "private" / "data").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.tmp / "private" / "hook").stat().st_mode & 0o777, 0o700)
        os.umask(0o022)
        correct.write_file(self.tmp / "usual" / "data", b"x", False)
        correct.write_file(self.tmp / "usual" / "hook", b"x", True)
        self.assertEqual((self.tmp / "usual" / "data").stat().st_mode & 0o777, 0o644)
        self.assertEqual((self.tmp / "usual" / "hook").stat().st_mode & 0o777, 0o755)

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

    def test_existing_settings_keep_their_own_characters(self) -> None:
        self.settings({"_note": "révisé — 設定", "hooks": {}})
        self.init()
        text = (self.repo / ".claude" / "settings.json").read_text(encoding="utf-8")
        self.assertIn("révisé — 設定", text)
        self.assertNotIn("\\u", text)

    def test_a_settings_value_with_no_utf8_form_stays_escaped(self) -> None:
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.json").write_text('{"example": "\\ud800", "note": "caf\\u00e9"}')
        self.init()
        text = (self.repo / ".claude" / "settings.json").read_text(encoding="utf-8")
        self.assertIn('"\\ud800"', text)
        self.assertEqual(json.loads(text)["note"], "café")
        self.assertTrue(text.startswith('{\n  "example"') and text.endswith("}\n"), text[:40])  # the usual layout

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
        # What happened, and no repair: the cause of a failed first replay is not init's to guess
        # (a review found "add a row for each" printed for a policy file with no `gates.hard`).
        self.assertTrue(proc.stderr.endswith(
            "correct init: the files are written, and the replay exits 1; its output is above.\n"), proc.stderr)
        self.assertNotIn("add a row", proc.stderr)
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


GATE = """#!/usr/bin/env python3
import json, sys
event = json.load(sys.stdin)
if event.get("tool_name") == "Bash" and "BAD" in event.get("tool_input", {}).get("command", ""):
    print("Gate X: BAD is blocked; run GOOD", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
"""
PACK = {
    "pack": "demo", "registry_version": 1,
    "hooks_not_rules": {"notify.sh": "Stop notification; always exits 0"},
    "rules": [{
        "id": "no-bad", "rule": "Never run BAD.", "source": "the demo tool's gate", "level": "hook",
        "runs_in": ["harness"],
        "enforcer": {"path": "scripts/gate.py",
                     "registered": {"event": "PreToolUse", "tools": ["Bash"], "scope": "project"}},
        "proofs": [{"from": "constructed", "event": {"tool_name": "Bash", "tool_input": {"command": "run BAD now"}},
                    "expect_reason": "Gate X"}],
        "controls": [{"why": "the allowed command",
                      "event": {"tool_name": "Bash", "tool_input": {"command": "run GOOD now"}}}],
        "canary": {"none": "a test fixture", "ticket": "T-1"},
    }],
}
LATER = {"pack": "later", "registry_version": 1, "rules": [{
    "id": "later-gap", "rule": "Prove the later thing.", "source": "a test", "level": "gap",
    "ticket": "T-2", "target": {"level": "hook", "mechanism": "a replay"}}]}


class Packs(CorrectCase):
    """A pack is the rows that prove hooks ANOTHER tool installed. The repository here already
    has such a tool's hooks (a gate on Bash, and a Stop hook that enforces nothing)."""

    def setUp(self) -> None:
        super().setUp()
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "gate.py").write_text(GATE)
        notify = self.repo / "scripts" / "notify.sh"
        notify.write_text("#!/bin/sh\nexit 0\n")
        notify.chmod(0o755)
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.json").write_text(json.dumps({"hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [
                {"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/scripts/gate.py"'}]}],
            "Stop": [{"hooks": [{"type": "command", "command": '"$CLAUDE_PROJECT_DIR"/scripts/notify.sh'}]}]}}))

    def pack(self, data: object = PACK, name: str = "pack.yaml") -> Path:
        path = self.tmp / name
        path.write_text(data if isinstance(data, str) else yaml.safe_dump(data, sort_keys=False))
        return path

    def test_without_the_pack_the_other_tools_hooks_have_no_row(self) -> None:
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("gate.py (PreToolUse, settings.json) is owned by no row", proc.stdout)
        self.assertIn("notify.sh (Stop, settings.json) is owned by no row", proc.stdout)

    def test_with_the_pack_its_rows_are_in_the_registry_and_replay(self) -> None:
        proc = self.run_correct("init", f"--pack={self.pack()}")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("pack   demo: 1 row(s)", proc.stdout)
        code, rows = self.rows()
        self.assertEqual(code, 0, rows)
        self.assertEqual({k: v["status"] for k, v in rows.items()},
                         {"branch-first": "PASS", "no-bad": "PASS", "registry-completeness": "PASS"})
        written = (self.repo / ".control" / "rules.yaml").read_bytes()
        starter = (SKILL / "assets" / "templates" / "rules.yaml").read_bytes()
        self.assertTrue(written.startswith(starter))  # the starter and its header, byte for byte
        self.assertIn(b"# Rows from the pack `demo` (pack.yaml)", written)
        self.assertEqual(yaml.safe_load(written)["hooks_not_rules"], PACK["hooks_not_rules"])

    def test_a_packs_rows_are_replayed_not_only_recorded(self) -> None:
        self.assertEqual(self.run_correct("init", "--pack", str(self.pack())).returncode, 0)
        (self.repo / "scripts" / "gate.py").write_text(ALLOW_ALL)
        code, rows = self.rows()
        self.assertEqual(code, 1)
        self.assertEqual(rows["no-bad"]["status"], "FAIL")

    def test_two_packs_are_added_in_the_order_given(self) -> None:
        proc = self.run_correct("init", "--pack", str(self.pack()), "--pack", str(self.pack(LATER, "later.yaml")))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = yaml.safe_load((self.repo / ".control" / "rules.yaml").read_text())
        self.assertEqual([r["id"] for r in data["rules"]], ["branch-first", "no-bad", "later-gap"])

    def test_a_dry_run_names_the_pack_and_writes_nothing(self) -> None:
        before = tree(self.repo)
        proc = self.run_correct("init", "--dry-run", "--pack", str(self.pack()))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("pack   demo: 1 row(s)", proc.stdout)
        self.assertEqual(tree(self.repo), before)

    def test_a_pack_is_not_added_to_a_registry_that_exists(self) -> None:
        self.assertEqual(self.run_correct("init", "--pack", str(self.pack())).returncode, 0)
        before = tree(self.repo)
        proc = self.run_correct("init", "--pack", str(self.pack(LATER, "later.yaml")))
        self.assertIn("--pack changes nothing here", proc.stdout)
        self.assertEqual(tree(self.repo), before)
        # The replay passes (the first pack owns every hook), and the registry lacks the later
        # pack's row: that is said, and it is not exit 0.
        self.assertIn("pack   later", proc.stdout)
        self.assertIn("is NOT all in this registry", proc.stdout)
        self.assertIn(f"row(s) missing: {LATER['rules'][0]['id']}", proc.stdout)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)

    def test_a_registry_that_holds_the_whole_pack_says_so_and_exits_0(self) -> None:
        self.assertEqual(self.run_correct("init", "--pack", str(self.pack())).returncode, 0)
        for extra in ((), ("--dry-run",)):
            proc = self.run_correct("init", "--pack", str(self.pack()), *extra)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("pack   demo: all 1 row(s) are in this registry", proc.stdout)
            self.assertNotIn("NOT all", proc.stdout)

    def test_a_hook_command_spaced_another_way_is_the_hook_the_registry_holds(self) -> None:
        """A later copy of a pack respaces a hook's command. The registry holds that hook with
        that reason, so nothing of the pack is absent, whichever of the two has the extra
        spaces. A review got exit 3 here: packs were compared with each other on the command's
        words, and with a registry on its text."""
        reason = PACK["hooks_not_rules"]["notify.sh"]
        settings = self.repo / ".claude" / "settings.json"
        settings.write_text(settings.read_text().replace("/scripts/notify.sh", "/scripts/notify.sh --quiet"))
        first = dict(PACK, hooks_not_rules={"notify.sh  --quiet": reason})  # two spaces, in the registry
        self.assertEqual(self.run_correct("init", "--pack", str(self.pack(first))).returncode, 0)
        for spelling in ("notify.sh --quiet", "notify.sh   --quiet"):  # fewer than the registry's, and more
            with self.subTest(spelling=spelling):
                again = dict(PACK, hooks_not_rules={spelling: reason})
                proc = self.run_correct("init", "--pack", str(self.pack(again, "respaced.yaml")))
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("pack   demo: all 1 row(s) are in this registry", proc.stdout)
        other = dict(PACK, hooks_not_rules={"notify.sh --quiet": "another reason"})
        proc = self.run_correct("init", "--pack", str(self.pack(other, "other.yaml")))
        self.assertEqual(proc.returncode, correct.PACK_NOT_WHOLE, proc.stdout + proc.stderr)
        self.assertIn("hooks_not_rules missing or with another reason: notify.sh --quiet", proc.stdout)

    def test_a_registry_with_one_hook_command_under_two_spellings_is_read_the_same_in_either_order(self) -> None:
        """A registry edited by hand: the same command twice, spaced two ways, with two reasons,
        and a key that is no string. The pack's reason is one of the two, so the pack is all
        there, whichever entry comes last. A review got exit 3 or 0 by the order of two keys."""
        reason = PACK["hooks_not_rules"]["notify.sh"]
        settings = self.repo / ".claude" / "settings.json"
        settings.write_text(settings.read_text().replace("/scripts/notify.sh", "/scripts/notify.sh --quiet"))
        first = dict(PACK, hooks_not_rules={"notify.sh --quiet": reason})
        self.assertEqual(self.run_correct("init", "--pack", str(self.pack(first))).returncode, 0)
        registry = correct.governance_file(self.repo, "rules.yaml")
        written = registry.read_text()
        ours, theirs = f"  notify.sh --quiet: {reason}\n", "  notify.sh  --quiet: an older reason\n  123: a key that is no string\n"
        self.assertEqual(written.count(ours), 1, written)
        for order in (ours + theirs, theirs + ours):
            with self.subTest(last=order.splitlines()[-1]):
                registry.write_text(written.replace(ours, order))
                proc = self.run_correct("init", "--pack", str(self.pack(first)))
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("pack   demo: all 1 row(s) are in this registry", proc.stdout)
                self.assertNotIn("Traceback", proc.stderr)
        neither = dict(PACK, hooks_not_rules={"notify.sh --quiet": "a third reason"})
        proc = self.run_correct("init", "--pack", str(self.pack(neither, "neither.yaml")))
        self.assertEqual(proc.returncode, correct.PACK_NOT_WHOLE, proc.stdout + proc.stderr)

    def test_a_registry_whose_row_differs_from_the_pack_is_reported(self) -> None:
        self.assertEqual(self.run_correct("init", "--pack", str(self.pack())).returncode, 0)
        row = PACK["rules"][0]
        newer = dict(PACK, rules=[dict(row, rule=row["rule"] + " (reworded in a later release)")],
                     hooks_not_rules=dict(PACK["hooks_not_rules"], **{"later-hook.sh": "added later"}))
        proc = self.run_correct("init", "--pack", str(self.pack(newer, "newer.yaml")))
        self.assertIn(f"row(s) that differ from the pack: {row['id']}", proc.stdout)
        self.assertIn("hooks_not_rules missing or with another reason: later-hook.sh", proc.stdout)
        self.assertNotIn("row(s) missing", proc.stdout)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)

    def test_a_file_that_is_not_a_pack_is_refused_on_a_registry_that_exists_too(self) -> None:
        self.assertEqual(self.run_correct("init", "--pack", str(self.pack())).returncode, 0)
        self.refused("it is not a mapping", "--pack", str(self.pack("[]", "bad.yaml")))

    def test_a_replay_that_fails_after_the_files_are_written_still_says_main_is_closed(self) -> None:
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertTrue((self.repo / "scripts" / "branch-first-hook.py").is_file())
        # Said before the replay starts, so a caller that stops the replay has already read it.
        notice = proc.stdout.index("an edit on main or master in this repository is refused")
        self.assertLess(notice, proc.stdout.index("replaying the registry"))

    def test_the_first_init_with_a_pack_replays_the_packs_rows_itself(self) -> None:
        """Not a later `check`: init's own exit status is the replay's. The gate here allows
        everything before init runs, so the pack's row must fail inside init."""
        (self.repo / "scripts" / "gate.py").write_text(ALLOW_ALL)
        proc = self.run_correct("init", "--pack", str(self.pack()))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertRegex(proc.stdout, r"FAIL +hook +no-bad")

    def test_a_registry_that_holds_no_list_of_rows_is_refused_not_a_traceback(self) -> None:
        self.assertEqual(self.run_correct("init", "--pack", str(self.pack())).returncode, 0)
        registry = correct.governance_file(self.repo, "rules.yaml")
        registry.write_text("version: 1\nrules: 42\n")
        self.refused("does not read as a registry", "--pack", str(self.pack()))

    def test_a_key_given_twice_in_a_pack_is_refused(self) -> None:
        """PyYAML keeps the last of two `rules:` blocks and drops the first without a word."""
        second = "rules:\n- {id: second, rule: x, level: gap, ticket: T-2, target: {level: hook, mechanism: m}}\n"
        self.refused("the key `rules` is given twice", "--pack",
                     str(self.pack(yaml.safe_dump(PACK, sort_keys=False) + second, "twice.yaml")))

    def test_a_gap_row_whose_target_is_not_a_mapping_is_refused(self) -> None:
        pack = dict(LATER, rules=[dict(LATER["rules"][0], target="hook")])
        self.refused("the row `later-gap` cannot be replayed: `target` is not a mapping", "--pack",
                     str(self.pack(pack, "target.yaml")))

    def test_a_row_the_runner_stops_on_is_reported_as_could_not_run(self) -> None:
        """init checks a stated list of a row's fields and no others. On a wrong kind of value
        in any other the runner stops. That is exit 2 and a diagnostic, not exit 1 and a bare
        traceback, and no repair is prescribed."""
        row = copy.deepcopy(PACK["rules"][0])
        row["proofs"][0]["event"] = "not a mapping"
        proc = self.run_correct("init", "--pack", str(self.pack(dict(PACK, rules=[row]), "deep.yaml")))
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("rules_check.py stopped on an error it does not handle", proc.stderr)
        self.assertIn("The replay did not finish", proc.stderr)
        self.assertNotIn("the files are written, and the replay exits", proc.stderr)
        again = self.run_correct("check")
        self.assertEqual(again.returncode, 2, again.stdout + again.stderr)
        self.assertIn("this is not a failed row", again.stderr)
        # init on the registry that now exists: the same report, and no advice about failed
        # rows or about deleting the registry after it.
        existing = self.run_correct("init", "--pack", str(self.pack()))
        self.assertEqual(existing.returncode, 2, existing.stdout + existing.stderr)
        self.assertIn("this is not a failed row", existing.stderr)
        self.assertNotIn("delete the registry", existing.stderr)
        self.assertNotIn("so it does not repair one either", existing.stderr)
        self.assertNotIn("delete the registry", proc.stderr)

    def test_only_an_error_the_tool_does_not_handle_is_reported_as_a_stopped_runner(self) -> None:
        """The lines a tool is started through: an unhandled error gets a status of its own; the
        tool's own exit and a reader that closed the pipe end as they did without them."""
        for body, status in (("raise ValueError('a row of the wrong kind')", correct.CRASHED),
                             ("raise SystemExit('the tool refuses this registry')", correct.REFUSED),
                             ("raise BrokenPipeError()", 1), ("raise SystemExit(3)", 3), ("pass", 0)):
            tool = self.tmp / "tool.py"
            tool.write_text(body + "\n")
            proc = subprocess.run([sys.executable, "-I", "-c", correct.RUN_TOOL, str(tool)],
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, status, (body, proc.stderr))

    def test_a_row_that_differs_from_the_pack_only_in_the_kind_of_a_value_differs(self) -> None:
        """False and 0 are equal to Python, and are different YAML and different JSON."""
        held = copy.deepcopy(PACK["rules"][0])
        held["proofs"][0]["event"]["tool_input"]["flag"] = False
        first = self.run_correct("init", "--pack", str(self.pack(dict(PACK, rules=[held]))))
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        asked = copy.deepcopy(held)
        asked["proofs"][0]["event"]["tool_input"]["flag"] = 0
        proc = self.run_correct("init", "--pack", str(self.pack(dict(PACK, rules=[asked]), "zero.yaml")))
        self.assertEqual(proc.returncode, correct.PACK_NOT_WHOLE, proc.stdout + proc.stderr)
        self.assertIn("row(s) that differ from the pack: no-bad", proc.stdout)

    def test_two_packs_whose_rows_share_a_value_are_written_out_and_read_back(self) -> None:
        """PyYAML writes a shared value as an anchor and aliases, and names the first anchor of
        every dump alike: two such packs in one registry did not read back as written."""
        def shares(name: str) -> str:
            return (f"pack: {name}\nregistry_version: 1\nrules:\n"
                    f"- {{id: {name}-one, rule: one, source: a test, level: gap, ticket: T-1, target: &t {{level: hook, mechanism: m}}}}\n"
                    f"- {{id: {name}-two, rule: two, source: a test, level: gap, ticket: T-2, target: *t}}\n")
        proc = self.run_correct("init", "--pack", str(self.pack()), "--pack", str(self.pack(shares("a"), "a.yaml")),
                                "--pack", str(self.pack(shares("b"), "b.yaml")))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        written = (self.repo / ".control" / "rules.yaml").read_text()
        self.assertNotIn("&id", written)
        self.assertNotIn("*id", written)
        self.assertEqual([r["id"] for r in yaml.safe_load(written)["rules"]][-4:], ["a-one", "a-two", "b-one", "b-two"])

    def test_the_notice_says_what_init_did_and_leaves_the_harness_to_the_replay(self) -> None:
        """With hooks disabled in the settings the replay says the hook is not registered. The
        notice before it must not have said that edits are refused from now on."""
        (self.repo / ".claude" / "settings.json").write_text(json.dumps({"disableAllHooks": True}))
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("Where the harness runs it, an edit on main or master in this repository is refused", proc.stdout)
        self.assertNotIn("From now on", proc.stdout)
        self.assertIn("disableAllHooks", proc.stdout)

    def refused(self, needle: str, *args: str) -> None:
        before = tree(self.repo)
        proc = self.run_correct("init", *args)
        self.assertEqual(proc.returncode, 2, (needle, proc.stdout + proc.stderr))
        self.assertIn(needle, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(tree(self.repo), before)

    def test_a_file_that_is_not_a_pack_is_refused_and_nothing_is_written(self) -> None:
        row = PACK["rules"][0]
        for needle, data in (
                ("is not readable YAML", "rules: [unclosed"),
                # A date that is no date: PyYAML raises ValueError building it (the words vary by Python).
                ("pack.yaml is not readable YAML (day", "pack: demo\nregistry_version: 1\nrules: [{id: a, since: 2026-11-31}]\n"),
                ("a pack does not use merge keys", "pack: demo\nregistry_version: 1\n<<: {rules: [{id: a}]}\n"),
                ("the key `1` is not a string", "pack: demo\nregistry_version: 1\nrules: [{id: a, 1: x}]\n"),
                ("`proofs` is not a list of cases", dict(PACK, rules=[dict(row, proofs=None)])),
                ("`target` is not a mapping", dict(PACK, rules=[dict(row, target=None)])),
                ("the row `no-bad` cannot be replayed: `occurrences` is not a list", dict(PACK, rules=[dict(row, occurrences=2)])),
                ("the row `no-bad` cannot be replayed: `hosts` is not a list of host group names",
                 dict(PACK, rules=[dict(row, hosts="mac")])),
                ("it is not a mapping", "[]"),
                ("key(s) a pack does not carry: hosts", dict(PACK, hosts={"mac": ["x"]})),
                # YAML keys of two types: found as a traceback by a review, not by a test.
                ("the key `1` is not a string",
                 "pack: demo\nregistry_version: 1\nrules: [{id: no-bad}]\n1: a\nfoo: b\n"),
                ("does not name itself", {k: v for k, v in PACK.items() if k != "pack"}),
                ("is not a plain name", dict(PACK, pack="demo\nhosts: {mac: [x]}")),
                ("is not a plain name", dict(PACK, pack="-demo")),
                ("`registry_version: 2`", dict(PACK, registry_version=2)),
                ("`registry_version: 1.0`", dict(PACK, registry_version=1.0)),
                ("`registry_version: None`", {k: v for k, v in PACK.items() if k != "registry_version"}),
                ("`rules` is not a list of rows", dict(PACK, rules=[])),
                ("`rules` is not a list of rows", dict(PACK, rules=[dict(row, id="   ")])),
                ("`level` is not a word", dict(PACK, rules=[dict(row, level="")])),
                ("`hooks_not_rules` is not a mapping", dict(PACK, hooks_not_rules={"notify.sh": "   "})),
                ("`rules` is not a list of rows", dict(PACK, rules={"no-bad": row})),
                ("`rules` is not a list of rows", dict(PACK, rules=[{k: v for k, v in row.items() if k != "id"}])),
                ("`hooks_not_rules` is not a mapping", dict(PACK, hooks_not_rules=["notify.sh"])),
                ("`hooks_not_rules` is not a mapping", dict(PACK, hooks_not_rules={"notify.sh": 3})),
                ("`rules` is not a list of rows", dict(PACK, rules=["no-bad"])),
                ("`hooks_not_rules` is not a mapping", dict(PACK, hooks_not_rules={"": "a reason for no script"})),
                ("the key `0` is not a string", "pack: demo\nregistry_version: 1\nrules: []\nhooks_not_rules: {0: a, false: b}\n"),
                # Shapes the runner reads without looking: written, they stop it with a traceback
                # and leave a registry that the next init keeps. Found by a review.
                ("the row `no-bad` cannot be replayed: `enforcer` is not a mapping",
                 dict(PACK, rules=[dict(row, enforcer="scripts/gate.py")])),
                ("the row `no-bad` cannot be replayed: `enforcer.registered` is not a mapping",
                 dict(PACK, rules=[dict(row, enforcer=dict(row["enforcer"], registered="PreToolUse"))])),
                ("the row `no-bad` cannot be replayed: `proofs` is not a list of cases",
                 dict(PACK, rules=[dict(row, proofs={"from": "x"})])),
                ("the row `no-bad` cannot be replayed: `known_misses` is not a list of cases",
                 dict(PACK, rules=[dict(row, known_misses=["ticket pending"])])),
                ("the row `no-bad` cannot be replayed: `controls` is not a list of cases",
                 dict(PACK, rules=[dict(row, controls=["git status"])])),
                ("the row `no-bad` cannot be replayed: `level` is not a word",
                 dict(PACK, rules=[{k: v for k, v in row.items() if k != "level"}])),
                ("the row `later-gap` cannot be replayed: `covers_hooks` is not a list of hook names",
                 dict(LATER, rules=[dict(LATER["rules"][0], covers_hooks="notify.sh")])),
                ("the row id `branch-first` is the id of a row of the starter registry", dict(PACK, rules=[dict(row, id="branch-first")])),
        ):
            self.refused(needle, "--pack", str(self.pack(data)))

    def test_a_registry_row_that_is_no_mapping_does_not_stop_the_comparison(self) -> None:
        """A registry edited by hand holds an entry under `rules:` that is a bare word. Comparing
        a pack with it skips that entry; the runner, which has no schema, then stops on it, and
        that is exit 2 with its diagnostic, not a traceback from the comparison."""
        self.assertEqual(self.run_correct("init", "--pack", str(self.pack())).returncode, 0)
        registry = correct.governance_file(self.repo, "rules.yaml")
        registry.write_text(registry.read_text().replace("\nrules:\n", "\nrules:\n- a bare word\n", 1))
        self.assertIn("a bare word", yaml.safe_load(registry.read_text())["rules"])
        proc = self.run_correct("init", "--pack", str(self.pack()))
        self.assertIn("pack   demo: all 1 row(s) are in this registry", proc.stdout)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("rules_check.py stopped on an error it does not handle", proc.stderr)

    def test_each_condition_of_the_row_shape_check_refuses_a_pack_on_its_own(self) -> None:
        """One pack for each condition `row_shape` tests, so that taking any one of them out is
        noticed. Two reviews each found one that no case reached: `known_misses`, then the kind
        of the entries of `hosts` (YAML reads the unquoted host name `on` as true)."""
        row, gap = PACK["rules"][0], LATER["rules"][0]
        cases = [
            ("`level` is not a word", dict(row, level=3)),
            ("`level` is not a word", dict(row, level="  ")),
            ("`enforcer` is not a mapping", dict(row, enforcer=["scripts/gate.py"])),
            ("`enforcer.registered` is not a mapping", dict(row, enforcer=dict(row["enforcer"], registered=["PreToolUse"]))),
            *[(f"`{key}` is not a list of cases", dict(row, **{key: value}))
              for key in ("proofs", "controls", "known_misses") for value in ("a case", ["a case"], {"event": {}})],
            ("`covers_hooks` is not a list of hook names", dict(gap, covers_hooks={"notify.sh": True})),
            ("`covers_hooks` is not a list of hook names", dict(gap, covers_hooks=["notify.sh", 3])),
            ("`target` is not a mapping", dict(gap, target=["hook"])),
            ("`hosts` is not a list of host group names", dict(row, hosts={"mac": True})),
            ("`hosts` is not a list of host group names", dict(row, hosts=["mac", True])),
            ("`occurrences` is not a list", dict(row, occurrences={"n": 2})),
        ]
        for needle, bad in cases:
            with self.subTest(needle=needle, row=repr(bad)[:80]):
                base = LATER if bad["id"] == gap["id"] else PACK
                self.refused(f"the row `{bad['id']}` cannot be replayed: {needle}", "--pack",
                             str(self.pack(dict(base, rules=[bad]), "shape.yaml")))

    def test_a_pack_file_that_is_not_there_or_not_named_is_refused(self) -> None:
        self.refused("there is no pack at", "--pack", str(self.tmp / "absent.yaml"))
        self.refused("--pack needs a file", "--pack")
        self.refused("--pack needs a file", "--pack=")
        # `~user` for a user this machine does not have: expanding it raises, before any file is looked for.
        self.refused("is not a path this run can read", "--pack", "~no-such-user-bro4147/pack.yaml")

    def test_a_pack_in_a_folder_that_cannot_be_entered_is_refused_not_a_traceback(self) -> None:
        """Looking for the file can itself fail. A review got a traceback and exit 1 on Python
        3.12, where the look raises; on later versions it answers that no file is there. Either
        way: exit 2, the pack named, nothing written."""
        if os.geteuid() == 0:
            self.skipTest("root enters any folder")
        locked = self.tmp / "locked"
        locked.mkdir()
        pack = self.pack(name="pack.yaml")
        inside = locked / "pack.yaml"
        inside.write_bytes(pack.read_bytes())
        locked.chmod(0o000)
        self.addCleanup(locked.chmod, 0o700)
        before = tree(self.repo)
        proc = self.run_correct("init", "--pack", str(inside))
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn(str(inside), proc.stderr)
        self.assertEqual(tree(self.repo), before)

    def test_two_packs_that_disagree_are_refused(self) -> None:
        first = str(self.pack())
        same_id = dict(LATER, rules=[dict(LATER["rules"][0], id="no-bad")])
        self.refused("the row id `no-bad` is in two packs", "--pack", first,
                     "--pack", str(self.pack(same_id, "later.yaml")))
        other_reason = dict(LATER, hooks_not_rules={"notify.sh": "something else"})
        self.refused("a reason another pack gives differently", "--pack", first,
                     "--pack", str(self.pack(other_reason, "later.yaml")))

    def test_a_registry_the_runner_refuses_is_could_not_run_not_a_failed_row(self) -> None:
        """The runner stops with a message before it replays anything (a `class_threshold` that is
        no number). That is exit 2, and init's paragraph about failed rows does not follow it."""
        self.assertEqual(self.run_correct("init", "--pack", str(self.pack())).returncode, 0)
        registry = correct.governance_file(self.repo, "rules.yaml")
        registry.write_text(registry.read_text().replace("class_threshold: 2", "class_threshold: high", 1))
        for command in (("check",), ("init", "--pack", str(self.pack()))):
            proc = self.run_correct(*command)
            self.assertEqual(proc.returncode, 2, (command, proc.stdout + proc.stderr))
            self.assertIn("class_threshold must be a positive integer", proc.stderr)
            self.assertNotIn("so it does not repair one either", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_a_registry_is_created_and_never_replaced(self) -> None:
        """write_file with `new`: a name that is taken is refused, and what is there is kept."""
        target = self.tmp / "out" / "rules.yaml"
        correct.write_file(target, b"first\n", False, new=True)
        with self.assertRaises(correct.Taken):
            correct.write_file(target, b"second\n", False, new=True)
        self.assertEqual(target.read_bytes(), b"first\n")
        self.assertEqual([p.name for p in target.parent.iterdir()], ["rules.yaml"])

    def test_an_init_that_loses_the_race_for_the_registry_reports_what_it_lacks(self) -> None:
        """Two inits at once, each with its own pack: one writes the registry. The other finds
        its name taken when it comes to write, writes none, and exits 3 with its pack's rows
        listed as missing. Before, both wrote, both exited 0, and one pack's rows were gone."""
        first, later = self.pack(), self.pack(LATER, "later.yaml")
        real = correct.write_file
        registry = correct.governance_file(self.repo, "rules.yaml")

        def lose_the_race(path: Path, content: bytes, executable: bool, new: bool = False) -> str | None:
            if path == registry:  # the other init gets there first, with the other pack
                real(path, correct.registry_with_packs([(first, correct.load_pack(first))]), False, new=True)
            return real(path, content, executable, new=new)

        self.addCleanup(setattr, correct, "write_file", real)
        correct.write_file = lose_the_race
        out = io.StringIO()
        with contextlib.redirect_stdout(out), unittest.mock.patch.dict(os.environ, self.env):
            status = correct.init(self.repo, ["--pack", str(later)])
        self.assertEqual(status, correct.PACK_NOT_WHOLE, out.getvalue())
        self.assertIn("answered that the name is taken", out.getvalue())
        self.assertIn("row(s) missing: later-gap", out.getvalue())
        held = [r["id"] for r in yaml.safe_load(registry.read_text())["rules"]]
        self.assertIn("no-bad", held)
        self.assertNotIn("later-gap", held)

    def test_two_spellings_of_one_hook_command_are_one_hook(self) -> None:
        first = dict(PACK, hooks_not_rules={"notify.sh --quiet": "one reason"})
        other = dict(LATER, hooks_not_rules={"notify.sh  --quiet": "another reason"})
        self.refused("a reason another pack gives differently", "--pack", str(self.pack(first)),
                     "--pack", str(self.pack(other, "later.yaml")))

    def test_a_row_id_twice_in_one_pack_is_said_as_that(self) -> None:
        twice = dict(LATER, rules=[LATER["rules"][0], dict(LATER["rules"][0], rule="Another.")])
        self.refused("the row id `later-gap` is twice in this pack", "--pack", str(self.pack(twice, "twice.yaml")))

    def test_a_registry_of_another_version_is_refused_before_a_pack_is_compared_with_it(self) -> None:
        self.assertEqual(self.run_correct("init", "--pack", str(self.pack())).returncode, 0)
        registry = correct.governance_file(self.repo, "rules.yaml")
        registry.write_text(registry.read_text().replace("version: 1", "version: 2", 1))
        proc = self.run_correct("init", "--pack", str(self.pack(LATER, "later.yaml")))
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("this copy of the skill replays version 1", proc.stderr)
        self.assertNotIn("pack   later", proc.stdout)

    def test_two_packs_that_disagree_are_refused_on_a_registry_that_exists_too(self) -> None:
        """There they would be listed as rows that differ, to copy by hand, and copying either
        would make the other differ."""
        first = str(self.pack())
        self.assertEqual(self.run_correct("init", "--pack", first).returncode, 0)
        same_id = dict(LATER, rules=[dict(LATER["rules"][0], id="no-bad")])
        self.refused("the row id `no-bad` is in two packs", "--pack", first,
                     "--pack", str(self.pack(same_id, "later.yaml")))
        other_reason = dict(LATER, hooks_not_rules={"notify.sh": "something else"})
        self.refused("a reason another pack gives differently", "--pack", first,
                     "--pack", str(self.pack(other_reason, "later.yaml")))

    def test_a_registry_that_would_not_read_back_is_refused(self) -> None:
        """The packs' rows are appended after the starter's rows, which holds only while `rules`
        is the starter's last key. A starter laid out otherwise must be refused, not written."""
        templates = self.tmp / "templates"
        templates.mkdir()
        (templates / "rules.yaml").write_text("version: 1\nrules:\n- id: branch-first\nclass_threshold: 2\n")
        self.addCleanup(setattr, correct, "TEMPLATES", correct.TEMPLATES)
        correct.TEMPLATES = templates
        with self.assertRaises(correct.Refused) as caught:
            correct.registry_with_packs([(self.tmp / "pack.yaml", PACK)])
        self.assertIn("does not read back as written", str(caught.exception))


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
        for line in ("version: 2\n", "version: true\n", "version: 1.0\n", ""):  # later, two wrong types, none
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

    def test_help_needs_no_repository_and_no_registry(self) -> None:
        for cwd in (self.repo, self.tmp):  # a repository before init, and no repository at all
            for command, usage in (("check", "usage: rules_check.py"), ("canary", "usage: rules_canary.py")):
                for args in (("--help",), ("-h",), ("--root", str(self.repo), "--help"),
                             (f"--root={self.repo}", "--help")):
                    proc = self.run_correct(command, *args, cwd=cwd)
                    self.assertEqual(proc.returncode, 0, (command, args, proc.stdout + proc.stderr))
                    self.assertIn(usage, proc.stdout)

    def test_a_root_option_without_its_directory_never_runs_a_tool_even_beside_help(self) -> None:
        """`--root --help`: --root takes the next word as its value, with or without --help.
        An earlier version looked for --help first, dropped it with --root, and then ran the
        checker (and the canary, which writes a receipt) on the current directory."""
        self.init()
        receipt = self.repo / ".control" / "rules-canary-receipt.json"
        for args in (("check", "--root", "--help"), ("check", "--root", "-h"),
                     ("canary", "--root", "--help", "run", "--claude", "/bin/false", "--dir", str(self.tmp / "cd"))):
            proc = self.run_correct(*args)  # the current directory is the set-up repository
            self.assertEqual(proc.returncode, 2, (args, proc.stdout + proc.stderr))
            self.assertIn("is not a directory", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertNotIn("PASS", proc.stdout)
            self.assertFalse(receipt.exists())
        empty = self.run_correct("check", "--root=", "--help")
        self.assertEqual(empty.returncode, 2, empty.stdout + empty.stderr)
        self.assertIn("empty value", empty.stderr)

    def test_beside_help_a_tool_is_handed_help_and_nothing_else(self) -> None:
        self.init()
        receipt = self.repo / ".control" / "rules-canary-receipt.json"
        for args, shown in ((("check", "--only", "branch-first", "--help"), "usage: rules_check.py"),
                            (("check", "--help", "--json"), "usage: rules_check.py"),
                            # The tool's own parser would reject this one; handed --help alone, it prints.
                            (("check", "--", "--help"), "usage: rules_check.py"),
                            (("canary", "run", "--claude", "/bin/false", "--help"), "usage: rules_canary.py run")):
            proc = self.run_correct(*args)
            self.assertEqual(proc.returncode, 0, (args, proc.stdout + proc.stderr))
            self.assertIn(shown, proc.stdout)
            self.assertNotIn("PASS", proc.stdout)
            self.assertFalse(receipt.exists())

    def test_no_command_prints_the_usage_and_exits_2(self) -> None:
        proc = self.run_correct()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("correct.py init", proc.stdout)
        self.assertEqual(self.run_correct("--help").returncode, 0)
        asked = self.run_correct("init", "--help")
        self.assertEqual(asked.returncode, 0, asked.stderr)
        self.assertIn("correct.py init", asked.stdout)
        self.assertEqual(tree(self.repo), {})

    def test_a_root_option_with_nothing_after_it_is_refused(self) -> None:
        proc = self.run_correct("check", "--root")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--root needs a directory", proc.stderr)

    def test_a_registry_that_is_not_yaml_is_refused(self) -> None:
        self.init()
        (self.repo / ".control" / "rules.yaml").write_text("version: 1\nrules: [unclosed\n")
        for command in ("check", "init"):
            proc = self.run_correct(command)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("is not readable YAML", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_a_shortened_registry_option_names_the_registry_that_is_checked(self) -> None:
        self.init()
        other = self.tmp / "v2.yaml"
        other.write_text(self.registry_text("version: 2\n"))
        for args in (("--reg", str(other)), (f"--regis={other}",)):
            proc = self.run_correct("check", *args)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("v2.yaml says `version: 2`", proc.stderr)

    def test_an_empty_registry_option_is_refused(self) -> None:
        self.init()
        for args in (("--registry=",), ("--registry",), ("--registry", "")):
            proc = self.run_correct("check", *args)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("--registry needs a file", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_a_relative_registry_is_read_from_the_current_directory_and_the_message_says_so(self) -> None:
        self.init()
        proc = self.run_correct("check", "--root", str(self.repo), "--registry", ".control/rules.yaml", cwd=self.tmp)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn(f"there is no registry at {self.tmp / '.control' / 'rules.yaml'}", proc.stderr)
        self.assertIn("relative to the current directory", proc.stderr)
        inside = self.run_correct("check", "--registry", ".control/rules.yaml", "--only", "branch-first")
        self.assertEqual(inside.returncode, 0, inside.stdout + inside.stderr)

    def test_the_canary_always_checks_the_repositorys_own_registry(self) -> None:
        self.init()
        good = self.tmp / "v1.yaml"
        good.write_bytes((self.repo / ".control" / "rules.yaml").read_bytes())
        (self.repo / ".control" / "rules.yaml").write_text(self.registry_text("version: 2\n"))
        proc = self.run_correct("canary", f"--registry={good}", "run")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("this copy of the skill replays version 1", proc.stderr)

    def test_init_on_a_set_up_repository_whose_hook_entry_was_removed_says_it_repairs_nothing(self) -> None:
        self.init()
        (self.repo / ".claude" / "settings.json").write_text('{"hooks": {}}')
        proc = self.run_correct("init")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("not registered", proc.stdout)
        # The whole of what init adds, and no more: it names no repair (a registry can hold rows
        # of the workspace's own, and an earlier text said to delete it) and says nothing of
        # FAIL rows, of which a replay that exits 1 need not have any.
        self.assertTrue(proc.stderr.endswith(self.KEPT_AND_FAILED), proc.stderr)

    KEPT_AND_FAILED = ("\ncorrect init: the replay exits 1; its output is above. init does not change a registry "
                       "that is there, so it does not repair one either.\n")

    def test_a_registry_with_no_rules_exits_1_which_is_the_runners_own_status(self) -> None:
        """The runner refuses to report a pass over nothing and returns 1, as on main. correct.py
        passes on a status the runner returns itself (it turns only an unhandled error and a
        SystemExit with a message into 2), and what init adds is true with no FAIL row."""
        self.init()
        registry = correct.governance_file(self.repo, "rules.yaml")
        registry.write_text("version: 1\nrules: []\n")
        for command in ("check", "init"):
            with self.subTest(command=command):
                proc = self.run_correct(command)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertIn("the registry has no rules; refusing to report a pass over nothing", proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
        self.assertTrue(proc.stderr.endswith(self.KEPT_AND_FAILED), proc.stderr)

    def test_canary_runs_the_canary_not_the_runner(self) -> None:
        self.init()
        proc = self.run_correct("canary", "--help")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("usage: rules_canary.py", proc.stdout)
        # Without --help too: the canary's own parser answers an argument only it would reject.
        real = self.run_correct("canary", "no-such-subcommand")
        self.assertEqual(real.returncode, 2, real.stdout + real.stderr)
        self.assertIn("usage: rules_canary.py", real.stderr)

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
        self.assertEqual(len(correct.SCRIPT_FILES), 4)

    def test_the_starter_row_and_the_hook_entry_agree(self) -> None:
        data = yaml.safe_load((SKILL / "assets" / "templates" / "rules.yaml").read_text())
        (row,) = data["rules"]
        self.assertEqual(row["enforcer"]["path"], f"scripts/{correct.ENFORCER}")
        self.assertEqual(row["enforcer"]["registered"]["event"], "PreToolUse")
        self.assertEqual("|".join(row["enforcer"]["registered"]["tools"]), correct.HOOK_GROUP["matcher"])
        # The group init writes, and the policy it writes, in full: a changed value is a changed contract.
        self.assertEqual(correct.HOOK_GROUP, {"matcher": "Write|Edit|MultiEdit|NotebookEdit", "hooks": [
            {"type": "command", "command": '"$CLAUDE_PROJECT_DIR"/scripts/branch-first-hook.py', "timeout": 10}]})
        self.assertEqual(yaml.safe_load(correct.POLICY), {"gates": {"hard": []}})
        # SKILL.md states these counts; a changed template must change the sentence too.
        self.assertEqual((len(row["proofs"]), len(row["controls"]), len(row["known_misses"])), (10, 3, 2))
        self.assertIn("ten proofs, three\n  controls and two recorded known misses", (SKILL / "SKILL.md").read_text())
        self.assertTrue(row["canary"]["none"] and row["canary"]["ticket"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
