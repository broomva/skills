#!/usr/bin/env bash
# role-x-intake-hook.sh — Claude Code UserPromptSubmit hook for bstack P17.
#
# Wires the role-x intake reflex (lens selection + mode decision + event
# capture + agent-context output) into every substantive user prompt.
#
# Always exits 0 (never blocks the user's turn). Graceful-fails if PyYAML
# isn't available or the workspace has no `roles/` directory.
#
# Installed by: `npx skills add broomva/role-x`
# Canonical location: ~/.agents/skills/role-x/scripts/role-x-intake-hook.sh
# Referenced from: $WORKSPACE/.claude/settings.json under "UserPromptSubmit"

set -eu

# -I on every interpreter launch (BRO-2591 P20 r8): this hook runs with the
# session's cwd, so a bare `python -c` would import a yaml.py / json.py committed
# at that repo's root in place of the real module, and `python role-x.py` would
# put this scripts/ dir first. -I drops cwd, the script dir, PYTHONPATH and user
# site-packages; PyYAML may live only in the user site, so the probe below and
# role-x.py re-add that one directory by APPENDING it (the stdlib still wins).
PYTHON_BIN="${ROLE_X_PYTHON:-python3}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROLE_X_PY="$SCRIPT_DIR/role-x.py"

# Graceful-fail if Python or the CLI are not present.
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  exit 0
fi
if [ ! -f "$ROLE_X_PY" ]; then
  exit 0
fi

# Graceful-fail if PyYAML isn't importable in the chosen interpreter.
if ! "$PYTHON_BIN" -I -c "import site, sys; sys.path.append(site.getusersitepackages()); import yaml" >/dev/null 2>&1; then
  exit 0
fi

# Resolve workspace: prefer Claude Code's CLAUDE_PROJECT_DIR env, else $PWD.
WORKSPACE="${CLAUDE_PROJECT_DIR:-$PWD}"

# Stream stdin (the hook JSON payload) through to the intake subcommand.
# `intake` always exits 0, and the guard below makes that hold for ANY failure:
# this is UserPromptSubmit, where exit 2 blocks and erases the user's prompt.
# No `exec`: an exec'd process replaces this shell, so a `|| true` after it
# never ran and role-x.py's own exit code (e.g. 2, "PyYAML required") was the
# hook's.
"$PYTHON_BIN" -I "$ROLE_X_PY" intake --workspace "$WORKSPACE" || true
exit 0
