#!/usr/bin/env bash
#
# install.sh — install `broomva-health` and put the `health` binary on PATH.
#
# Usage:
#   # one-shot from clone:
#   bash install.sh
#
#   # one-shot from web (no clone):
#   curl -fsSL https://raw.githubusercontent.com/broomva/skills/main/skills/health/install.sh | bash
#
# What it does:
#   1. Detects `uv` (preferred) or `python3` ≥ 3.12.
#   2. Creates an isolated venv at $BROOMVA_HEALTH_HOME/.venv
#      (default: ~/.local/share/broomva-health/.venv).
#   3. Editable-installs the package with the [garmin] extra.
#   4. Symlinks the `health` script into $BROOMVA_HEALTH_BIN_DIR
#      (default: ~/.local/bin).
#   5. Idempotent — re-runs upgrade in place; never duplicates state.
#
# Environment overrides:
#   BROOMVA_HEALTH_HOME      install root (default ~/.local/share/broomva-health)
#   BROOMVA_HEALTH_BIN_DIR   symlink target dir (default ~/.local/bin)
#   BROOMVA_HEALTH_EXTRAS    pip extras to install (default "garmin")
#   BROOMVA_HEALTH_SRC       source dir to install from (default: this script's dir)
#   BROOMVA_HEALTH_NO_GARMIN if set, skips the [garmin] extra (core CLI only)
#
# Exit codes: 0 OK · 1 generic failure · 2 missing Python · 3 missing source

set -euo pipefail

# ─── colors ──────────────────────────────────────────────────────────────────
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_INFO='\033[0;36m'; C_OK='\033[0;32m'; C_WARN='\033[0;33m'; C_ERR='\033[0;31m'; C_OFF='\033[0m'
else
  C_INFO=''; C_OK=''; C_WARN=''; C_ERR=''; C_OFF=''
fi
log()  { printf "${C_INFO}▸${C_OFF} %s\n" "$*"; }
ok()   { printf "${C_OK}✓${C_OFF} %s\n" "$*"; }
warn() { printf "${C_WARN}!${C_OFF} %s\n" "$*" >&2; }
fail() { printf "${C_ERR}✗${C_OFF} %s\n" "$*" >&2; exit "${2:-1}"; }

# ─── paths ───────────────────────────────────────────────────────────────────
BROOMVA_HEALTH_HOME="${BROOMVA_HEALTH_HOME:-$HOME/.local/share/broomva-health}"
BROOMVA_HEALTH_BIN_DIR="${BROOMVA_HEALTH_BIN_DIR:-$HOME/.local/bin}"
BROOMVA_HEALTH_EXTRAS="${BROOMVA_HEALTH_EXTRAS:-garmin}"

# Default source dir: directory containing this script (works for `bash install.sh`
# from a clone). When piped from curl, BROOMVA_HEALTH_SRC must be set OR the
# script falls back to a temp clone of the repo.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
BROOMVA_HEALTH_SRC="${BROOMVA_HEALTH_SRC:-$SCRIPT_DIR}"

# ─── source resolution (pyproject must be alongside this script) ─────────────
resolve_source() {
  if [ -f "$BROOMVA_HEALTH_SRC/pyproject.toml" ]; then
    return 0
  fi
  # Piped install (no local source) — clone the broomva/skills monorepo to a
  # temp dir and point at skills/health/ where the package actually lives.
  log "No local source; cloning broomva/skills to a temp dir."
  command -v git >/dev/null 2>&1 || fail "git not found; install git or run from a clone" 3
  local tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/broomva-skills-src.XXXXXX")"
  # Fast path: blobless sparse clone (monorepo is large). Fall back to a plain
  # shallow clone on older git that lacks --filter/--sparse.
  git clone --depth 1 --filter=blob:none --sparse --quiet \
      https://github.com/broomva/skills.git "$tmp" 2>/dev/null \
    || git clone --depth 1 --quiet https://github.com/broomva/skills.git "$tmp" \
    || fail "git clone of broomva/skills failed" 3
  git -C "$tmp" sparse-checkout set skills/health 2>/dev/null || true
  BROOMVA_HEALTH_SRC="$tmp/skills/health"
  [ -f "$BROOMVA_HEALTH_SRC/pyproject.toml" ] \
    || fail "cloned broomva/skills but skills/health/pyproject.toml is missing" 3
  ok "Source: $BROOMVA_HEALTH_SRC (temp clone of broomva/skills)"
}

# ─── python detection ────────────────────────────────────────────────────────
PYTHON_BIN=""

# `uv` is faster + handles Python download itself; prefer it.
USE_UV=0
if command -v uv >/dev/null 2>&1; then
  USE_UV=1
  ok "Found uv: $(uv --version 2>&1 | head -1)"
fi

# Fall back to system python ≥ 3.12. Search common locations beyond $PATH
# (Homebrew, pyenv shims, asdf) because users running this from a sandboxed
# shell or curl-pipe often have $PATH limited to /usr/bin:/bin.
if [ "$USE_UV" -eq 0 ]; then
  EXTRA_DIRS=(
    "/opt/homebrew/bin"
    "/usr/local/bin"
    "$HOME/.pyenv/shims"
    "$HOME/.asdf/shims"
    "$HOME/.local/bin"
  )
  for candidate in python3.14 python3.13 python3.12 python3; do
    bin=""
    if command -v "$candidate" >/dev/null 2>&1; then
      bin="$(command -v "$candidate")"
    else
      for d in "${EXTRA_DIRS[@]}"; do
        if [ -x "$d/$candidate" ]; then
          bin="$d/$candidate"
          break
        fi
      done
    fi
    if [ -n "$bin" ]; then
      ver="$("$bin" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo 0.0)"
      if [ "$(printf '%s\n3.12\n' "$ver" | sort -V | head -1)" = "3.12" ]; then
        PYTHON_BIN="$bin"
        break
      fi
    fi
  done
  if [ -z "$PYTHON_BIN" ]; then
    fail "Python ≥ 3.12 not found (or install \`uv\`). Searched \$PATH and: ${EXTRA_DIRS[*]}" 2
  fi
  ok "Found Python: $PYTHON_BIN ($("$PYTHON_BIN" --version))"
fi

# ─── venv setup ──────────────────────────────────────────────────────────────
resolve_source
[ -f "$BROOMVA_HEALTH_SRC/pyproject.toml" ] \
  || fail "pyproject.toml not found at $BROOMVA_HEALTH_SRC" 3

# ─── durability guard (RC1 / BRO-1552) ───────────────────────────────────────
# Never editable-install (`pip install -e`) from an ephemeral temp dir. A prior
# install pinned the editable `.pth` to a mktemp clone under /tmp; when the OS
# cleared /tmp the link dangled and EVERY invocation died with
# `ModuleNotFoundError: No module named 'broomva_health'`. If the resolved
# source lives under a temp dir (our own temp clone, a curl-pipe, or $TMPDIR),
# copy it to a stable location inside $BROOMVA_HEALTH_HOME and install from
# there so the editable link survives reboots. A source under a user's own
# persistent clone is left untouched (dev edit-loop preserved).
src_is_temp=0
case "$BROOMVA_HEALTH_SRC/" in
  /tmp/*|/private/tmp/*|/var/folders/*) src_is_temp=1 ;;
esac
if [ -n "${TMPDIR:-}" ]; then
  case "$BROOMVA_HEALTH_SRC/" in "${TMPDIR%/}/"*) src_is_temp=1 ;; esac
fi
if [ "$src_is_temp" -eq 1 ]; then
  STABLE_SRC="$BROOMVA_HEALTH_HOME/pkg"
  log "Source under a temp dir — copying to stable $STABLE_SRC (durability; BRO-1552)."
  mkdir -p "$BROOMVA_HEALTH_HOME"
  rm -rf "$STABLE_SRC"
  mkdir -p "$STABLE_SRC"
  cp -R "$BROOMVA_HEALTH_SRC/." "$STABLE_SRC/"
  rm -rf "$STABLE_SRC/.git" "$STABLE_SRC/.venv"
  find "$STABLE_SRC" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  BROOMVA_HEALTH_SRC="$STABLE_SRC"
  ok "Stable source: $BROOMVA_HEALTH_SRC"
fi

log "Source:   $BROOMVA_HEALTH_SRC"
log "Install:  $BROOMVA_HEALTH_HOME"
log "Bin:      $BROOMVA_HEALTH_BIN_DIR/health"

mkdir -p "$BROOMVA_HEALTH_HOME"
mkdir -p "$BROOMVA_HEALTH_BIN_DIR"

VENV="$BROOMVA_HEALTH_HOME/.venv"

if [ -n "${BROOMVA_HEALTH_NO_GARMIN:-}" ]; then
  PKG_SPEC="$BROOMVA_HEALTH_SRC"
  log "Installing without [garmin] extra (BROOMVA_HEALTH_NO_GARMIN set)."
else
  PKG_SPEC="$BROOMVA_HEALTH_SRC[$BROOMVA_HEALTH_EXTRAS]"
  log "Installing with extras: [$BROOMVA_HEALTH_EXTRAS]"
fi

if [ "$USE_UV" -eq 1 ]; then
  log "Creating venv via uv (forces Python ≥ 3.12)"
  uv venv --python ">=3.12" --quiet "$VENV"
  uv pip install --python "$VENV/bin/python" --quiet -e "$PKG_SPEC"
else
  log "Creating venv via python -m venv"
  "$PYTHON_BIN" -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade --quiet pip wheel
  "$VENV/bin/pip" install --quiet -e "$PKG_SPEC"
fi
ok "Package installed into $VENV"

# ─── symlink ─────────────────────────────────────────────────────────────────
HEALTH_BIN="$VENV/bin/health"
[ -x "$HEALTH_BIN" ] || fail "Expected $HEALTH_BIN to exist after install" 1

TARGET="$BROOMVA_HEALTH_BIN_DIR/health"
if [ -L "$TARGET" ] || [ -e "$TARGET" ]; then
  rm -f "$TARGET"
fi
ln -s "$HEALTH_BIN" "$TARGET"
ok "Symlinked $TARGET → $HEALTH_BIN"

# ─── PATH sanity ─────────────────────────────────────────────────────────────
case ":$PATH:" in
  *":$BROOMVA_HEALTH_BIN_DIR:"*) ok "$BROOMVA_HEALTH_BIN_DIR is on \$PATH" ;;
  *)
    warn "$BROOMVA_HEALTH_BIN_DIR is NOT on your PATH."
    warn "Add this to your shell rc:"
    warn "  export PATH=\"$BROOMVA_HEALTH_BIN_DIR:\$PATH\""
    ;;
esac

# ─── verify ──────────────────────────────────────────────────────────────────
log "Verifying installation..."
"$TARGET" --version >/dev/null 2>&1 \
  || fail "Installation completed but \`health --version\` did not run" 1
INSTALLED_VER="$("$TARGET" --version 2>/dev/null)"
ok "broomva-health $INSTALLED_VER installed."

printf "\n${C_OK}Next steps:${C_OFF}\n"
printf "  1. ${C_INFO}health auth login${C_OFF}         — one-time Garmin login (MFA prompted)\n"
printf "  2. ${C_INFO}health doctor${C_OFF}             — verify paths, tokens, repo migration\n"
printf "  3. ${C_INFO}health --format json status${C_OFF} — reflexive snapshot\n"
printf "  4. ${C_INFO}health sync${C_OFF}                — incremental pull\n"
printf "\nSee ${C_INFO}https://github.com/broomva/skills/tree/main/skills/health${C_OFF} for docs.\n"
