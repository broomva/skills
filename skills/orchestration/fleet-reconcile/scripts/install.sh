#!/bin/bash
# install.sh: install, or remove, the hourly fleet-reconcile tick for one scope.
# The owner runs it; nothing in this build loads the job on its own.
#
#   bash scripts/install.sh --scope broomva              install (or reinstall) and load
#   bash scripts/install.sh --scope broomva --dry-run    print what it would do, change nothing
#   bash scripts/install.sh --scope broomva --uninstall  unload, and move the plist to the Trash
#
# The job runs a PINNED COPY, not this checkout: fleet-reconcile's and
# ctx-core's scripts and templates are copied to
# ~/.local/share/fleet-reconcile/releases/<commit>/, and the plist points
# there. A branch switch or an edit in the checkout doesn't change what launchd
# runs; installing again does. A checkout with uncommitted changes in either
# skill is refused unless --force (the release is then named <commit>-dirty-<time>).
#
# Idempotent: installing again renders the plist and reloads the job (bootout,
# wait for it to go, bootstrap). The config (~/.config/ctx/fleet.json) is
# seeded from templates/fleet.json.example only when it doesn't exist, mode
# 0600, and never overwritten. Uninstall leaves the config, the releases and
# the state dir (reports, ledger).
#
# Test seams: FLEET_LAUNCHCTL, FLEET_LAUNCH_AGENTS_DIR, FLEET_CONFIG,
# FLEET_TRASH, FLEET_RELEASES_DIR.
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
    (-h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    (*) echo "install.sh: unknown argument $1" >&2; exit 2 ;;
  esac
done
case "$SCOPE" in
  ([a-z0-9]*) : ;;
  (*) echo "install.sh: --scope <id> is required (a scope in ~/.config/ctx/scopes.yaml)" >&2; exit 2 ;;
esac

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CTX_DIR="$(cd "$SKILL_DIR/../ctx-core" && pwd)"
LABEL="com.broomva.fleet-reconcile.$SCOPE"
AGENTS="${FLEET_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
PLIST="$AGENTS/$LABEL.plist"
LAUNCHCTL="${FLEET_LAUNCHCTL:-launchctl}"
DOMAIN="gui/$(id -u)"
CONFIG="${FLEET_CONFIG:-$HOME/.config/ctx/fleet.json}"
RELEASES="${FLEET_RELEASES_DIR:-$HOME/.local/share/fleet-reconcile/releases}"
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

# bootout, then wait until launchd has let the job go: a bootstrap straight
# after a bootout can fail with "5: Input/output error" while it finishes.
unload() {
  run "$LAUNCHCTL" bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  [ "$DRY" = 1 ] && return 0
  local i=0
  while [ $i -lt 20 ] && "$LAUNCHCTL" print "$DOMAIN/$LABEL" >/dev/null 2>&1; do
    sleep 0.5
    i=$((i + 1))
  done
}

if [ "$MODE" = uninstall ]; then
  unload
  if [ -f "$PLIST" ]; then to_trash "$PLIST"; else echo "install.sh: no plist at $PLIST"; fi
  echo "install.sh: uninstalled $LABEL. Left in place: $CONFIG, $RELEASES and the scope's state dir."
  exit 0
fi

# ── which code the job will run ──────────────────────────────────────────────
COMMIT=$(git -C "$SKILL_DIR" rev-parse --short=12 HEAD 2>/dev/null || echo "")
DIRTY=$(git -C "$SKILL_DIR" status --porcelain -- "$SKILL_DIR" "$CTX_DIR" 2>/dev/null | grep -v '__pycache__' || true)
if [ -z "$COMMIT" ]; then
  if [ "$FORCE" != 1 ]; then
    echo "install.sh: $SKILL_DIR is not in a git checkout; pass --force to install it anyway" >&2
    exit 2
  fi
  COMMIT="nogit"
fi
REL_NAME="$COMMIT"
if [ -n "$DIRTY" ]; then
  if [ "$FORCE" != 1 ]; then
    echo "install.sh: uncommitted changes in fleet-reconcile or ctx-core; commit them, or pass --force:" >&2
    echo "$DIRTY" | head -10 >&2
    exit 2
  fi
  REL_NAME="$COMMIT-dirty-$(date +%s)"
fi
REL="$RELEASES/$REL_NAME"
TICK="$REL/orchestration/fleet-reconcile/scripts/tick.sh"

# ── the config: seeded once, then checked ────────────────────────────────────
if [ ! -f "$CONFIG" ]; then
  echo "install.sh: seeding $CONFIG from templates/fleet.json.example (report mode, dry_run 1)"
  if [ "$DRY" != 1 ]; then
    mkdir -p "$(dirname "$CONFIG")"
    (umask 077 && cp "$SKILL_DIR/templates/fleet.json.example" "$CONFIG")
    chmod 600 "$CONFIG"
  fi
fi
CHECK_CONFIG="$CONFIG"
[ -f "$CHECK_CONFIG" ] || CHECK_CONFIG="$SKILL_DIR/templates/fleet.json.example"
if ! FLEET_CONFIG="$CHECK_CONFIG" "$SKILL_DIR/scripts/fleet" config-check "$SCOPE"; then
  echo "install.sh: config-check failed for $SCOPE; fix $CONFIG and run this again" >&2
  exit 1
fi

# ── the pinned copy ──────────────────────────────────────────────────────────
if [ "$DRY" = 1 ]; then
  echo "would copy: fleet-reconcile and ctx-core (scripts, templates) at $REL_NAME -> $REL"
elif [ ! -d "$REL" ]; then
  python3 - "$SKILL_DIR" "$CTX_DIR" "$REL" "$REL_NAME" <<'PY'
import os, shutil, sys, time
skill, ctx, rel, name = sys.argv[1:5]
tmp = rel + ".partial"
ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
shutil.rmtree(tmp, ignore_errors=True)  # a half-made copy of our own from an interrupted install
for src, dst in ((os.path.join(skill, "scripts"), "orchestration/fleet-reconcile/scripts"),
                 (os.path.join(skill, "templates"), "orchestration/fleet-reconcile/templates"),
                 (os.path.join(ctx, "scripts"), "orchestration/ctx-core/scripts")):
    shutil.copytree(src, os.path.join(tmp, dst), ignore=ignore)
with open(os.path.join(tmp, "RELEASE"), "w") as fh:
    fh.write("release %s\nsource %s\ninstalled %s\n" % (name, skill, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
os.replace(tmp, rel)
PY
  echo "install.sh: pinned $REL_NAME at $REL"
else
  echo "install.sh: $REL already exists; reusing it"
fi

# ── the plist ─────────────────────────────────────────────────────────────────
TMP=$(mktemp "${TMPDIR:-/tmp}/fleet-plist.XXXXXX")
trap 'rm -f "$TMP"' EXIT
FLEET_PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
python3 - "$SKILL_DIR/templates/launchd.plist.template" "$TMP" \
  "$LABEL" "$TICK" "$SCOPE" "$CONFIG" "$HOME" "$FLEET_PATH" <<'PY'
import sys
from xml.sax.saxutils import escape
src, dst = sys.argv[1], sys.argv[2]
values = dict(zip(("LABEL", "TICK", "SCOPE", "CONFIG", "HOME", "PATH"), sys.argv[3:9]))
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
unload
if [ "$DRY" != 1 ]; then
  ok=0
  for _ in 1 2 3; do
    if "$LAUNCHCTL" bootstrap "$DOMAIN" "$PLIST"; then ok=1; break; fi
    sleep 1
  done
  if [ "$ok" != 1 ]; then
    echo "install.sh: launchctl bootstrap failed three times; the plist is at $PLIST" >&2
    exit 1
  fi
else
  echo "would run: $LAUNCHCTL bootstrap $DOMAIN $PLIST"
  echo "install.sh: dry run; nothing was changed."
  exit 0
fi
echo "install.sh: $LABEL installed from $REL_NAME; it ticks hourly (report-only in phase 1)."
echo "  run one now:   launchctl kickstart $DOMAIN/$LABEL"
echo "  its asks:      $REL/orchestration/fleet-reconcile/scripts/fleet asks --scope $SCOPE"
echo "  remove it:     bash $SKILL_DIR/scripts/install.sh --scope $SCOPE --uninstall"
