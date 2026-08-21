#!/usr/bin/env bash
# tests/mutate-reviewer-guard.sh — per-rule mutation sweep for the BRO-2200
# reviewer guard. Regenerates the "6 killed / 0 survived" figure.
#
# Neuters ONE property at a time and requires a test to go red for each. This is
# finer-grained than mutation-proof.sh (which stubs the whole file): a suite can
# notice a stubbed file while testing none of the individual properties in it.
# Both survivors it found on first run were real — the diff half of the
# fingerprint and the -uall flag were each doing work no test exercised.
#
# Note the anchor counter uses python, not `grep -cF`: grep counts LINES and
# splits a multi-line pattern into an OR, so a multi-line anchor miscounts and
# the mutation silently SKIPs — a skipped mutation reads like a passed one.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 2
[ -n "$(git -c core.fsmonitor=false status --porcelain .)" ] && { echo "REFUSING: dirty"; exit 2; }
F=scripts/cross-review.sh; pass=0; surv=0
bash tests/cross-review.test.sh >/dev/null 2>&1 || { echo "baseline RED"; exit 2; }
echo "  baseline green"
mut(){ local n="$1" a="$2" r="$3"
  local c; c=$(python3 -c "import sys;print(open(sys.argv[1]).read().count(sys.argv[2]))" "$F" "$a")
  [ "$c" -ne 1 ] && { echo "  [SKIP] $n (anchor x$c)"; return; }
  python3 - "$F" "$a" "$r" <<'PY'
import sys,pathlib
p=pathlib.Path(sys.argv[1]);s=p.read_text();assert s.count(sys.argv[2])==1
p.write_text(s.replace(sys.argv[2],sys.argv[3]))
PY
  bash -n "$F" 2>/dev/null || { echo "  [SKIP] $n (mutant unparseable)"; git checkout -q -- "$F"; return; }
  if bash tests/cross-review.test.sh >/dev/null 2>&1; then
    echo "  [SURVIVED] $n  <-- untested"; surv=$((surv+1))
  else echo "  [KILLED ] $n"; pass=$((pass+1)); fi
  git checkout -q -- "$F"; }

mut "fingerprint ignores untracked files"  "        git -c core.fsmonitor=false status --porcelain=v1 -uall 2>/dev/null" "        git -c core.fsmonitor=false status --porcelain=v1 2>/dev/null"
mut "fingerprint ignores tracked edits"    "        git -c core.fsmonitor=false diff HEAD --no-ext-diff --no-textconv 2>/dev/null" "        true"
mut "missing baseline treated as pass"     'An unverifiable review is not a passed review." >&2
                exit 4' 'An unverifiable review is not a passed review." >&2
                exit 0'
# shellcheck disable=SC2016  # anchors are literal source text; expansion would
# rewrite the very string we are searching for, and the mutation would never match.
mut "verify always admissible"             '            if [ "$BEFORE" = "$AFTER" ]; then' '            if true; then'
mut "strata B back to general-purpose"     "subagent_type='Explore'" "subagent_type='general-purpose'"
mut "strata A sandbox removed"             "codex exec -m gpt-5.4 -c sandbox_mode=read-only" "codex exec -m gpt-5.4"
echo "=== $pass killed / $surv survived ==="
[ "$surv" -eq 0 ] || exit 1
