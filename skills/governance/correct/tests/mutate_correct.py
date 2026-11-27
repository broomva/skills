#!/usr/bin/env -S python3 -I
"""mutate_correct.py — break scripts/correct.py and tests/vendored.py one rule at a time; the suite
must notice each.

Each mutant is one textual change that removes one promise the command or the manifest check
makes. The skill is copied to a temporary directory, the change is applied to the copy, and
tests/test_correct.py runs against the copy. A mutant the suite still passes on is a promise
no test holds.

  python3 -I tests/mutate_correct.py        prints one line per mutant, then "N killed, M survived"

A mutant is killed only when a test fails; a run that timed out is reported as undecided.

Exit 0 when every mutant is killed, 1 when one survives, 2 when a mutant no longer applies
(its text is not found exactly once: the code changed, so the mutant must be rewritten) or
when the unchanged suite does not pass (a red suite would "kill" every mutant).
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
     "    need_registry(root, [])\n    return replay(root, wrote=False)\n", "    return 0\n"),
    ("a dry run on an existing registry exits 0 without replaying",
     "        return on_registry(root)\n\n    try:\n", "        return 0 if dry else on_registry(root)\n\n    try:\n"),
    ("the registry is replaced when another init has published one",
     "                os.link(tmp, path)\n", "                os.replace(tmp, path)\n"),
    ("an init that finds the registry written meanwhile does not take the existing-registry path",
     "        except NotCreated as why:\n", "        except ZeroDivisionError as why:\n"),
    ("a write that stops on a name taken, or on any error, is handled as a registry not created",
     "        except NotCreated as why:\n", "        except (NotCreated, OSError) as why:\n"),
    ("a name taken by a folder or a dangling link is replayed",
     "            if not a_file:\n", "            if False:\n"),
    ("a link to nothing at the name is said to be something that cannot be read",
     "            except FileNotFoundError:  # a link to nothing\n                a_file = False\n",
     "            except FileNotFoundError:  # a link to nothing\n                raise\n"),
    ("a name taken by something that cannot be read is a traceback",
     "            except OSError as unreadable:\n", "            except ZeroDivisionError as unreadable:\n"),
    ("a link that answers with an error is told as a name that was taken",
     "            if isinstance(why, NotLinked):\n", "            if False:\n"),
    ("an init that loses the race replays a registry of a version this copy does not replay",
     "            replayable(target)  # this file, at this name: no second search for where a registry might be\n", ""),
    ("after a collision the registry is searched for again, not read at the plan's name",
     "            replayable(target)  # this file, at this name: no second search for where a registry might be\n",
     "            need_registry(root, [])\n"),
    ("an init that loses the race reports success whatever the replay says",
     "            return replay(root, wrote=False)\n        except OSError as exc:\n",
     "            replay(root, wrote=False)\n            return 0\n        except OSError as exc:\n"),
    ("the path init looks at, not the one its plan writes, is the registry it creates as new",
     "    target = writes[-1][0]\n", "    target = registry\n"),
    ("a name that is taken is treated as a registry this run wrote",
     "            except FileExistsError:\n                failed = Taken(str(path))\n",
     "            except FileExistsError:\n                pass\n"),
    ("a new file's name is looked at before the link, so a taken name that cannot be read is a failed write",
     "    mode = (path.stat().st_mode & 0o777) if not new and path.is_file() else 0o666 & ~umask\n",
     "    mode = (path.stat().st_mode & 0o777) if path.is_file() else 0o666 & ~umask\n"),
    ("the name is looked at after the link's answer, and that look's error replaces the link's",
     "            except OSError as exc:\n                failed = NotLinked(str(exc))\n",
     "            except OSError as exc:\n                os.stat(path)\n                failed = NotLinked(str(exc))\n"),
    ("a link that answers with an error is treated as a registry this run wrote",
     "            except OSError as exc:\n                failed = NotLinked(str(exc))\n",
     "            except OSError as exc:\n                pass\n"),
    ("a temporary file that cannot be removed turns a written or taken registry into a failed write",
     "    except OSError:\n        left = tmp\n", "    except ZeroDivisionError:\n        left = tmp\n"),
    ("a temporary file that is already gone is called left",
     "    except FileNotFoundError:\n        pass\n    except OSError:\n        left = tmp\n",
     "    except OSError:\n        left = tmp\n"),
    ("a temporary file that is left is never said",
     "    if left:\n        print(f\"correct init: removing this run's temporary file", "    if False:\n        print(f\"correct init: removing this run's temporary file"),
    ("a run that did not create the registry does not say the temporary file it left",
     "            say_left(target.parent.relative_to(root), why.left)\n", ""),
    ("a run that wrote the registry does not say the temporary file it left",
     "        say_left(path.parent.relative_to(root), left)\n", ""),
    ("an existing registry of an unknown version is replayed by init",
     "    need_registry(root, [])\n    return replay(root, wrote=False)\n",
     "    return replay(root, wrote=False)\n"),
    ("a registry of an unknown version is replayed",
     "    if type(version) is not int or version not in REGISTRY_VERSIONS:  # 1, not 1.0 and not true\n", "    if False:\n"),
    ("a registry version that is a float or a boolean is accepted",
     "    if type(version) is not int or version not in REGISTRY_VERSIONS:  # 1, not 1.0 and not true\n",
     "    if version not in REGISTRY_VERSIONS:\n"),
    ("--registry is not the registry that is checked",
     "    registry = Path(named).expanduser().absolute() if named else governance_file(root, \"rules.yaml\")\n",
     "    registry = governance_file(root, \"rules.yaml\")\n"),
    ("an empty --root falls back to the environment",
     "        if named == \"\":\n            raise Refused(\"--root needs a directory, and got an empty value\")\n", ""),
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
     "    return status\n\n\ndef on_registry", "    return 0\n\n\ndef on_registry"),
    ("the hook entry is added even when init's own group is there",
     "    return len(others) != len(groups)\n", "    return False\n"),
    ("any group that mentions the enforcer counts as init's own",
     "    others = [g for g in groups if g != HOOK_GROUP]\n",
     "    others = [g for g in groups if f\"scripts/{ENFORCER}\" not in json.dumps(g)]\n"),
    ("a mention of the enforcer in another form is not refused",
     "    if f\"scripts/{ENFORCER}\" in json.dumps(others):\n", "    if False:\n"),
    # The setdefault stays (removing it would break every run, which proves nothing).
    ("a PreToolUse that is not a list is not checked",
     "    if not isinstance(hooks, dict) or not isinstance(hooks.setdefault(\"PreToolUse\", []), list):\n",
     "    if not isinstance(hooks, dict) or hooks.setdefault(\"PreToolUse\", []) is None:\n"),
    ("hooks that are not an object are a traceback, not a refusal",
     "    if not isinstance(hooks, dict) or not isinstance(hooks.setdefault(\"PreToolUse\", []), list):\n",
     "    if not isinstance(hooks.setdefault(\"PreToolUse\", []), list):\n"),
    ("a malformed PreToolUse entry is not checked",
     "        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):\n",
     "        if False:\n"),
    ("an error while reading the repository's state is a traceback",
     "    except OSError as exc:\n        raise Refused(f\"could not read the repository's current state",
     "    except ZeroDivisionError as exc:\n        raise Refused(f\"could not read the repository's current state"),
    ("the directory a file is created in need not be writable",
     "                if not os.access(at, (os.W_OK | os.X_OK) if nearest else os.X_OK):\n",
     "                if not os.access(at, os.X_OK):\n"),
    ("an empty --registry reaches the runner",
     "    if named == \"\":\n        raise Refused(\"--registry needs a file, and got none\")\n", ""),
    ("the canary's arguments can name another registry to be checked",
     "    for i, arg in enumerate(args if flag else []):\n", "    for i, arg in enumerate(args):\n"),
    ("--help needs a repository and a registry",
     "        if \"-h\" in rest or \"--help\" in rest:\n            if command == \"init\":",
     "        if command == \"init\" and (\"-h\" in rest or \"--help\" in rest):\n            if command == \"init\":"),
    ("a read-only file is replaced",
     "        if path.exists() and not os.access(path, os.W_OK):\n", "        if False:\n"),
    ("an unwritable directory is not noticed before writing",
     "                if not os.access(at, (os.W_OK | os.X_OK) if nearest else os.X_OK):\n", "                if False:\n"),
    ("init does not check for PyYAML before writing",
     "    need_yaml()  # also on a dry run: it reports what the real run would do, and that run would stop here\n", ""),
    ("the settings' own characters are re-escaped",
     "json.dumps(settings, indent=2, ensure_ascii=False)", "json.dumps(settings, indent=2)"),
    ("a settings value with no UTF-8 form is a traceback",
     "        except UnicodeEncodeError:  # a lone surrogate has no UTF-8 form; it can only stay escaped\n",
     "        except ZeroDivisionError:\n"),
    ("the hook entry init writes has another timeout than the one the suite pins",
     "\"command\": HOOK_COMMAND, \"timeout\": 10}", "\"command\": HOOK_COMMAND, \"timeout\": 11}"),
    ("the starter policy lists a hard gate that is not a gate",
     "    \"  hard: []\\n\"\n", "    \"  hard: [broken]\\n\"\n"),
    ("init --help is an error",
     "            if command == \"init\":\n                print(__doc__)\n                return 0\n", ""),
    ("--help is looked for before --root is taken out, so a --root without its directory runs the tool",
     "        if \"-h\" in rest or \"--help\" in rest:\n            if command == \"init\":",
     "        if \"-h\" in argv or \"--help\" in argv:\n            if command == \"init\":"),
    ("the caller's other arguments reach the tool beside --help",
     "[\"run\", \"--help\"] if tool == \"rules_canary.py\" and \"run\" in rest\n                            else [\"--help\"])",
     "rest)"),
    ("check and canary do not check for PyYAML",
     "        need_yaml()\n        need_registry(root, rest, flag=command == \"check\")\n",
     "        need_registry(root, rest, flag=command == \"check\")\n"),
    ("check without a registry reaches the runner",
     "        need_yaml()\n        need_registry(root, rest, flag=command == \"check\")\n", "        need_yaml()\n"),
    ("canary runs the runner",
     "        tool = \"rules_check.py\" if command == \"check\" else \"rules_canary.py\"\n",
     "        tool = \"rules_check.py\"\n"),
    ("-h is not --help",
     "        if \"-h\" in rest or \"--help\" in rest:\n            if command == \"init\":",
     "        if \"--help\" in rest:\n            if command == \"init\":"),
    ("every directory above a file must be writable, not only the one it is created in",
     "                nearest = False\n", "                pass\n"),
    ("a new hook is executable for its owner only",
     "        os.chmod(tmp, mode | 0o100 | ((mode & 0o044) >> 2) if executable else mode)\n",
     "        os.chmod(tmp, mode | 0o100 if executable else mode)\n"),
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
     "        os.chmod(tmp, mode | 0o100 | ((mode & 0o044) >> 2) if executable else mode)\n", "        os.chmod(tmp, mode)\n"),
    ("a private hook becomes executable for everyone",
     "        os.chmod(tmp, mode | 0o100 | ((mode & 0o044) >> 2) if executable else mode)\n",
     "        os.chmod(tmp, mode | 0o111 if executable else mode)\n"),
    ("a replaced file loses its permissions",
     "    mode = (path.stat().st_mode & 0o777) if not new and path.is_file() else 0o666 & ~umask\n", "    mode = 0o666 & ~umask\n"),
    ("a new file ignores the caller's umask",
     "    mode = (path.stat().st_mode & 0o777) if not new and path.is_file() else 0o666 & ~umask\n",
     "    mode = (path.stat().st_mode & 0o777) if not new and path.is_file() else 0o644\n"),
    ("a registry path that is a directory is treated as a registry",
     "    if registry.exists() and not registry.is_file():\n", "    if False:\n"),
    ("a missing git is a traceback",
     "    except OSError as exc:\n        raise Refused(f\"git could not be run", "    except ZeroDivisionError as exc:\n        raise Refused(f\"git could not be run"),
    ("an existing policy file is replaced",
     "    if policy.exists():\n        kept.append(f\"{policy.relative_to(root)} (yours; the replay reads its gates.hard)\")\n    else:\n        writes.append",
     "    if True:\n        writes.append"),
    ("a policy path that is a directory is kept as a policy file",
     "    if policy.exists() and not policy.is_file():\n", "    if False:\n"),
    ("the escaped form of the settings loses its layout",
     "            data = (json.dumps(settings, indent=2) + \"\\n\").encode(\"ascii\")\n",
     "            data = json.dumps(settings).encode(\"ascii\")\n"),
    ("symlinks and misplaced files are not checked before writing",
     "    stops = blocked(root, writes)\n", "    stops = []\n"),
    ("a symlinked file is written through",
     "        if path.is_symlink():\n", "        if False:\n"),
    ("a symlinked directory is written through",
     "            if parent != Path(\".\") and at.is_symlink():\n", "            if False:\n"),
    ("a file where a directory must go is not noticed",
     "            if at.exists() and not at.is_dir():\n", "            if False:\n"),
    ("the registry is written first",
     "    writes.append((gov / \"rules.yaml\", (TEMPLATES / \"rules.yaml\").read_bytes(), False))\n    return writes, kept, conflicts\n",
     "    writes.insert(0, (gov / \"rules.yaml\", (TEMPLATES / \"rules.yaml\").read_bytes(), False))\n    return writes, kept, conflicts\n"),
    ("a failed write is a traceback, not a refusal",
     "        except OSError as exc:\n            raise Refused(f\"could not write", "        except ZeroDivisionError as exc:\n            raise Refused(f\"could not write"),
    ("a failed write leaves its temporary file",
     "        if os.path.exists(tmp):\n            os.unlink(tmp)\n        raise\n", "        raise\n"),
    # A real in-place write: same content, same mode, no temporary file left. Only a test that
    # looks at WHICH file was written (a second name for the old one) can tell it from a replace.
    ("a file is written in place, not replaced whole",
     "        else:\n            os.replace(tmp, path)\n",
     "        else:\n            with open(path, \"wb\") as handle:\n                handle.write(content)\n"
     "            os.chmod(path, os.stat(tmp).st_mode & 0o777)\n            os.unlink(tmp)\n"),
    ("unreadable settings are treated as empty",
     "            raise Refused(f\"{settings_path} is not readable JSON ({exc}); fix it, then run init again\") from exc\n",
     "            settings = {}\n"),
    ("a directory where a file goes is not noticed",
     "        if path.exists() and not path.is_file():\n", "        if False:\n"),
    ("the registry does not go beside an existing policy file",
     "    if policy.exists():\n        return policy.parent\n", ""),
    ("a --root with nothing after it is accepted",
     "            if i + 1 >= len(argv):\n                raise Refused(\"--root needs a directory\")\n",
     "            if i + 1 >= len(argv):\n                break\n"),
    ("a registry whose YAML raises ValueError is a traceback",
     "    except (OSError, ValueError, yaml.YAMLError) as exc:  # ValueError: undecodable bytes, or a date that is none\n",
     "    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:\n"),
    ("a registry that is not YAML is a traceback",
     "    except (OSError, ValueError, yaml.YAMLError) as exc:  # ValueError: undecodable bytes, or a date that is none\n",
     "    except ZeroDivisionError as exc:\n"),
    ("no command at all exits 0",
     "        return 0 if argv else 2\n", "        return 0\n"),
    ("a shortened --registry is not the registry that is checked",
     "        if len(option) >= len(\"--reg\") and \"--registry\".startswith(option):\n",
     "        if option == \"--registry\":\n"),
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
RUN_LIMIT_S = 1500  # one suite run takes about two minutes; this only stops a hang


def run(snapshot: Path, target: Path, mutant: tuple[str, str, str]) -> tuple[str, str]:
    """(name, verdict). "killed" only when a test FAILED on an assertion or an error of its own.
    A run that stopped on a timeout decided nothing, and counting it as a kill would let a slow
    machine certify a mutant no test notices."""
    name, old, new = mutant
    with tempfile.TemporaryDirectory(prefix="correct-mutant-") as tmp:
        copy = Path(tmp) / "skill"
        shutil.copytree(snapshot, copy)
        (copy / target).write_text((snapshot / target).read_text().replace(old, new))
        # -f: stop at the first failing test. One failure is the whole answer for a mutant.
        try:
            proc = subprocess.run([sys.executable, "-I", str(copy / "tests" / "test_correct.py"), "-f"],
                                  capture_output=True, text=True, check=False, timeout=RUN_LIMIT_S)
        except subprocess.TimeoutExpired:
            return name, "UNDECIDED"  # a mutant that hangs the suite decided nothing either
    if proc.returncode == 0:
        return name, "SURVIVED"
    if "TimeoutExpired" in proc.stderr or "FAILED (" not in proc.stderr:
        return name, "UNDECIDED"
    return name, "killed"


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
        # A suite that is already red "kills" every mutant. The unchanged snapshot must pass
        # first, or no line below means anything.
        baseline = subprocess.run([sys.executable, "-I", str(snapshot / "tests" / "test_correct.py")],
                                  capture_output=True, text=True, check=False)
        if baseline.returncode != 0:
            print("the unchanged suite fails, so no mutant was run:\n" + baseline.stderr[-600:], file=sys.stderr)
            return 2
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda item: run(snapshot, item[0], item[1]), plan))
    for name, verdict in results:
        print(f"{verdict:<9} {name}")
    survived = sum(1 for _name, verdict in results if verdict == "SURVIVED")
    undecided = sum(1 for _name, verdict in results if verdict == "UNDECIDED")
    print(f"{len(results) - survived - undecided} killed, {survived} survived"
          + (f", {undecided} undecided (a timeout, or a run that ended without a test failing)" if undecided else ""))
    return 1 if survived else 2 if undecided else 0


if __name__ == "__main__":
    sys.exit(main())
