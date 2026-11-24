#!/usr/bin/env -S python3 -I
"""mutate_correct.py — break scripts/correct.py and tests/vendored.py one rule at a time; the suite
must notice each.

Each mutant is one textual change that removes one promise the command or the manifest check
makes. The skill is copied to a temporary directory, the change is applied to the copy, and
tests/test_correct.py runs against the copy. A mutant the suite still passes on is a promise
no test holds.

  python3 -I tests/mutate_correct.py        prints one line per mutant, then "N killed, M survived"

Exit 0 when every mutant is killed, 1 when one survives, 2 when a mutant no longer applies
(its text is not found exactly once: the code changed, so the mutant must be rewritten).
The live skill directory is never modified.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
TARGET = Path("scripts") / "correct.py"

MUTANTS: list[tuple[str, str, str]] = [
    ("a differing file no longer stops init",
     "    if conflicts and not force:\n", "    if False:\n"),
    ("an existing registry is overwritten",
     "    if registry.exists():\n", "    if False:\n"),
    ("an existing registry is reported as success without a replay",
     "        need_registry(root, [])\n        return replay(root, wrote=False)\n", "        return 0\n"),
    ("a dry run on an existing registry replays",
     "        if dry:\n            return 0\n        need_registry(root, [])\n", "        need_registry(root, [])\n"),
    ("an existing registry of an unknown version is replayed by init",
     "        need_registry(root, [])\n        return replay(root, wrote=False)\n", "        return replay(root, wrote=False)\n"),
    ("a registry of an unknown version is replayed",
     "    if version not in REGISTRY_VERSIONS or isinstance(version, bool):\n", "    if False:\n"),
    ("--registry is not the registry that is checked",
     "    registry = Path(named).expanduser() if named else governance_file(root, \"rules.yaml\")\n",
     "    registry = governance_file(root, \"rules.yaml\")\n"),
    ("an empty --root falls back to the environment",
     "    if named == \"\":\n", "    if False:\n"),
    ("an identical hook that is not executable is kept as it is",
     "            if name in EXECUTABLE and not os.access(target, os.X_OK):\n", "            if False:\n"),
    ("the fixtures script is not made executable",
     "EXECUTABLE = {ENFORCER, \"rules_fixtures.py\"}\n", "EXECUTABLE = {ENFORCER}\n"),
    ("settings that are not a JSON object are accepted",
     "        if not isinstance(settings, dict):\n", "        if False:\n"),
    ("check always exits 0",
     "    return subprocess.run([sys.executable, \"-I\", str(HERE / script), *args], env=env, check=False).returncode\n",
     "    subprocess.run([sys.executable, \"-I\", str(HERE / script), *args], env=env, check=False)\n    return 0\n"),
    ("init exits 0 whatever the replay says",
     "    return status\n\n\ndef init", "    return 0\n\n\ndef init"),
    ("the hook entry is added even when the exact one is there",
     "                exact = True\n", "                exact = False\n"),
    ("an entry that mentions the enforcer in another form is kept as if it ran it",
     "            if command == HOOK_COMMAND and group.get(\"matcher\") == HOOK_GROUP[\"matcher\"]:\n",
     "            if True:\n"),
    ("the enforcer entry on fewer tools counts as the exact one",
     "            if command == HOOK_COMMAND and group.get(\"matcher\") == HOOK_GROUP[\"matcher\"]:\n",
     "            if command == HOOK_COMMAND:\n"),
    ("a PreToolUse that is not a list is not checked",
     "    if not isinstance(hooks, dict) or not isinstance(hooks.setdefault(\"PreToolUse\", []), list):\n",
     "    if False:\n"),
    ("a malformed PreToolUse entry is not checked",
     "        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):\n",
     "        if False:\n"),
    ("a read-only file is replaced",
     "        if path.exists() and not os.access(path, os.W_OK):\n", "        if False:\n"),
    ("an unwritable directory is not noticed before writing",
     "            if at.is_dir() and not os.access(at, os.W_OK | os.X_OK):\n", "            if False:\n"),
    ("init does not check for PyYAML before writing",
     "    if not dry:\n        need_yaml()\n", ""),
    ("check and canary do not check for PyYAML",
     "        need_yaml()\n        need_registry(root, rest)\n", "        need_registry(root, rest)\n"),
    ("check without a registry reaches the runner",
     "        need_yaml()\n        need_registry(root, rest)\n", "        need_yaml()\n"),
    ("canary runs the runner",
     "\"rules_check.py\" if command == \"check\" else \"rules_canary.py\"", "\"rules_check.py\""),
    ("the registry always goes to the last governance directory",
     "    for name in DIRS:\n        if (root / name).is_dir():\n            return root / name\n", ""),
    ("a file that is already the skill's copy is treated as a conflict",
     "        elif target.is_file() and target.read_bytes() == content:\n", "        elif False:\n"),
    ("a dry run writes",
     "    if dry:\n        print(\"correct init: dry run, nothing written.\")\n        return 0\n", ""),
    ("--root and RULES_CHECK_ROOT are ignored",
     "    named = named or os.environ.get(\"RULES_CHECK_ROOT\")\n", "    named = None\n"),
    ("RULES_CHECK_ROOT is ignored",
     "    named = named or os.environ.get(\"RULES_CHECK_ROOT\")\n", ""),
    ("init accepts a directory below the top of the checkout",
     "    if git_toplevel(root) != root:\n", "    if False:\n"),
    ("unknown init options are accepted",
     "    if unknown:\n", "    if False:\n"),
    ("the hook is not made executable",
     "        os.chmod(tmp, mode | 0o111 if executable else mode)\n", "        os.chmod(tmp, mode)\n"),
    ("a replaced file loses its permissions",
     "    mode = (path.stat().st_mode & 0o777) if path.is_file() else 0o644\n", "    mode = 0o644\n"),
    ("a registry path that is a directory is treated as a registry",
     "    if registry.exists() and not registry.is_file():\n", "    if False:\n"),
    ("a missing git is a traceback",
     "    except OSError as exc:\n        raise Refused(f\"git could not be run", "    except ZeroDivisionError as exc:\n        raise Refused(f\"git could not be run"),
    ("an existing policy file is replaced",
     "    if policy.exists():\n        kept.append(f\"{policy.relative_to(root)} (yours; the replay reads its gates.hard)\")\n    else:\n        writes.append",
     "    if True:\n        writes.append"),
    ("symlinks and misplaced files are not checked before writing",
     "    stops = blocked(root, writes)\n", "    stops = []\n"),
    ("a symlinked file is written through",
     "        if path.is_symlink():\n", "        if False:\n"),
    ("a symlinked directory is written through",
     "            if at.is_symlink():\n", "            if False:\n"),
    ("a file where a directory must go is not noticed",
     "            if at.exists() and not at.is_dir():\n", "            if False:\n"),
    ("the registry is written first",
     "    writes.append((gov / \"rules.yaml\", (TEMPLATES / \"rules.yaml\").read_bytes(), False))\n    return writes, kept, conflicts\n",
     "    writes.insert(0, (gov / \"rules.yaml\", (TEMPLATES / \"rules.yaml\").read_bytes(), False))\n    return writes, kept, conflicts\n"),
    ("a failed write is a traceback, not a refusal",
     "        except OSError as exc:\n            raise Refused(", "        except ZeroDivisionError as exc:\n            raise Refused("),
    ("a failed write leaves its temporary file",
     "        if os.path.exists(tmp):\n            os.unlink(tmp)\n        raise\n", "        raise\n"),
    ("a file is written in place, not replaced whole",
     "        os.replace(tmp, path)\n", "        shutil_copy = open(path, \"wb\"); shutil_copy.write(content); shutil_copy.close()\n"),
    ("unreadable settings are treated as empty",
     "            raise Refused(f\"{settings_path} is not readable JSON ({exc}); fix it, then run init again\") from exc\n",
     "            settings = {}\n"),
    ("an unknown command runs the runner",
     "    if command not in (\"init\", \"check\", \"canary\"):\n", "    if False:\n"),
]

# The manifest checker is a gate too (CI runs it), so it is broken here as well.
VENDORED_MUTANTS: list[tuple[str, str, str]] = [
    ("the manifest check reports nothing",
     "    return out\n", "    return []\n"),
    ("a shipped file that differs from its recorded hash is not reported",
     "        elif sha(path) != entry[\"shipped_sha256\"]:\n", "        elif False:\n"),
    ("a difference from the source needs no recorded reason",
     "        if entry[\"shipped_sha256\"] != entry[\"source_sha256\"] and not any(\n", "        if False and not any(\n"),
    ("--write also rewrites the source hashes",
     "            entry[\"shipped_sha256\"] = sha(SCRIPTS / name)\n",
     "            entry[\"shipped_sha256\"] = entry[\"source_sha256\"] = sha(SCRIPTS / name)\n"),
]


VENDORED = Path("tests") / "vendored.py"


def run(snapshot: Path, target: Path, mutant: tuple[str, str, str]) -> tuple[str, bool, str]:
    name, old, new = mutant
    with tempfile.TemporaryDirectory(prefix="correct-mutant-") as tmp:
        copy = Path(tmp) / "skill"
        shutil.copytree(snapshot, copy)
        (copy / target).write_text((snapshot / target).read_text().replace(old, new))
        proc = subprocess.run([sys.executable, "-I", str(copy / "tests" / "test_correct.py")],
                              capture_output=True, text=True, check=False)
    return name, proc.returncode != 0, proc.stderr[-300:]


def main() -> int:
    plan = [(TARGET, m) for m in MUTANTS] + [(VENDORED, m) for m in VENDORED_MUTANTS]
    stale = [m[0] for target, m in plan if (SKILL / target).read_text().count(m[1]) != 1]
    if stale:
        for name in stale:
            print(f"mutant no longer applies (its text is not found exactly once): {name}", file=sys.stderr)
        return 2
    # One snapshot for the whole run: an edit to the live skill while this runs cannot mix
    # one version's code with another version's tests.
    with tempfile.TemporaryDirectory(prefix="correct-snapshot-") as snap:
        snapshot = Path(snap) / "skill"
        shutil.copytree(SKILL, snapshot, ignore=shutil.ignore_patterns("__pycache__"))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda item: run(snapshot, item[0], item[1]), plan))
    for name, killed, _tail in results:
        print(f"{'killed  ' if killed else 'SURVIVED'} {name}")
    survived = sum(1 for _name, killed, _tail in results if not killed)
    print(f"{len(results) - survived} killed, {survived} survived")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
