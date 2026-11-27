#!/usr/bin/env -S python3 -I
"""correct.py — set a repository up with a rule registry, and replay it.

  correct.py init   [--root DIR] [--dry-run] [--force]
      Give a repository its registry: the registry file with one proven rule
      (branch first), that rule's enforcer and its fixtures under scripts/, a
      governance policy file if there is none, and the hook entry in
      .claude/settings.json. Then replay the registry and exit with the replay's
      status. A repository that already has a registry gets nothing written and
      is replayed the same way. A repository whose existing gates and hooks have
      no row yet exits 1 and lists them.
  correct.py check  [--root DIR] [runner options ...]
      Replay every row against its real enforcer (scripts/rules_check.py in this
      skill): --ci, --json, --markdown, --only ID ..., --base REF, --replay-only.
  correct.py canary [--root DIR] [canary options ...]
      The real-harness canary (scripts/rules_canary.py in this skill).

This file lives in the skill, not in the repository it sets up: call it by its
path in the skill's directory. The repository is --root, else $RULES_CHECK_ROOT,
else the git checkout the current directory is in. The runner and the canary run
from this skill's directory, outside the repository they judge; the enforcers
and the registry rows are the repository's own files.

Exit codes: 0 done and the replay passed; 1 the replay failed; 2 the command
could not run (no repository, no registry for check, git or PyYAML missing, a
registry of a version this copy does not replay, an unreadable settings file,
a file init would have to overwrite, a path that leaves the repository). On 2,
init has written nothing unless it says which files it wrote; when the link
that creates the registry answers with an error, the registry is not among the
files it lists and may be there all the same. A dry run on a
repository without a registry lists what would be written and is refused
wherever the real run is refused before it tries a write; it tries none, so it
cannot say that one will fail, nor whether the replay will pass afterwards. On
a repository with a registry it is the same run as the real one.
"""
from __future__ import annotations

import json
import os
import site
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "assets" / "templates"

# Appended, not prepended: the stdlib keeps precedence under -I.
sys.path.append(str(HERE))
from governance_paths import DIRS, governance_file  # noqa: E402

# What init copies into the repository's scripts/. The hook is the enforcer; it imports
# governance_paths. The registry's cases build their state with rules_fixtures, which
# imports rules_case_data. The runner looks for the fixtures at {root}/scripts/.
ENFORCER = "branch-first-hook.py"
SCRIPT_FILES = (ENFORCER, "governance_paths.py", "rules_fixtures.py", "rules_case_data.py")
EXECUTABLE = {ENFORCER, "rules_fixtures.py"}
HOOK_COMMAND = f'"$CLAUDE_PROJECT_DIR"/scripts/{ENFORCER}'
HOOK_GROUP = {
    "matcher": "Write|Edit|MultiEdit|NotebookEdit",
    "hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 10}],
}
POLICY = (
    "# The governance policy. `gates.hard` lists the hard gates; a gate with a `pattern`\n"
    "# needs a row in rules.yaml (`policy_gate:`) that proves it. Written by `correct.py init`.\n"
    "gates:\n"
    "  hard: []\n"
)

Write = tuple[Path, bytes, bool]  # (path, content, executable)


class Refused(Exception):
    """The command cannot run; the message names what to do."""


def git_toplevel(cwd: Path) -> Path | None:
    try:
        proc = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, check=False)
    except OSError as exc:
        raise Refused(f"git could not be run ({exc}); the commands need git on PATH") from exc
    return Path(proc.stdout.strip()).resolve() if proc.returncode == 0 and proc.stdout.strip() else None


def split_root(argv: list[str]) -> tuple[str | None, list[str]]:
    """(what --root names or None, the arguments without it). --root DIR or --root=DIR, anywhere."""
    rest: list[str] = []
    named: str | None = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--root":
            if i + 1 >= len(argv):
                raise Refused("--root needs a directory")
            named = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--root="):
            named = arg.split("=", 1)[1]
        else:
            rest.append(arg)
        i += 1
    return named, rest


def resolve_root(named: str | None) -> Path:
    """The repository: what --root named, else $RULES_CHECK_ROOT, else the checkout of the current directory."""
    named = named or os.environ.get("RULES_CHECK_ROOT")
    if named:
        root = Path(named).expanduser().resolve()
        if not root.is_dir():
            raise Refused(f"{root} is not a directory")
        return root
    top = git_toplevel(Path.cwd())
    if top is None:
        raise Refused("not inside a git checkout; run it from the repository or pass --root DIR")
    return top


YAML_PROBE = "import site, sys; sys.path.append(site.getusersitepackages()); import yaml"


def need_yaml() -> None:
    """The runner and the canary need PyYAML, found the way they find it (the user site is
    added back under -I). Checked before init writes anything: a repository set up and then
    not replayable has an enforcer installed and nothing that says whether it holds."""
    proc = subprocess.run([sys.executable, "-I", "-c", YAML_PROBE], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise Refused(f"PyYAML is not importable by {sys.executable}; install it "
                      "(python3 -m pip install --user pyyaml) and run the command again. Nothing written.")


# The registry versions this copy of the runner replays. A registry written for a later
# version may carry fields this runner would ignore, and a row it ignores part of can pass
# without being checked; so an unknown version is refused, not replayed.
REGISTRY_VERSIONS = (1,)


def need_registry(root: Path, args: list[str], flag: bool = False) -> None:
    """A registry exists and is a version this copy of the skill replays. With `flag` (the
    runner, which takes --registry FILE), the file named there is the registry; it is read the
    way the runner reads it, relative to the current directory. The canary takes no such
    option and always reads the repository's own registry."""
    named = None
    for i, arg in enumerate(args if flag else []):
        option, eq, value = arg.partition("=")
        # The runner's parser takes any unambiguous start of the option (--reg, --regis ...).
        if len(option) >= len("--reg") and "--registry".startswith(option):
            named = value if eq else (args[i + 1] if i + 1 < len(args) else "")
    if named == "":
        raise Refused("--registry needs a file, and got none")
    registry = Path(named).expanduser().absolute() if named else governance_file(root, "rules.yaml")
    if not registry.is_file():
        raise Refused(f"there is no registry at {registry}" + ("; run init first" if not named else
                      " (--registry is read relative to the current directory, as the runner reads it)"))
    replayable(registry)


def replayable(registry: Path) -> None:
    """The file is YAML, and a registry of a version this copy of the skill replays."""
    if site.getusersitepackages() not in sys.path:
        sys.path.append(site.getusersitepackages())
    import yaml  # noqa: PLC0415  (need_yaml ran first)
    try:
        data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    except Exception as exc:  # reading, decoding, parsing, and what a constructor raises on a value: all one answer
        raise Refused(f"{registry} is not readable YAML ({exc})") from exc
    version = data.get("version") if isinstance(data, dict) else None
    if type(version) is not int or version not in REGISTRY_VERSIONS:  # 1, not 1.0 and not true
        raise Refused(f"{registry} says `version: {version!r}`, and this copy of the skill replays "
                      f"version {' or '.join(map(str, REGISTRY_VERSIONS))}. Update the skill, or correct "
                      "the registry's `version:`.")


def run_tool(script: str, root: Path, args: list[str]) -> int:
    env = dict(os.environ, RULES_CHECK_ROOT=str(root))
    sys.stdout.flush()  # what this command printed so far comes before the tool's own output
    sys.stderr.flush()
    return subprocess.run([sys.executable, "-I", str(HERE / script), *args], env=env, check=False).returncode


def governance_dir(root: Path) -> Path:
    """Where a new registry goes: beside the policy file, else an existing governance directory."""
    policy = governance_file(root, "policy.yaml")
    if policy.exists():
        return policy.parent
    for name in DIRS:
        if (root / name).is_dir():
            return root / name
    return root / DIRS[-1]


def enforcer_entry(settings: dict, settings_path: Path) -> bool:
    """True when the settings already hold the group init writes, value for value; False when
    nothing in them mentions the enforcer. Anything else that mentions it is refused.

    init does not read an entry and decide whether it would run the hook. Three review rounds
    found that reading wrong three ways (a substring, a matcher on fewer tools, a `type` that
    is not a command), each time as "kept" here and "not registered" in the replay. Equality
    with what init itself writes needs no judgment, and the replay judges everything else."""
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict) or not isinstance(hooks.setdefault("PreToolUse", []), list):
        raise Refused(f"{settings_path}: `hooks.PreToolUse` is not a list; fix it, then run init again")
    groups = hooks["PreToolUse"]
    for group in groups:  # the shape only: a settings file the harness would reject loads no hook at all
        entries = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise Refused(f"{settings_path}: a `hooks.PreToolUse` entry is not {{matcher, hooks: [...]}}; "
                          "fix it, then run init again")
    others = [g for g in groups if g != HOOK_GROUP]
    if f"scripts/{ENFORCER}" in json.dumps(others):
        raise Refused(f"{settings_path} already mentions scripts/{ENFORCER} under `hooks.PreToolUse` in a "
                      "form other than the entry init writes. Nothing written. init recognises only its "
                      "own entry and does not judge whether another one runs the hook. Remove that entry "
                      "and run init again (init then writes its own), or keep yours, write the registry "
                      "row by hand and run `check`.")
    return len(others) != len(groups)


def plan(root: Path) -> tuple[list[Write], list[str], list[str]]:
    """(files to write, files left as they are, conflicts). The registry is the LAST write:
    its presence is what marks a repository as set up, so a run that stops early leaves a
    repository the next run still treats as not set up."""
    writes: list[Write] = []
    kept: list[str] = []
    conflicts: list[str] = []

    for name in SCRIPT_FILES:
        target = root / "scripts" / name
        content = (HERE / name).read_bytes()
        if not target.exists():
            writes.append((target, content, name in EXECUTABLE))
        elif target.is_file() and target.read_bytes() == content:
            if name in EXECUTABLE and not os.access(target, os.X_OK):
                writes.append((target, content, True))  # the same bytes, made executable
            else:
                kept.append(f"scripts/{name} (already this version)")
        else:
            conflicts.append(f"scripts/{name} exists and differs from the skill's copy")
            writes.append((target, content, name in EXECUTABLE))

    gov = governance_dir(root)
    policy = governance_file(root, "policy.yaml")
    if policy.exists() and not policy.is_file():
        raise Refused(f"{policy.relative_to(root)} exists and is not a regular file; nothing written")
    if policy.exists():
        kept.append(f"{policy.relative_to(root)} (yours; the replay reads its gates.hard)")
    else:
        writes.append((gov / "policy.yaml", POLICY.encode(), False))

    settings_path = root / ".claude" / "settings.json"
    settings: dict = {}
    if settings_path.is_file():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise Refused(f"{settings_path} is not readable JSON ({exc}); fix it, then run init again") from exc
        if not isinstance(settings, dict):
            raise Refused(f"{settings_path} is not a JSON object; fix it, then run init again")
    if enforcer_entry(settings, settings_path):
        kept.append(".claude/settings.json (it has the entry init writes; the replay says whether the harness runs it)")
    else:
        settings["hooks"]["PreToolUse"].append(HOOK_GROUP)
        try:  # their characters, as they wrote them
            data = (json.dumps(settings, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        except UnicodeEncodeError:  # a lone surrogate has no UTF-8 form; it can only stay escaped
            data = (json.dumps(settings, indent=2) + "\n").encode("ascii")
        writes.append((settings_path, data, False))

    writes.append((gov / "rules.yaml", (TEMPLATES / "rules.yaml").read_bytes(), False))
    return writes, kept, conflicts


def blocked(root: Path, writes: list[Write]) -> list[str]:
    """Why a planned write cannot land where it is planned. Checked for every file before any is
    written: a path that goes through a symlink would write outside the repository (or into a
    file the repository does not own), and a file where a directory must go would stop the run
    after some files were already written."""
    out: list[str] = []
    for path, _content, _exe in writes:
        rel = path.relative_to(root)
        if path.is_symlink():
            out.append(f"{rel} is a symlink; init writes only regular files inside the repository")
            continue
        if path.exists() and not path.is_file():
            out.append(f"{rel} exists and is not a regular file")
            continue
        if path.exists() and not os.access(path, os.W_OK):
            out.append(f"{rel} is read-only; init does not replace a file marked read-only")
            continue
        nearest = True  # the deepest directory that exists is where the file or its folders get made
        for parent in rel.parents:  # from the file's own directory up to the repository itself
            at, name = root / parent, ("the repository's top directory" if parent == Path(".") else f"{parent}/")
            if parent != Path(".") and at.is_symlink():
                out.append(f"{parent}/ is a symlink; init writes only inside the repository ({rel})")
                break
            if at.exists() and not at.is_dir():
                out.append(f"{parent} is a file, and {rel} needs it to be a directory")
                break
            if at.is_dir():
                if not os.access(at, (os.W_OK | os.X_OK) if nearest else os.X_OK):
                    out.append(f"{name} is not writable ({rel})")
                    break
                nearest = False
    return sorted(set(out))


class NotCreated(Exception):
    """write_file was asked for a new file and the link that creates it did not answer yes.
    `left` is the temporary file's name if removing it answered with an error, else None."""

    left: str | None = None


class Taken(NotCreated):
    """The link answered that the name is taken. What is there is kept."""


class NotLinked(NotCreated):
    """The link answered with any other error. The message is that error."""


def write_file(path: Path, content: bytes, executable: bool, new: bool = False) -> str | None:
    """Whole or not at all: the content goes to a temporary file beside the target, which then
    replaces it, so an interrupted run never leaves a half-written settings file.

    With `new`, the target must not exist, and is never replaced: the finished temporary file
    is linked to the target's name, which the filesystem does in one step and refuses when
    the name is taken (Taken). There is no other way in: any other error from the link is
    NotLinked. The link's answer is taken as given: nothing looks at the name before the link
    or after it. link(2) can answer with an error for a link it made (its BUGS section), so
    NotLinked does not mean the file is not there, and no caller says it does.

    The answer is settled before the temporary file is removed, and a removal that answers
    with an error does not change it: the temporary name is returned (written) or carried by
    the exception, for the caller to say. Otherwise the return is None."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # A file that is replaced keeps its own permissions (a settings file kept private stays
    # private); a new one gets what the caller's umask allows, as any created file would. The
    # hook is executable for its owner, and for whoever else may already read it.
    umask = os.umask(0)
    os.umask(umask)
    mode = (path.stat().st_mode & 0o777) if not new and path.is_file() else 0o666 & ~umask
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    failed: NotCreated | None = None
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        os.chmod(tmp, mode | 0o100 | ((mode & 0o044) >> 2) if executable else mode)
        if new:
            try:
                os.link(tmp, path)
            except FileExistsError:
                failed = Taken(str(path))
            except OSError as exc:
                failed = NotLinked(str(exc))
        else:
            os.replace(tmp, path)
            return None
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    left = None
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    except OSError:
        left = tmp
    if failed:
        failed.left = left
        raise failed
    return left


def say_left(folder: Path, left: str | None) -> None:
    if left:
        print(f"correct init: removing this run's temporary file {folder / Path(left).name} answered with an "
              "error.", file=sys.stderr, flush=True)


def replay(root: Path, wrote: bool) -> int:
    print("\ncorrect init: replaying the registry (correct.py check)\n")
    status = run_tool("rules_check.py", root, [])
    if status == 0 and wrote:
        print("\ncorrect init: done. The starter rule is installed and its proofs and controls replay.\n"
              "  - From now on an edit on main or master in this repository is refused; work on a branch.\n"
              "  - Commit the new files on a branch. In CI run this skill's correct.py with:\n"
              "      check --ci --base origin/main\n"
              "  - The starter row is replayed, not yet certified on the real harness: replace its\n"
              "    `canary: {none, ticket}` ticket with one of yours, or write canary cases and run\n"
              "    `correct.py canary run`.")
    elif status != 0 and wrote:
        print(f"\ncorrect init: the files are written, and the replay exits {status}; its output is above. A "
              "FAIL row there is a gate or a hook this repository already has that no row accounts for, or a "
              "row that does not hold: add a row for each (a `gap` row with a ticket is a valid start), then "
              "run `correct.py check` again. Output with no rows means the runner itself stopped.",
              file=sys.stderr)
    elif status != 0:
        print(f"\ncorrect init: the replay exits {status}; its output is above. init does not change a "
              "registry that is there, so it does not repair one either. If a row says `not registered` "
              "or its script is missing, something init installed was removed: restore it from version "
              "control, or delete the registry and run init again to write the starter files anew. "
              "Otherwise fix the row or the enforcer the FAIL names.", file=sys.stderr)
    return status


def on_registry(root: Path) -> int:
    """init on a registry that is there: replay it, write nothing. The status is the replay's."""
    need_registry(root, [])
    return replay(root, wrote=False)


def init(root: Path, args: list[str]) -> int:
    unknown = [a for a in args if a not in ("--dry-run", "--force")]
    if unknown:
        raise Refused(f"init does not take {' '.join(unknown)}")
    dry, force = "--dry-run" in args, "--force" in args
    if git_toplevel(root) != root:
        raise Refused(f"{root} is not the top of a git checkout; run init at the repository root")
    need_yaml()  # also on a dry run: it reports what the real run would do, and that run would stop here
    registry = governance_file(root, "rules.yaml")
    if registry.exists() and not registry.is_file():
        raise Refused(f"{registry.relative_to(root)} exists and is not a regular file; nothing written")
    if registry.exists():
        # Set up already. Nothing is written, and the answer is still the replay's: a registry
        # that exists and does not hold is not a success. That is true of a dry run too: with
        # nothing to write, the dry run and the real run are the same run.
        print(f"correct init: {registry.relative_to(root)} exists, so this repository already has a "
              "registry. Nothing written.")
        return on_registry(root)

    try:
        writes, kept, conflicts = plan(root)
        stops = blocked(root, writes)
    except OSError as exc:
        raise Refused(f"could not read the repository's current state ({exc}); nothing written") from exc
    if stops:
        raise Refused("nothing written. " + "; ".join(stops))
    if conflicts and not force:
        for line in conflicts:
            print(f"correct init: {line}", file=sys.stderr)
        print("correct init: nothing written. Move those files aside, or pass --force to replace them "
              "with the skill's copies.", file=sys.stderr)
        return 2
    for path, _content, _exe in writes:
        print(f"  {'would write' if dry else 'write'}  {path.relative_to(root)}")
    for line in kept:
        print(f"  keep   {line}")
    if dry:
        print("correct init: dry run, nothing written.")
        return 0
    done: list[str] = []
    # The registry this run writes is the plan's last write. Its path is the plan's, not the
    # one looked at above: the look says where a registry would be FOUND, and with an empty
    # new-style folder that is the old folder, while the plan writes into the new one.
    target = writes[-1][0]
    for path, content, executable in writes:
        try:
            # The registry is created, never replaced. It was not there when this run looked;
            # if another init has published one since, that one stands, whatever is in it.
            left = write_file(path, content, executable, new=path == target)
        except NotCreated as why:
            say_left(target.parent.relative_to(root), why.left)
            name, before = target.relative_to(root), f"Written before it: {', '.join(done) or 'nothing'}."
            if isinstance(why, NotLinked):
                raise Refused(f"the link that creates {name} answered with an error ({why}). A registry may "
                              f"be at that name all the same: this run did not look. {before} The starter "
                              "hook and its settings entry are in place.") from why
            print(f"correct init: the link that creates {name} answered that the name is taken. What is "
                  f"there is kept. {before}", flush=True)
            try:
                a_file = stat.S_ISREG(os.stat(target).st_mode)
            except FileNotFoundError:  # a link to nothing
                a_file = False
            except OSError as unreadable:
                raise Refused(f"what is at {name} could not be read ({unreadable}).") from why
            if not a_file:
                raise Refused(f"what is at {name} is not a file.") from why
            replayable(target)  # this file, at this name: no second search for where a registry might be
            return replay(root, wrote=False)
        except OSError as exc:
            raise Refused(f"could not write {path.relative_to(root)} ({exc}). Written before it: "
                          f"{', '.join(done) or 'nothing'}. The registry is written last and was not "
                          "written, so the repository is not set up; fix the cause and run init again."
                          ) from exc
        done.append(str(path.relative_to(root)))
        say_left(path.parent.relative_to(root), left)
    return replay(root, wrote=True)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0 if argv else 2
    command, rest = argv[0], argv[1:]
    if command not in ("init", "check", "canary"):
        print(f"correct: unknown command {command!r}; it takes init, check or canary", file=sys.stderr)
        return 2
    try:
        # The arguments are read once. --root and its value come out first, and only what is left
        # is searched for --help: a --root whose directory is missing takes the next word as its
        # value with or without --help, and is refused as not a directory. (Round 3 looked for
        # --help first and parsed --root second; `check --root --help` then ran the checker on
        # the current directory.)
        named, rest = split_root(rest)
        if named == "":
            raise Refused("--root needs a directory, and got an empty value")
        tool = "rules_check.py" if command == "check" else "rules_canary.py"
        if "-h" in rest or "--help" in rest:
            if command == "init":
                print(__doc__)
                return 0
            need_yaml()  # the tools import it before they parse their arguments
            # No repository has been resolved here, so the tool is handed --help and nothing
            # else of the caller's: whatever was typed beside it, the tool can only print.
            return run_tool(tool, Path.cwd(), ["run", "--help"] if tool == "rules_canary.py" and "run" in rest
                            else ["--help"])
        root = resolve_root(named)
        if command == "init":
            return init(root, rest)
        need_yaml()
        need_registry(root, rest, flag=command == "check")
        return run_tool(tool, root, rest)
    except Refused as exc:
        print(f"correct {command}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
