#!/usr/bin/env bash
#
# install-skill.sh — register the SKILL.md surface only (no Python CLI).
#
# Use this when you want an agent (Claude Code / Cursor / Gemini CLI / etc.)
# to *see* the Health skill so it can route work to it, but you don't yet
# want to install the Python CLI. Useful for:
#
#   - Read-only browsing of the skill's workflow docs from an agent context
#   - Multi-agent setups where the CLI runs on a single machine but agents
#     on other machines need the manifest for discovery
#   - CI scenarios that need SKILL.md present but not the binary
#
# Drops the manifest into every agent's known skills dir.
#
# Usage:
#   bash install-skill.sh                              # install to all detected agents
#   bash install-skill.sh --agent claude-code,cursor   # specific agents
#   bash install-skill.sh --uninstall                  # remove
#
# Internally this is a thin wrapper around `npx skills add --local` once
# the standalone repo is published; for the curl-piped path we bootstrap
# without npm by copying files directly.

set -euo pipefail

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_INFO='\033[0;36m'; C_OK='\033[0;32m'; C_WARN='\033[0;33m'; C_OFF='\033[0m'
else
  C_INFO=''; C_OK=''; C_WARN=''; C_OFF=''
fi
log()  { printf "${C_INFO}▸${C_OFF} %s\n" "$*"; }
ok()   { printf "${C_OK}✓${C_OFF} %s\n" "$*"; }
warn() { printf "${C_WARN}!${C_OFF} %s\n" "$*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_NAME="health"

# Files to bundle into each agent's skill dir. The Python `src/`, `tests/`,
# `Makefile`, `pyproject.toml` are intentionally excluded — they're only
# needed by `install.sh` (the CLI install path), not by the agent-discovery
# path.
SKILL_FILES=("SKILL.md" "README.md" "Workflows" "References" "LICENSE")

# Known agent skill directories. Adding a new agent? Add a line here.
AGENT_DIRS=(
  "$HOME/.claude/skills"
  "$HOME/.cursor/skills"
  "$HOME/.gemini/skills"
  "$HOME/.agents/skills"      # the npx-skills universal install target
)

UNINSTALL=0
declare -a TARGET_AGENTS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --uninstall) UNINSTALL=1; shift ;;
    --agent)
      [ $# -lt 2 ] && { warn "--agent needs a value"; exit 2; }
      IFS=',' read -r -a TARGET_AGENTS <<< "$2"
      shift 2
      ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# //; s/^#$//'
      exit 0
      ;;
    *) warn "Unknown arg: $1"; exit 2 ;;
  esac
done

# Resolve target dirs.
declare -a TARGET_DIRS=()
if [ ${#TARGET_AGENTS[@]} -gt 0 ]; then
  for a in "${TARGET_AGENTS[@]}"; do
    case "$a" in
      claude-code|claude) TARGET_DIRS+=("$HOME/.claude/skills") ;;
      cursor)             TARGET_DIRS+=("$HOME/.cursor/skills") ;;
      gemini|gemini-cli)  TARGET_DIRS+=("$HOME/.gemini/skills") ;;
      universal|all)      TARGET_DIRS+=("$HOME/.agents/skills") ;;
      *) warn "Unknown agent: $a (skipped)" ;;
    esac
  done
else
  # Auto-detect: install to every agent whose parent dir already exists.
  for d in "${AGENT_DIRS[@]}"; do
    if [ -d "$(dirname "$d")" ]; then
      TARGET_DIRS+=("$d")
    fi
  done
fi

if [ ${#TARGET_DIRS[@]} -eq 0 ]; then
  warn "No agent skill dirs detected. Use --agent to install to a specific one."
  exit 1
fi

for target_root in "${TARGET_DIRS[@]}"; do
  target="$target_root/$SKILL_NAME"

  if [ "$UNINSTALL" -eq 1 ]; then
    if [ -e "$target" ] || [ -L "$target" ]; then
      rm -rf "$target"
      ok "Removed $target"
    else
      log "Skipped $target (not present)"
    fi
    continue
  fi

  mkdir -p "$target_root"
  # Clean previous install (idempotent re-run)
  rm -rf "$target"
  mkdir -p "$target"

  for f in "${SKILL_FILES[@]}"; do
    src="$SCRIPT_DIR/$f"
    if [ -e "$src" ]; then
      cp -R "$src" "$target/"
    fi
  done
  ok "Installed SKILL.md surface to $target"
done

if [ "$UNINSTALL" -eq 0 ]; then
  printf "\n${C_OK}Skill manifest installed.${C_OFF}\n"
  printf "Agents can now discover the ${C_INFO}Health${C_OFF} skill.\n"
  printf "Install the CLI separately with: ${C_INFO}bash install.sh${C_OFF}\n"
fi
