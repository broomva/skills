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
could not run (no repository, an unreadable settings file, a file init would
have to overwrite, a path that leaves the repository). On 2, init has written
nothing unless it says which files it wrote.
"""
from __future__ import annotations

import json
import os
import site
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


def take_root(argv: list[str]) -> tuple[Path, list[str]]:
    """(the repository, the remaining arguments). --root DIR or --root=DIR, anywhere."""
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
    if named == "":
        raise Refused("--root needs a directory, and got an empty value")
    named = named or os.environ.get("RULES_CHECK_ROOT")
    if named:
        root = Path(named).expanduser().resolve()
        if not root.is_dir():
            raise Refused(f"{root} is not a directory")
        return root, rest
    top = git_toplevel(Path.cwd())
    if top is None:
        raise Refused("not inside a git checkout; run it from the repository or pass --root DIR")
    return top, rest


def need_yaml() -> None:
    """The runner and the canary need PyYAML, found the way they find it (the user site is
    added back under -I). Checked before init writes anything: a repository set up and then
    not replayable has an enforcer installed and nothing that says whether it holds."""
    probe = "import site, sys; sys.path.append(site.getusersitepackages()); import yaml"
    proc = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise Refused(f"PyYAML is not importable by {sys.executable}; install it "
                      "(python3 -m pip install --user pyyaml) and run the command again. Nothing written.")


# The registry versions this copy of the runner replays. A registry written for a later
# version may carry fields this runner would ignore, and a row it ignores part of can pass
# without being checked; so an unknown version is refused, not replayed.
REGISTRY_VERSIONS = (1,)


def need_registry(root: Path, args: list[str]) -> None:
    """A registry exists and is a version this copy of the skill replays."""
    named = None
    for i, arg in enumerate(args):
        if arg == "--registry" and i + 1 < len(args):
            named = args[i + 1]
        elif arg.startswith("--registry="):
            named = arg.split("=", 1)[1]
    registry = Path(named).expanduser() if named else governance_file(root, "rules.yaml")
    if not registry.is_file():
        raise Refused(f"there is no registry at {registry}; run init first")
    if site.getusersitepackages() not in sys.path:
        sys.path.append(site.getusersitepackages())
    import yaml  # noqa: PLC0415  (need_yaml ran first)
    try:
        data = yaml.safe_load(registry.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise Refused(f"{registry} is not readable YAML ({exc})") from exc
    version = data.get("version") if isinstance(data, dict) else None
    if version not in REGISTRY_VERSIONS or isinstance(version, bool):
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
    """True when the settings already hold exactly the entry init writes; False when they do
    not mention the enforcer. Anything in between is refused: init does not judge whether some
    other entry runs the enforcer. The replay does that, and "kept, it already runs" followed by
    the replay's "not registered" would be two answers to one question."""
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict) or not isinstance(hooks.setdefault("PreToolUse", []), list):
        raise Refused(f"{settings_path}: `hooks.PreToolUse` is not a list; fix it, then run init again")
    exact = False
    for group in hooks["PreToolUse"]:
        entries = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise Refused(f"{settings_path}: a `hooks.PreToolUse` entry is not {{matcher, hooks: [...]}}; "
                          "fix it, then run init again")
        for entry in entries:
            command = str(entry.get("command", ""))
            if f"scripts/{ENFORCER}" not in command:
                continue
            if command == HOOK_COMMAND and group.get("matcher") == HOOK_GROUP["matcher"]:
                exact = True
            else:
                raise Refused(f"{settings_path} already has a PreToolUse entry that mentions "
                              f"scripts/{ENFORCER} in another form ({command!r}, matcher "
                              f"{group.get('matcher')!r}). Nothing written. Remove that entry and run init "
                              "again; init then writes the one the registry's row expects.")
    return exact


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
    if policy.exists():
        kept.append(f"{policy.relative_to(root)} (yours; the replay reads its gates.hard)")
    else:
        writes.append((gov / "policy.yaml", POLICY.encode(), False))

    settings_path = root / ".claude" / "settings.json"
    settings: dict = {}
    if settings_path.is_file():
        try:
            settings = json.loads(settings_path.read_text())
        except (OSError, ValueError) as exc:
            raise Refused(f"{settings_path} is not readable JSON ({exc}); fix it, then run init again") from exc
        if not isinstance(settings, dict):
            raise Refused(f"{settings_path} is not a JSON object; fix it, then run init again")
    if enforcer_entry(settings, settings_path):
        kept.append(".claude/settings.json (already has the enforcer's entry)")
    else:
        settings["hooks"]["PreToolUse"].append(HOOK_GROUP)
        writes.append((settings_path, (json.dumps(settings, indent=2) + "\n").encode(), False))

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
        for parent in list(rel.parents)[:-1]:  # every directory between the repository and the file
            at = root / parent
            if at.is_symlink():
                out.append(f"{parent}/ is a symlink; init writes only inside the repository ({rel})")
                break
            if at.exists() and not at.is_dir():
                out.append(f"{parent} is a file, and {rel} needs it to be a directory")
                break
            if at.is_dir() and not os.access(at, os.W_OK | os.X_OK):
                out.append(f"{parent}/ is not writable ({rel})")
                break
    return sorted(set(out))


def write_file(path: Path, content: bytes, executable: bool) -> None:
    """Whole or not at all: the content goes to a temporary file beside the target, which then
    replaces it, so an interrupted run never leaves a half-written settings file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # A file that is replaced keeps its own permissions (a settings file kept private stays
    # private); a new one gets the usual ones. Either way the hook ends up executable.
    mode = (path.stat().st_mode & 0o777) if path.is_file() else 0o644
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        os.chmod(tmp, mode | 0o111 if executable else mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


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
              "    `correct.py canary run`.\n"
              "  - To back out: delete the registry, the four files under scripts/ and the PreToolUse\n"
              "    entry that runs scripts/branch-first-hook.py in .claude/settings.json.")
    elif status != 0:
        what = "the files are written, and the" if wrote else "the"
        print(f"\ncorrect init: {what} replay exits {status}; its output is above. A FAIL row there is a "
              "gate or a hook this repository already has that no row accounts for, or a row that does "
              "not hold: add a row for each (a `gap` row with a ticket is a valid start), then run "
              "`correct.py check` again. Output with no rows means the runner itself stopped.",
              file=sys.stderr)
    return status


def init(root: Path, args: list[str]) -> int:
    unknown = [a for a in args if a not in ("--dry-run", "--force")]
    if unknown:
        raise Refused(f"init does not take {' '.join(unknown)}")
    dry, force = "--dry-run" in args, "--force" in args
    if git_toplevel(root) != root:
        raise Refused(f"{root} is not the top of a git checkout; run init at the repository root")
    if not dry:
        need_yaml()
    registry = governance_file(root, "rules.yaml")
    if registry.exists() and not registry.is_file():
        raise Refused(f"{registry.relative_to(root)} exists and is not a regular file; nothing written")
    if registry.exists():
        # Set up already. Nothing is written, and the answer is still the replay's: a registry
        # that exists and does not hold is not a success.
        print(f"correct init: {registry.relative_to(root)} exists, so this repository already has a "
              "registry. Nothing written.")
        if dry:
            return 0
        need_registry(root, [])
        return replay(root, wrote=False)

    writes, kept, conflicts = plan(root)
    stops = blocked(root, writes)
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
    for path, content, executable in writes:
        try:
            write_file(path, content, executable)
        except OSError as exc:
            raise Refused(f"could not write {path.relative_to(root)} ({exc}). Written before it: "
                          f"{', '.join(done) or 'nothing'}. The registry is written last and was not "
                          "written, so the repository is not set up; fix the cause and run init again."
                          ) from exc
        done.append(str(path.relative_to(root)))
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
        root, rest = take_root(rest)
        if command == "init":
            return init(root, rest)
        need_yaml()
        need_registry(root, rest)
        return run_tool("rules_check.py" if command == "check" else "rules_canary.py", root, rest)
    except Refused as exc:
        print(f"correct {command}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
