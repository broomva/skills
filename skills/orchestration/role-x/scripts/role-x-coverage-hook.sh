#!/usr/bin/env bash
# role-x-coverage-hook.sh — Claude Code SessionStart hook for v0.4.1 onwards.
#
# Once-per-session-ish nudge surfacing registry health when it looks under-
# covered. Always exits 0; never blocks. Cooldown via stamp file.
#
# Installed by: `npx skills add broomva/role-x`
# Canonical location: ~/.agents/skills/role-x/scripts/role-x-coverage-hook.sh
# Wired from: $WORKSPACE/.claude/settings.json under "SessionStart"

set -eu

PYTHON_BIN="${ROLE_X_PYTHON:-python3}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROLE_X_PY="$SCRIPT_DIR/role-x.py"

# Cooldown — at most one report per N hours (default 24h)
COOLDOWN_HOURS="${ROLE_X_COVERAGE_COOLDOWN_HOURS:-24}"
STAMP_FILE="${HOME}/.config/broomva/role/coverage-stamp"

# Graceful-fail if Python or the CLI are absent
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  exit 0
fi
if [ ! -f "$ROLE_X_PY" ]; then
  exit 0
fi
if ! "$PYTHON_BIN" -c "import yaml" >/dev/null 2>&1; then
  exit 0
fi

# Cooldown check (Darwin and Linux paths)
if [ -f "$STAMP_FILE" ]; then
  if [ "$(uname)" = "Darwin" ]; then
    last_run=$(stat -f %m "$STAMP_FILE" 2>/dev/null || echo 0)
  else
    last_run=$(stat -c %Y "$STAMP_FILE" 2>/dev/null || echo 0)
  fi
  now=$(date +%s)
  elapsed=$((now - last_run))
  cooldown=$((COOLDOWN_HOURS * 3600))
  if [ "$elapsed" -lt "$cooldown" ]; then
    exit 0
  fi
fi

# Run the coverage summary. The subcommand stays silent when healthy.
"$PYTHON_BIN" "$ROLE_X_PY" coverage --since 7d 2>/dev/null || true

# Refresh the stamp regardless of whether we printed anything
mkdir -p "$(dirname "$STAMP_FILE")"
touch "$STAMP_FILE"

exit 0
