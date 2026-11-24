#!/usr/bin/env -S python3 -I
"""correct.py — set a repository up with a rule registry, and replay it.

  correct.py init   [--root DIR] [--dry-run] [--force]
      Give a repository its registry: the registry file with one proven rule
      (branch first), that rule's enforcer and its fixtures under scripts/, a
      governance policy file if there is none, and the hook entry in
      .claude/settings.json. Then replay the registry. Exits with the replay's
      status, so a repository whose existing gates and hooks have no row yet
      exits 1 and lists them.
  correct.py check  [--root DIR] [runner options ...]
      Replay every row against its real enforcer (scripts/rules_check.py in this
      skill): --ci, --json, --markdown, --only ID ..., --base REF, --replay-only.
  correct.py canary [--root DIR] [canary options ...]
      The real-harness canary (scripts/rules_canary.py in this skill).

The repository is --root, else $RULES_CHECK_ROOT, else the git checkout the
current directory is in. The runner and the canary run from this skill's
directory, outside the repository they judge; the enforcers and the registry
rows are the repository's own files.

Exit codes: 0 done and the replay passed; 1 the replay failed; 2 the command
could not run (no repository, an unreadable settings file, a file init would
have to overwrite).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
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


class Refused(Exception):
    """The command cannot run; the message names what to do."""


def git_toplevel(cwd: Path) -> Path | None:
    proc = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True, check=False)
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


def runs_enforcer(settings: dict) -> bool:
    for group in (settings.get("hooks") or {}).get("PreToolUse") or []:
        for hook in (group or {}).get("hooks") or []:
            if f"scripts/{ENFORCER}" in str((hook or {}).get("command", "")):
                return True
    return False


def plan(root: Path) -> tuple[list[tuple[Path, bytes, bool]], list[str], list[str]]:
    """(files to write as (path, content, executable), files left as they are, conflicts)."""
    writes: list[tuple[Path, bytes, bool]] = []
    kept: list[str] = []
    conflicts: list[str] = []

    for name in SCRIPT_FILES:
        target = root / "scripts" / name
        content = (HERE / name).read_bytes()
        if not target.exists():
            writes.append((target, content, name in EXECUTABLE))
        elif target.read_bytes() == content:
            kept.append(f"scripts/{name} (already this version)")
        else:
            conflicts.append(f"scripts/{name} exists and differs from the skill's copy")
            writes.append((target, content, name in EXECUTABLE))

    gov = governance_dir(root)
    writes.append((gov / "rules.yaml", (TEMPLATES / "rules.yaml").read_bytes(), False))
    policy = governance_file(root, "policy.yaml")
    if policy.exists():
        kept.append(f"{policy.relative_to(root)} (yours; the replay reads its gates.hard)")
    else:
        writes.append((gov / "policy.yaml", POLICY.encode(), False))

    settings_path = root / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except (OSError, ValueError) as exc:
            raise Refused(f"{settings_path} is not readable JSON ({exc}); fix it, then run init again") from exc
        if not isinstance(settings, dict):
            raise Refused(f"{settings_path} is not a JSON object; fix it, then run init again")
    else:
        settings = {}
    if runs_enforcer(settings):
        kept.append(".claude/settings.json (already runs the enforcer)")
    else:
        hooks = settings.setdefault("hooks", {})
        if not isinstance(hooks, dict) or not isinstance(hooks.setdefault("PreToolUse", []), list):
            raise Refused(f"{settings_path}: `hooks.PreToolUse` is not a list; fix it, then run init again")
        hooks["PreToolUse"].append(HOOK_GROUP)
        writes.append((settings_path, (json.dumps(settings, indent=2) + "\n").encode(), False))
    return writes, kept, conflicts


def init(root: Path, args: list[str]) -> int:
    unknown = [a for a in args if a not in ("--dry-run", "--force")]
    if unknown:
        raise Refused(f"init does not take {' '.join(unknown)}")
    dry, force = "--dry-run" in args, "--force" in args
    if git_toplevel(root) != root:
        raise Refused(f"{root} is not the top of a git checkout; run init at the repository root")
    registry = governance_file(root, "rules.yaml")
    if registry.exists():
        print(f"correct init: {registry.relative_to(root)} exists, so this repository already has a "
              "registry. Nothing written. Replay it with `correct.py check`.")
        return 0

    writes, kept, conflicts = plan(root)
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
    for path, content, executable in writes:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        if executable:
            path.chmod(0o755)

    print("\ncorrect init: replaying the registry (correct.py check)\n")
    status = run_tool("rules_check.py", root, [])
    if status == 0:
        print("\ncorrect init: done. The starter rule is installed and its proofs and controls replay.\n"
              "  - From now on an edit on main or master in this repository is refused; work on a branch.\n"
              "  - Commit the new files on a branch. In CI run: correct.py check --ci --base origin/main\n"
              "  - The starter row is replayed, not yet certified on the real harness: replace its\n"
              "    `canary: {none, ticket}` ticket with one of yours, or write canary cases and run\n"
              "    `correct.py canary run`.")
    else:
        print(f"\ncorrect init: the files are written, and the replay exits {status}. Each FAIL above is a "
              "gate or a hook this repository already has that no row accounts for, or a row that does not "
              "hold. Add a row for each (a `gap` row with a ticket is a valid start), then run "
              "`correct.py check` again.", file=sys.stderr)
    return status


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
        return run_tool("rules_check.py" if command == "check" else "rules_canary.py", root, rest)
    except Refused as exc:
        print(f"correct {command}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
