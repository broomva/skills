#!/bin/bash
# install.sh: install, or remove, the hourly fleet-reconcile tick for one scope.
# The owner runs it; no session loads the job itself.
#
#   bash scripts/install.sh --scope broomva              install (or reinstall) and load
#   bash scripts/install.sh --scope broomva --dry-run    print what it would do, change nothing
#   bash scripts/install.sh --scope broomva --uninstall  unload, and move the plist to the Trash
#
# Idempotent: installing again re-renders the plist and reloads the job
# (bootout, then bootstrap). The config (~/.config/ctx/fleet.json) is seeded
# from templates/fleet.json.example only when it doesn't exist, mode 0600, and
# never overwritten; uninstall leaves it and the state dir (reports, ledger).
#
# The plist points at this checkout's scripts/tick.sh, so run it from the
# checkout the tick should use (after a merge, the owner's ~/broomva/skills),
# not from a worktree that will be removed.
#
# Test seams: FLEET_LAUNCHCTL, FLEET_LAUNCH_AGENTS_DIR, FLEET_CONFIG, FLEET_TRASH.
set -euo pipefail

SCOPE=""
MODE=install
DRY=0
FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    (--scope) SCOPE=${2:-}; shift 2 ;;
    (--scope=*) SCOPE=${1#--scope=}; shift ;;
    (--uninstall) MODE=uninstall; shift ;;
    (--dry-run) DRY=1; shift ;;
    (--force) FORCE=1; shift ;;
    (-h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    (*) echo "install.sh: unknown argument $1" >&2; exit 2 ;;
  esac
done
case "$SCOPE" in
  ([a-z0-9]*) : ;;
  (*) echo "install.sh: --scope <id> is required (a scope in ~/.config/ctx/scopes.yaml)" >&2; exit 2 ;;
esac

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.broomva.fleet-reconcile.$SCOPE"
AGENTS="${FLEET_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
PLIST="$AGENTS/$LABEL.plist"
LAUNCHCTL="${FLEET_LAUNCHCTL:-launchctl}"
DOMAIN="gui/$(id -u)"
CONFIG="${FLEET_CONFIG:-$HOME/.config/ctx/fleet.json}"
export FLEET_CONFIG="$CONFIG"

run() {
  if [ "$DRY" = 1 ]; then echo "would run: $*"; else "$@"; fi
}

to_trash() {
  if [ -n "${FLEET_TRASH:-}" ]; then
    run "$FLEET_TRASH" "$1"
  elif command -v trash >/dev/null 2>&1; then
    run trash "$1"
  else
    run mv "$1" "$HOME/.Trash/$(basename "$1").$(date +%s)"
  fi
}

if [ "$MODE" = uninstall ]; then
  run "$LAUNCHCTL" bootout "$DOMAIN/$LABEL" 2>/dev/null || echo "install.sh: $LABEL was not loaded"
  if [ -f "$PLIST" ]; then to_trash "$PLIST"; else echo "install.sh: no plist at $PLIST"; fi
  echo "install.sh: uninstalled $LABEL. Left in place: $CONFIG and the scope's state dir."
  exit 0
fi

case "$SKILL_DIR" in
  (/tmp/*|/private/tmp/*|"$HOME"/.paseo/worktrees/*|*/.claude/worktrees/*)
    if [ "$FORCE" != 1 ]; then
      echo "install.sh: $SKILL_DIR looks like a temporary checkout; the job would break when it goes." >&2
      echo "install.sh: run this from the checkout the tick should use, or pass --force." >&2
      exit 2
    fi ;;
esac

if [ ! -f "$CONFIG" ]; then
  echo "install.sh: seeding $CONFIG from templates/fleet.json.example (report mode, dry_run 1)"
  if [ "$DRY" != 1 ]; then
    mkdir -p "$(dirname "$CONFIG")"
    (umask 077 && cp "$SKILL_DIR/templates/fleet.json.example" "$CONFIG")
    chmod 600 "$CONFIG"
  fi
fi
if [ "$DRY" != 1 ] && ! "$SKILL_DIR/scripts/fleet" config-check "$SCOPE"; then
  echo "install.sh: config-check failed for $SCOPE; fix $CONFIG and run this again" >&2
  exit 1
fi

TMP=$(mktemp "${TMPDIR:-/tmp}/fleet-plist.XXXXXX")
trap 'rm -f "$TMP"' EXIT
FLEET_PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
python3 - "$SKILL_DIR/templates/launchd.plist.template" "$TMP" \
  "$LABEL" "$SKILL_DIR" "$SCOPE" "$CONFIG" "$HOME" "$FLEET_PATH" <<'PY'
import sys
from xml.sax.saxutils import escape
src, dst = sys.argv[1], sys.argv[2]
values = dict(zip(("LABEL", "SKILL_DIR", "SCOPE", "CONFIG", "HOME", "PATH"), sys.argv[3:9]))
text = open(src, encoding="utf-8").read()
for key, value in values.items():
    text = text.replace("{{%s}}" % key, escape(value))
assert "{{" not in text, "unrendered placeholder"
open(dst, "w", encoding="utf-8").write(text)
PY
if command -v plutil >/dev/null 2>&1; then
  plutil -lint "$TMP" >/dev/null
else
  python3 -c 'import plistlib, sys; plistlib.load(open(sys.argv[1], "rb"))' "$TMP"
fi

if [ "$DRY" = 1 ]; then
  echo "would write: $PLIST"
  cat "$TMP"
else
  mkdir -p "$AGENTS"
  install -m 0644 "$TMP" "$PLIST"
fi
run "$LAUNCHCTL" bootout "$DOMAIN/$LABEL" 2>/dev/null || true
run "$LAUNCHCTL" bootstrap "$DOMAIN" "$PLIST"
if [ "$DRY" = 1 ]; then echo "install.sh: dry run; nothing was changed."; exit 0; fi
echo "install.sh: $LABEL installed; it ticks hourly (report-only in phase 1)."
echo "  run one now:   launchctl kickstart $DOMAIN/$LABEL"
echo "  its asks:      $SKILL_DIR/scripts/fleet asks --scope $SCOPE (reports: the state dir's ticks/)"
echo "  remove it:     bash $SKILL_DIR/scripts/install.sh --scope $SCOPE --uninstall"
