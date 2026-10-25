#!/usr/bin/env bash
# Build assets/the-new-baseline.pdf from references/playbook.md.
# Requires: pandoc, and Google Chrome or Chromium (set CHROME to override the path).
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
chrome="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

cat > "$tmp/cover.html" <<HTML
<div class="cover">
  <div class="kicker">A WORKING PLAYBOOK</div>
  <h1>The New Baseline</h1>
  <div class="sub">Agentic work and agentic leadership: contracts, checks, rituals and templates.</div>
  <img src="$here/assets/new-baseline.png" alt="The new baseline: an exploded stack of layers from agent loops at the base to intent at the top.">
  <div class="by">Carlos D. Escobar-Valbuena · broomva.tech</div>
  <div class="install">npx skills add broomva/skills --skill agentic-leadership</div>
</div>
HTML

# Drop only the YAML front matter; the body keeps its own heading and intro.
awk 'NR==1 && /^---$/ {fm=1; next} fm && /^---$/ {fm=0; next} !fm' \
  "$here/references/playbook.md" > "$tmp/body.md"

pandoc "$tmp/body.md" -f gfm -t html5 -s --metadata pagetitle="The New Baseline" \
  --css "$here/assets/print.css" --include-before-body "$tmp/cover.html" \
  -o "$tmp/playbook.html"

"$chrome" --headless=new --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$here/assets/the-new-baseline.pdf" "file://$tmp/playbook.html" 2>/dev/null

echo "$here/assets/the-new-baseline.pdf"
