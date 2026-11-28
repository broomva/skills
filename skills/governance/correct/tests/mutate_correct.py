#!/usr/bin/env -S python3 -I
"""mutate_correct.py — break scripts/correct.py and tests/vendored.py one rule at a time; the suite
must notice each.

Each mutant is one textual change that removes one promise the command or the manifest check
makes. The skill is copied to a temporary directory, the change is applied to the copy, and
tests/test_correct.py runs against the copy. A mutant the suite still passes on is a promise
no test holds.

  python3 -I tests/mutate_correct.py        prints one line per mutant, then "N killed, M survived"
  python3 -I tests/mutate_correct.py --shard K/N
                                            runs every N-th mutant, starting at the K-th, and first
                                            prints "shard K/N: <run here> of <all> mutants". Each
                                            mutant is in exactly one of the N shards. CI runs one
                                            job per shard: one job for all of them passed its time limit.

A mutant is killed only when a test fails; a run that timed out is reported as undecided.

Exit 0 when every mutant is killed, 1 when one survives, 2 when a mutant no longer applies
(its text is not found exactly once: the code changed, so the mutant must be rewritten),
when the unchanged suite does not pass (a red suite would "kill" every mutant), or when
--shard is not K/N with 1 <= K <= N (at most four digits each). A mutant that no longer applies stops every shard.
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
     "        print(\"\\n\".join(lines))\n    status = replay(root, wrote=False, registry=registry if named else None)\n",
     "        print(\"\\n\".join(lines))\n    status = 0\n"),
    ("a dry run on an existing registry exits 0 without replaying",
     "        return on_registry(root, registry, packs)\n\n    try:\n",
     "        return 0 if dry else on_registry(root, registry, packs)\n\n    try:\n"),
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
     "            replayable(target)\n", ""),
    ("after a collision the registry is searched for again, not read at the plan's name",
     "            replayable(target)\n", "            need_registry(root, [])\n"),
    ("an init that loses the race reports success whatever the replay says",
     "            return on_registry(root, target, packs, named=True)\n        except OSError as exc:\n",
     "            on_registry(root, target, packs, named=True)\n            return 0\n        except OSError as exc:\n"),
    ("after a collision the registry that is there is not compared with the packs given",
     "            return on_registry(root, target, packs, named=True)\n", "            return on_registry(root, target, [], named=True)\n"),
    ("after a collision the runner searches for a registry and may replay another folder's",
     "            return on_registry(root, target, packs, named=True)\n", "            return on_registry(root, target, packs)\n"),
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
    ("an existing registry of an unknown version is replayed by init, and compared with a pack",
     "        need_registry(root, [])  # first: a registry this skill does not read is compared with no pack\n",
     ""),
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
     "    return status\n\n\nPACK_KEYS", "    return 0\n\n\nPACK_KEYS"),
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
     "    if unknown:\n        raise Refused(f\"init does not take", "    if False:\n        raise Refused(f\"init does not take"),
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
     "    writes.append((gov / \"rules.yaml\", registry_with_packs(packs or []), False))\n    return writes, kept, conflicts\n",
     "    writes.insert(0, (gov / \"rules.yaml\", registry_with_packs(packs or []), False))\n    return writes, kept, conflicts\n"),
    ("a failed write is a traceback, not a refusal",
     "        except OSError as exc:\n            raise Refused(f\"could not write", "        except ZeroDivisionError as exc:\n            raise Refused(f\"could not write"),
    ("a failed write leaves its temporary file",
     "        if os.path.exists(tmp):\n            os.unlink(tmp)\n        raise\n", "        raise\n"),
    # After a collision the replay line says which file is replayed.
    ("the replay after a collision does not say which registry",
     "        print(f\"\\ncorrect init: replaying the registry at {registry}\\n\")\n",
     "        print(\"\\ncorrect init: replaying the registry (correct.py check)\\n\")\n"),
    # The file is finished before its name appears. Linked first and written after (whatever the
    # link answers), every test that looks once the call has returned still finds it whole: only
    # the one that reads the name at the link does not.
    ("a new file is linked before it is written",
     "        with os.fdopen(fd, \"wb\") as handle:\n            handle.write(content)\n"
     "        os.chmod(tmp, mode | 0o100 | ((mode & 0o044) >> 2) if executable else mode)\n"
     "        if new:\n            try:\n                os.link(tmp, path)\n",
     "        if not new:\n            with os.fdopen(fd, \"wb\") as handle:\n                handle.write(content)\n"
     "            os.chmod(tmp, mode | 0o100 | ((mode & 0o044) >> 2) if executable else mode)\n"
     "        if new:\n            try:\n                try:\n                    os.link(tmp, path)\n"
     "                finally:\n"
     "                    with os.fdopen(fd, \"wb\") as handle:\n                        handle.write(content)\n"
     "                    os.chmod(tmp, mode | 0o100 | ((mode & 0o044) >> 2) if executable else mode)\n"),
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
    ("a registry that is not YAML is a traceback",
     "    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:\n        raise Refused(f\"{registry} is not readable YAML",
     "    except ZeroDivisionError as exc:\n        raise Refused(f\"{registry} is not readable YAML"),
    ("a pack that is not YAML is a traceback",
     "    except (OSError, ValueError, yaml.YAMLError) as exc:\n        raise Refused(f\"{path} is not readable YAML",
     "    except ZeroDivisionError as exc:\n        raise Refused(f\"{path} is not readable YAML"),
    ("no command at all exits 0",
     "        return 0 if argv else 2\n", "        return 0\n"),
    ("a shortened --registry is not the registry that is checked",
     "        if len(option) >= len(\"--reg\") and \"--registry\".startswith(option):\n",
     "        if option == \"--registry\":\n"),
    ("a pack is recorded in the output and not added to the registry",
     "    if not packs:\n        return template\n", "    if True:\n        return template\n"),
    ("a pack file that is not there is a traceback",
     "        if not path.is_file():\n            raise Refused(f\"there is no pack at {path}\")\n", ""),
    ("a pack in a folder that cannot be entered is looked for outside the guard (a traceback on Python 3.12)",
     "    try:\n        # Inside the guard: on Python 3.12 the look itself raises for a folder that cannot be entered.\n"
     "        if not path.is_file():\n            raise Refused(f\"there is no pack at {path}\")\n",
     "    if not path.is_file():\n        raise Refused(f\"there is no pack at {path}\")\n    try:\n"),
    ("a pack that is not a mapping is a traceback",
     "    if not isinstance(data, dict):\n        raise Refused(f\"{path} is not a pack: it is not a mapping\")\n", ""),
    ("a pack's keys init does not carry over are dropped without a word",
     "    unknown = sorted(set(data) - PACK_KEYS)  # every key is a string: the loader refused the rest\n", "    unknown = []\n"),
    ("a registry that lacks a pack's row replays to exit 0",
     "    return PACK_NOT_WHOLE if status == 0 and not whole else status\n", "    return status\n"),
    ("a pack's missing rows are not listed",
     "        missing = [r[\"id\"] for r in pack[\"rules\"] if r[\"id\"] not in rows]\n", "        missing = []\n"),
    ("a pack's reworded rows are not listed",
     "        differ = [r[\"id\"] for r in pack[\"rules\"] if r[\"id\"] in rows and not same(rows[r[\"id\"]], r)]\n",
     "        differ = []\n"),
    ("a pack's missing hooks_not_rules are not listed",
     "        hooks = [s for s, why in (pack.get(\"hooks_not_rules\") or {}).items() if (hook_name(s), why) not in held]\n",
     "        hooks = []\n"),
    ("a file that is not a pack is accepted when a registry exists",
     "    # Read before anything else: a file that is not a pack is refused whether or not a registry exists.\n"
     "    packs = [(path, load_pack(path)) for path in map(pack_path, pack_files)]\n",
     "    packs = [] if governance_file(root, \"rules.yaml\").exists() else "
     "[(path, load_pack(path)) for path in map(pack_path, pack_files)]\n"),
    ("the notice that main is closed comes after the replay, if the replay ends",
     "          \"branch. The replay below checks the registration.\", flush=True)\n    return replay(root, wrote=True)\n",
     "          \"branch. The replay below checks the registration.\", flush=True) if False else None\n"
     "    status = replay(root, wrote=True)\n"
     "    print(\"an edit on main or master in this repository is refused\")\n    return status\n"),
    ("a key given twice in a pack is taken, and the first block is dropped",
     "                    elif key in seen:\n", "                    elif False:\n"),
    ("a merge key is taken, and drops what a later key of the same name replaces",
     "                    refuse = \"a pack does not use merge keys (`<<`); write the keys out\"\n", "                    continue\n"),
    ("a key that is not a string is taken",
     "                    if not isinstance(key, str):\n", "                    if False:\n"),
    ("a pack with a date that is no date is a traceback",
     "    except (OSError, ValueError, yaml.YAMLError) as exc:\n        raise Refused(f\"{path} is not readable YAML ({exc})\") from exc\n    if not isinstance(data, dict):\n        raise Refused(f\"{path} is not a pack: it is not a mapping\")",
     "    except (OSError, yaml.YAMLError) as exc:\n        raise Refused(f\"{path} is not readable YAML ({exc})\") from exc\n    if not isinstance(data, dict):\n        raise Refused(f\"{path} is not a pack: it is not a mapping\")"),
    ("a tool that refuses to run, with a message, is passed on as a failed row",
     "    if not isinstance(stop.code, str):\n        raise\n", "    raise\n"),
    ("two spellings of one hook command are two hooks to init",
     "            name = hook_name(script)\n", "            name = script\n"),
    ("a hook command spaced another way is a hook the registry lacks",
     "if (hook_name(s), why) not in held]", "if (s, why) not in held]"),
    ("a registry's own hook command is compared as it is spaced",
     "    held = [(hook_name(s), why) for s, why in held.items() if isinstance(s, str)]\n",
     "    held = [(s, why) for s, why in held.items() if isinstance(s, str)]\n"),
    ("of two spellings of one hook command in a registry, the last one's reason is the only one",
     "    held = [(hook_name(s), why) for s, why in held.items() if isinstance(s, str)]\n",
     "    held = list({hook_name(s): why for s, why in held.items() if isinstance(s, str)}.items())\n"),
    ("a registry key that is no string stops init with a traceback",
     "    held = [(hook_name(s), why) for s, why in held.items() if isinstance(s, str)]\n",
     "    held = [(hook_name(s), why) for s, why in held.items()]\n"),
    ("a reader that closed the pipe is reported as a registry row of the wrong kind",
     "except BrokenPipeError:\n    raise\n", ""),
    ("init adds its line about a failed replay after a runner that could not run",
     "    elif status == 1:\n", "    elif status != 0:\n"),
    ("after a failed replay on a registry that is there init says more than what happened",
     "registry that is there, so it does not repair one either.\", file=sys.stderr)\n",
     "registry that is there, so it does not repair one either. Each FAIL row names the rule.\", file=sys.stderr)\n"),
    ("init adds its line about a failed first replay after a runner that could not run",
     "    elif status == 1 and wrote:\n", "    elif status != 0 and wrote:\n"),
    ("after a failed first replay init prescribes a repair",
     "the replay exits {status}; its output is above.\",\n              file=sys.stderr)\n",
     "the replay exits {status}; its output is above. Add a row for each FAIL row.\",\n              file=sys.stderr)\n"),
    ("a hook script named by nothing is accepted in hooks_not_rules",
     "            isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip() for", "            isinstance(k, str) and isinstance(v, str) and v.strip() for"),
    ("a hook's reason that is only spaces is accepted",
     "isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip() for", "isinstance(k, str) and k.strip() and isinstance(v, str) and v for"),
    ("a row id that is only spaces is accepted",
     "isinstance(r.get(\"id\"), str) and r[\"id\"].strip() for r in rules", "isinstance(r.get(\"id\"), str) and r[\"id\"] for r in rules"),
    ("a row whose level is an empty word passes",
     "    if not (isinstance(row.get(\"level\"), str) and row[\"level\"].strip()):\n", "    if not isinstance(row.get(\"level\"), str):\n"),
    ("a row that differs from the pack only in the kind of a value is called the same",
     "if r[\"id\"] in rows and not same(rows[r[\"id\"]], r)]", "if r[\"id\"] in rows and rows[r[\"id\"]] != r]"),
    ("a value two rows share is written as an anchor and aliases",
     "    return yaml.dump(data, Dumper=Plain, sort_keys=False", "    return yaml.dump(data, Dumper=yaml.SafeDumper, sort_keys=False"),
    ("a gap row whose target is not a mapping passes",
     "    if \"target\" in row and not isinstance(row[\"target\"], dict):\n", "    if False:\n"),
    ("a row whose known_misses is not a list of cases passes",
     "    for key in (\"proofs\", \"controls\", \"known_misses\"):\n", "    for key in (\"proofs\", \"controls\"):\n"),
    ("a pack path that cannot be expanded is a traceback",
     "    except (OSError, RuntimeError) as exc:\n        raise Refused(f\"--pack {given} is not a path this run can read",
     "    except ZeroDivisionError as exc:\n        raise Refused(f\"--pack {given} is not a path this run can read"),
    ("a row whose occurrences is a number passes",
     "    if \"occurrences\" in row and not isinstance(row[\"occurrences\"], list):\n", "    if False:\n"),
    ("a pack row that is no mapping is a traceback",
     "isinstance(r, dict) and isinstance(r.get(\"id\"), str) and r[\"id\"].strip() for r in rules):",
     "isinstance(r.get(\"id\"), str) and r[\"id\"].strip() for r in rules):"),
    ("a hook's reason that is no string is a traceback",
     "isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip() for k, v in not_rules.items()):",
     "isinstance(k, str) and k.strip() and v.strip() for k, v in not_rules.items()):"),
    ("a registry row that is no mapping stops the comparison with a traceback",
     "rows = {r.get(\"id\"): r for r in rules if isinstance(r, dict) and isinstance(r.get(\"id\"), str)}",
     "rows = {r.get(\"id\"): r for r in rules}"),
    ("a row whose hosts holds something that is no name passes",
     "    if \"hosts\" in row and not (isinstance(row[\"hosts\"], list) and all(isinstance(h, str) for h in row[\"hosts\"])):\n",
     "    if \"hosts\" in row and not isinstance(row[\"hosts\"], list):\n"),
    ("a row whose covers_hooks holds something that is no name passes",
     "    if \"covers_hooks\" in row and not (isinstance(row[\"covers_hooks\"], list)\n"
     "                                      and all(isinstance(h, str) for h in row[\"covers_hooks\"])):\n",
     "    if \"covers_hooks\" in row and not isinstance(row[\"covers_hooks\"], list):\n"),
    ("a row whose list of cases holds something that is no case passes",
     "        if key in row and not (isinstance(row[key], list) and all(isinstance(c, dict) for c in row[key])):\n",
     "        if key in row and not isinstance(row[key], list):\n"),
    ("a row whose hosts is a word passes",
     "    if \"hosts\" in row and not (isinstance(row[\"hosts\"], list)", "    if False and not (isinstance(row[\"hosts\"], list)"),
    ("a field left empty passes the shape check as if it were absent",
     "        if key in row and not (isinstance(row[key], list)", "        if row.get(key) is not None and not (isinstance(row[key], list)"),
    ("a runner that stops on an error is passed on as its own exit status",
     "    if status == CRASHED:\n", "    if False:\n"),
    ("the notice says edits are refused from now on, whatever the settings",
     "          \"Where the harness runs it, an edit on main", "          \"From now on an edit on main"),
    ("the first init with a pack reports success without replaying",
     "    return replay(root, wrote=True)\n", "    return 0 if packs else replay(root, wrote=True)\n"),
    ("a registry that holds no list of rows is a traceback",
     "    if not isinstance(rules, list):\n", "    if False:\n"),
    ("a pack row the runner cannot read is written, and stops the replay with a traceback",
     "        problem = row_shape(row)\n", "        problem = None\n"),
    ("a pack row whose enforcer is not a mapping passes",
     "    if \"enforcer\" in row and not isinstance(enforcer, dict):\n", "    if False:\n"),
    ("a pack row whose cases are not a list of mappings passes",
     "        if key in row and not (isinstance(row[key], list) and all(isinstance(c, dict) for c in row[key])):\n",
     "        if False:\n"),
    ("a pack's name may be any text, a second line included",
     "    if not PACK_NAME.fullmatch(data[\"pack\"]):\n", "    if False:\n"),
    ("a pack need not name itself",
     "    if not isinstance(data.get(\"pack\"), str) or not data[\"pack\"].strip():\n", "    if False:\n"),
    ("a pack for another registry version is added",
     "    if type(version) is not int or version not in REGISTRY_VERSIONS:\n        raise Refused(f\"{path} says `registry_version",
     "    if False:\n        raise Refused(f\"{path} says `registry_version"),
    ("a pack's rows are not checked for an id",
     "    if not isinstance(rules, list) or not rules or not all(\n", "    if False and not all(\n"),
    ("a pack's hooks_not_rules is not checked",
     "    if not isinstance(not_rules, dict) or not all(\n", "    if False and not all(\n"),
    ("a pack row may reuse an id already in the registry",
     "            if row[\"id\"] in ids:\n", "            if False:\n"),
    ("two packs may give one hook two reasons",
     "            if reasons.get(name, why) != why:\n", "            if False:\n"),
    ("two packs may hold one row id",
     "            if row[\"id\"] in seen:\n", "            if False:\n"),
    ("packs that disagree are only refused when init writes the registry",
     "    packs_agree(packs)\n", "    if not governance_file(root, \"rules.yaml\").exists():\n        packs_agree(packs)\n"),
    ("--pack with no file is accepted",
     "    if \"\" in named:\n        raise Refused(\"--pack needs a file\")\n", ""),
    ("a registry that does not read back is written",
     "    if back != expected:\n", "    if False:\n"),
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


def main(argv: list[str]) -> int:
    plan = [(TARGET, m) for m in MUTANTS] + [(VENDORED, m) for m in VENDORED_MUTANTS]
    k, n = 1, 1
    if argv:
        parts = argv[1].split("/") if len(argv) == 2 and argv[0] == "--shard" else []
        if len(parts) != 2 or not all(p.isascii() and p.isdigit() and len(p) <= 4 for p in parts) or not 1 <= int(parts[0]) <= int(parts[1]):
            print("usage: mutate_correct.py [--shard K/N], with 1 <= K <= N", file=sys.stderr)
            return 2
        k, n = int(parts[0]), int(parts[1])
    stale = [m[0] for target, m in plan if (SKILL / target).read_text().count(m[1]) != 1]
    if stale:
        for name in stale:
            print(f"mutant no longer applies (its text is not found exactly once): {name}", file=sys.stderr)
        return 2
    everything = len(plan)
    plan = plan[k - 1::n]
    if argv:
        print(f"shard {k}/{n}: {len(plan)} of {everything} mutants", flush=True)
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
    sys.exit(main(sys.argv[1:]))
