#!/usr/bin/env bash
# Measure the settings change marker specimen with headless Chrome. Read-only.
# Setup: materialize a `foundation` target, copy settings-change-marker.html and
# settings-change-marker-frame.html into <target>/settings/, serve <target> over HTTP.
# Usage: bash settings-change-marker-measure.sh http://127.0.0.1:8765/settings/
# Headless Chrome has a 500px minimum window, so each width is measured inside an iframe
# of exactly that width. The frame reports: w (iframe clientWidth), overflow
# (scrollWidth - clientWidth) and overlaps (value elements intersecting their row
# label's rendered text). The two control rows must read non-zero.
BASE="${1:?base URL of the served settings/ directory}"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
echo "harness_sha256=$(curl -s "${BASE}settings-change-marker.html" | shasum -a 256 | cut -c1-16)"
for q in "w=375&theme=light&control=overflow" "w=375&theme=light&control=overlap" \
         "w=375&theme=light" "w=375&theme=dark" "w=768&theme=light" "w=768&theme=dark" \
         "w=1440&theme=light&h=1300" "w=1440&theme=dark&h=1300"; do
  t=$("$CHROME" --headless=new --disable-gpu --window-size=1500,1400 --virtual-time-budget=3000 \
      --dump-dom "${BASE}settings-change-marker-frame.html?$q" 2>/dev/null | grep -oE '<title>[^<]*')
  echo "$q -> ${t#<title>}"
done
