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
if ! "$PYTHON_BIN" -c "import yaml" >/dev/null 2>&1; then
  exit 0
fi

# Resolve workspace: prefer Claude Code's CLAUDE_PROJECT_DIR env, else $PWD.
WORKSPACE="${CLAUDE_PROJECT_DIR:-$PWD}"

# Stream stdin (the hook JSON payload) through to the intake subcommand.
# `intake` always exits 0; we still guard with `|| true` so the hook never
# fails the user's turn for any unexpected reason.
exec "$PYTHON_BIN" "$ROLE_X_PY" intake --workspace "$WORKSPACE" || true
