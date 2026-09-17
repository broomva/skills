#!/usr/bin/env bash
# Mutation proof for spec_check.
#
# Each mutant is a semantic WEAKENING of exactly one check. A mutant that
# survives means the suite passes with that check disabled — the check is
# decorative and the tests that "cover" it prove nothing.
#
# The whole skill directory is copied to a scratch dir and mutated THERE. The
# working tree is never written to, so an interrupted run cannot destroy
# uncommitted work and there is no revert step that could restore a stale mtime.
#
# Usage:  tests/mutation.sh [python]
set -uo pipefail

PY="${1:-/usr/bin/python3}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1   # a same-length mutant is otherwise masked by a stale .pyc

if ! "$PY" -c 'import pytest' 2>/dev/null; then
  echo "mutation.sh: $PY has no pytest" >&2; exit 2
fi

# name<TAB>from<TAB>to  — `from` must appear EXACTLY once in the source, which is
# asserted per mutant; a substitution that silently matches zero or many places
# would report a fake survivor.
read -r -d '' MUTANTS <<'EOF' || true
C1-required-empty	    return PROFILES[profile]["required"]	    return ()
C2-status-never-missing	    if not m:	    if False:
C3-reversal-never-missing	    if not rm:	    if False:
C4-negation-never-matches	            if NEGATION_HEAD.match(head):	            if False:
C5-one-alternative-is-enough	        if len(distinct) < 2:	        if len(distinct) < 1:
C5-rejection-never-required	        if not REJECTION_MARKERS.search(body):	        if False:
C6-cost-always-found	        if dsec and not COST_LANGUAGE.search(" ".join(s.subtree for s in dsec)):	        if False:
C7-next-step-always-found	        if not NEXT_STEP.search(body):	        if False:
C8-acceptance-always-measurable	        if asec and not MEASURABLE.search(" ".join(s.subtree for s in asec)):	        if False:
C9-manual-never-detected	    if hits == 0 and words > MIN_WORDS:	    if False:
C10-size-never-warns	    if pages > MAX_PAGES:	    if False:
C1-required-downgraded-to-warn	                "C1-missing-section", "fail",	                "C1-missing-section", "warn",
subtree-is-a-noop	            parts.append(nxt.body)	            pass
profile-always-note	    if words is not None and words < 700:	    if True:
EOF

killed=0; survived=0; broken=0
printf '%-34s %s\n' "MUTANT" "VERDICT"
printf '%-34s %s\n' "----------------------------------" "-------"

while IFS=$'\t' read -r name from to; do
  [ -z "${name:-}" ] && continue
  scratch="$(mktemp -d)"
  cp -R "$HERE/scripts" "$HERE/tests" "$scratch/"
  src="$scratch/scripts/spec_check.py"

  # Refuse a substitution that is not unique: zero matches makes an inert mutant
  # that survives for the wrong reason, many matches changes more than one check.
  n=$("$PY" - "$src" "$from" <<'PY'
import sys
print(open(sys.argv[1], encoding="utf-8").read().count(sys.argv[2]))
PY
)
  if [ "$n" != "1" ]; then
    printf '%-34s BROKEN (anchor matched %s times)\n' "$name" "$n"
    broken=$((broken + 1)); rm -rf "$scratch"; continue
  fi

  "$PY" - "$src" "$from" "$to" <<'PY'
import sys
p, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(p, encoding="utf-8").read()
open(p, "w", encoding="utf-8").write(s.replace(a, b, 1))
PY

  if "$PY" -m pytest "$scratch/tests/test_spec_check.py" -q >"$scratch/out.txt" 2>&1; then
    printf '%-34s SURVIVED  <-- the suite does not test this\n' "$name"
    survived=$((survived + 1))
  else
    nfail=$(grep -cE '^FAILED|^ERROR' "$scratch/out.txt" || true)
    printf '%-34s killed (%s test(s))\n' "$name" "$nfail"
    killed=$((killed + 1))
  fi
  rm -rf "$scratch"
done <<< "$MUTANTS"

total=$((killed + survived))
echo
echo "killed $killed/$total   survived $survived   broken-anchor $broken"
[ "$broken" -gt 0 ] && { echo "FAIL: a mutant anchor did not match exactly once"; exit 1; }
[ "$survived" -gt 0 ] && { echo "FAIL: a check survived its own mutant"; exit 1; }
echo "OK: every check is killed by its own mutant"
