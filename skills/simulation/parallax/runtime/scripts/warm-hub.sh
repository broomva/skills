#!/usr/bin/env bash
# Wake the Render hub and report what is actually running on it.
#
# The free tier spins down after 15 minutes idle. Measured: 12.4s cold, 0.22s
# warm. Run it a few minutes before anything needs the hub to answer quickly.
#
# It reports the DEPLOYED COMMIT, not the version: `version` is a source
# constant and the deploy API reports intent. The commit is the only field that
# a stale image cannot fake.
#
# Usage:  scripts/warm-hub.sh [--watch]
set -uo pipefail

HUB="${PARALLAX_HUB:-https://parallax-hub.onrender.com}"
HUB="${HUB%/}"

probe() {
  local body http time
  body=$(curl -s -m 120 -w '\n%{http_code} %{time_total}' "$HUB/health" 2>/dev/null) || {
    printf 'unreachable  %s\n' "$HUB"; return 1; }
  http=$(printf '%s' "$body" | tail -1 | cut -d' ' -f1)
  time=$(printf '%s' "$body" | tail -1 | cut -d' ' -f2)
  body=$(printf '%s' "$body" | sed '$d')

  if [ "$http" != "200" ]; then
    printf 'HTTP %s in %ss  %s\n' "$http" "$time" "$HUB"; return 1
  fi

  local commit state
  commit=$(printf '%s' "$body" | sed -n 's/.*"commit":"\([^"]*\)".*/\1/p')
  # Under ~2s it was already awake; above that we just paid the cold start.
  state=$(awk -v t="$time" 'BEGIN{print (t+0 < 2.0) ? "warm" : "COLD (now warm)"}')
  printf 'ok  %-16s %ss  commit %s\n' "$state" "$time" "${commit:0:12}"

  if [ -n "$commit" ] && git rev-parse --git-dir >/dev/null 2>&1; then
    if ! git cat-file -e "$commit^{commit}" 2>/dev/null; then
      printf '    note: that commit is not in this checkout -- fetch, or the hub is ahead\n'
    else
      local behind
      behind=$(git rev-list --count "$commit..HEAD" 2>/dev/null || echo '?')
      [ "$behind" != "0" ] && printf '    note: local HEAD is %s commit(s) ahead of what is deployed\n' "$behind"
    fi
  fi
  return 0
}

if [ "${1:-}" = "--watch" ]; then
  # Keep it awake. 240s polling is well inside the 15-minute idle window.
  while true; do printf '%s  ' "$(date '+%H:%M:%S')"; probe; sleep 240; done
else
  probe
fi
