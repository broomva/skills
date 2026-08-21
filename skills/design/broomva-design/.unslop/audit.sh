#!/usr/bin/env bash
# The two-gate audit contract (BRO-2197). The archive waivers in waivers.json are check-global,
# so on their own they could mask FUTURE drift in the portable layer (codex finding, skills#179).
# This script is the enforcement: gate 1 runs the portable layer with ZERO waivers — any new
# portable drift fails here regardless of what waivers.json says. Gate 2 is the whole-skill run
# with the archive waivers. Both must exit 0.
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNSLOP="${UNSLOP_SCRIPTS:-$(cd "$SKILL_DIR/../unslop/scripts" 2>/dev/null && pwd || echo "$HOME/.claude/skills/unslop/scripts")}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

echo "── gate 1: assets/portable, NO waivers (the product-neutral floor)"
python3 "$UNSLOP/unslop_survey.py" "$SKILL_DIR/assets/portable" --detect --json "$TMP/portable.json" --md "$TMP/portable.md"
python3 "$UNSLOP/unslop_gate.py" "$SKILL_DIR/assets/portable" --manifest "$TMP/portable.json" --no-render

echo "── gate 2: whole skill, archive waivers (the boundary)"
python3 "$UNSLOP/unslop_survey.py" "$SKILL_DIR" --detect --json "$TMP/skill.json" --md "$TMP/skill.md"
python3 "$UNSLOP/unslop_gate.py" "$SKILL_DIR" --manifest "$TMP/skill.json" --waivers "$SKILL_DIR/.unslop/waivers.json" --no-render

echo "audit: both gates CLEAR"
