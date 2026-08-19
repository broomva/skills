#!/usr/bin/env bash
# Mutation proof for attempt-audit's own test suite.
#
# A suite that always passes is a vacuous pass -- the defect this tool detects.
# Each arm removes one behaviour and names the test that MUST go red.
#
# RED HAS TWO CAUSES: the behaviour changed, or the mutant is simply broken. An
# earlier version ran ONE global control before any mutation and called that
# "pairing"; replacing the whole script with `sys.exit(3)` then scored 5/5
# KILLED. So every arm now runs a per-arm SANITY probe -- the mutated script
# must still execute correctly on a file with no findings -- and arm 0 is a
# deliberately-broken sentinel that MUST be rejected as invalid, not counted as
# a kill.
#
# Mutants run against a full COPY of the skill dir under $TMP; the tracked
# source is never edited.
set -uo pipefail

SKILL="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fail=0

stage() { rm -rf "$TMP/s"; cp -R "$SKILL" "$TMP/s"; }
src()   { echo "$TMP/s/scripts/attempt_audit.py"; }
runtest() { python3 -m pytest "$TMP/s/tests/test_attempt_audit.py::$1" -q 2>&1 | tail -1; }

# --- control -----------------------------------------------------------------
stage
if python3 -m pytest "$TMP/s/tests/test_attempt_audit.py" -q >"$TMP/out" 2>&1; then
  echo "PASS  control: unmutated suite is green"
else
  echo "FAIL  control: unmutated suite is RED -- every arm below is meaningless"; tail -5 "$TMP/out"; fail=1
fi

# A mutant must still RUN. If it cannot audit a trivial clean file, any red it
# produces is breakage, not evidence.
# The mutant must still run and still emit parseable JSON on a probe. This
# rejects the crudest false KILLED (a mutant that is simply broken), and NOT all
# of them: review found a three-line insert that removes no detection logic yet
# passes both probes and still turns three arms red, because the probes and the
# tests use different argument combinations. Chasing that with a third probe
# would be hardening the measurement apparatus instead of the product, so the
# claim is narrowed rather than the harness extended.
sane() {
  local probe="$TMP/probe.py"; printf 'def f(x):\n    return x + 1\n' > "$probe"
  python3 "$1" "$probe" >/dev/null 2>&1
  local rc=$?
  # 0 (clean) and 1 (findings) are both healthy; >=2 is a broken or blind mutant.
  [ "$rc" -le 1 ] || return 1
  # No pipeline here: `set -o pipefail` would surface the auditor's exit 1
  # ("findings found", perfectly healthy) as a probe failure. Capture, then parse.
  python3 "$1" "$TMP/s/tests/fixtures" --json >"$TMP/sane.json" 2>/dev/null
  python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$TMP/sane.json" 2>/dev/null
}

arm() { # name, test, python-mutation-expression
  local name="$1" test="$2" mut="$3"
  stage
  python3 - "$(src)" <<PY
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
$mut
assert s != orig, "MUTATION DID NOT APPLY"
p.write_text(s)
PY
  if [ $? -ne 0 ]; then
    echo "FAIL  $name: mutation did not apply -- stale anchor, result meaningless"; fail=1; return
  fi
  if ! sane "$(src)"; then
    echo "FAIL  $name: mutant does not run at all -- any red is breakage, not evidence"; fail=1; return
  fi
  out=$(runtest "$test")
  if echo "$out" | grep -q "1 failed"; then
    echo "PASS  $name: removing it turns $test RED (mutant still runs)"
  else
    echo "FAIL  $name: $test stayed green -- it does not test this ($out)"; fail=1
  fi
}

# --- arm 0: the sentinel. A totally broken script must be REJECTED, not killed.
stage
printf 'import sys\nsys.exit(3)\n' > "$(src)"
if sane "$(src)"; then
  echo "FAIL  mutant0 sentinel: a broken script passed the sanity probe"; fail=1
else
  echo "PASS  mutant0 sentinel: total breakage is rejected as invalid, not scored KILLED"
fi

arm "mutant1 does_work filter" test_ignores_a_validation_chain \
  'orig = s
s = s.replace("            if not does_work:\n                continue\n", "")'

arm "mutant2 adjacency rule" test_ignores_a_guard_followed_by_an_alternative_path \
  'orig = s
s = s.replace("            if body.index(stmt) != body.index(fallthrough) - 1:\n                continue\n", "")'

arm "mutant3 recorded-skip check" test_ignores_a_recorded_skip \
  'orig = s
s = s.replace("            if _records_a_skip(list(stmt.orelse) + after):\n                continue\n", "")'

arm "mutant4 scanned-nothing exit" test_scanning_nothing_is_not_a_clean_result \
  'orig = s
s = s.replace("    if scanned == 0 or walk_errors or unreadable:\n        return 2\n", "")'

arm "mutant5 unreadable reporting" test_unreadable_files_are_reported_not_silently_skipped \
  'orig = s
s = s.replace("            unreadable.append({\"file\": str(p), \"reason\": f\"{type(exc).__name__}: {exc}\"})", "            pass")'

echo
# Deliberately not "every behaviour is covered": these arms show that each named
# behaviour has a test which goes red when that behaviour is removed. A mutant
# built to defeat the probes can still score PASS.
[ "$fail" -eq 0 ] && echo "ALL ARMS PASS: each named behaviour has a test that fails without it" \
                  || echo "SUITE FAILED"
exit "$fail"
