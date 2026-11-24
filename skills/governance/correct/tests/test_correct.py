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
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(tree(self.repo), before)

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

    def test_an_unknown_command_exits_2(self) -> None:
        proc = self.run_correct("chek")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("init, check or canary", proc.stderr)

    def test_a_root_that_is_not_a_directory_exits_2(self) -> None:
        proc = self.run_correct("check", "--root", str(self.tmp / "absent"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("is not a directory", proc.stderr)


class Shipped(unittest.TestCase):
    def test_the_vendored_files_are_the_recorded_ones(self) -> None:
        self.assertEqual(vendored.mismatches(), [])

    def test_the_manifest_covers_every_runner_file_init_or_check_uses(self) -> None:
        recorded = set(json.loads(vendored.MANIFEST.read_text())["files"])
        self.assertEqual(recorded, {"rules_check.py", "rules_canary.py", *correct.SCRIPT_FILES})

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
