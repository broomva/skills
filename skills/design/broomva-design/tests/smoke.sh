#!/usr/bin/env bash
set -euo pipefail

skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target_dir="$(mktemp -d)"
trap 'rm -rf "$target_dir"' EXIT

python3 "$skill_dir/scripts/materialize.py" materialize "$target_dir" --profile tokens
python3 "$skill_dir/scripts/materialize.py" verify "$target_dir" --profile tokens
test -f "$target_dir/DESIGN.md"
test -f "$target_dir/design-system/broomva/tokens/colors.css"
test -f "$target_dir/design-system/broomva/fonts/OFL.txt"
