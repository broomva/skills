#!/usr/bin/env bash
set -euo pipefail

skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target_dir="$(mktemp -d)"
trap 'rm -rf "$target_dir"' EXIT

python3 "$skill_dir/scripts/materialize.py" materialize "$target_dir" --profile web
python3 "$skill_dir/scripts/materialize.py" verify "$target_dir" --profile web
recommend_output="$(python3 "$skill_dir/scripts/materialize.py" recommend "$target_dir")"
grep -Fq 'recommended profile: web' <<<"$recommend_output"
dry_run_output="$(python3 "$skill_dir/scripts/materialize.py" materialize "$target_dir" --profile web --dry-run)"
grep -Fq 'dry-run plan: profile=web' <<<"$dry_run_output"
verbose_output="$(python3 "$skill_dir/scripts/materialize.py" materialize "$target_dir" --profile web --dry-run --verbose)"
grep -Fq 'paths:' <<<"$verbose_output"
help_output="$(python3 "$skill_dir/scripts/materialize.py" materialize --help)"
grep -Fq 'default: foundation' <<<"$help_output"
test -f "$target_dir/DESIGN.md"
test -f "$target_dir/design-system/broomva/broomva-foundation.css"
test -f "$target_dir/design-system/broomva/tokens.json"
test -f "$target_dir/design-system/broomva/styles.css"
test -f "$target_dir/design-system/broomva/fonts/OFL.txt"
test -f "$target_dir/design-system/broomva/index.js"
test -f "$target_dir/design-system/broomva/components/core/Button.jsx"
test ! -e "$target_dir/design-system/broomva/components/work"
test ! -e "$target_dir/design-system/broomva/tokens/motion.css"
