#!/usr/bin/env bash
# Mutation proof for BRO-2131. A green suite proves the tests PASS; it does not
# prove any check can FAIL. Each mutation guts exactly one check and asserts the
# suite goes red. A mutation that SURVIVES means that check is unbound to its
# test — vacuous.
#
# Discipline enforced here (each learned from a prior arc that got it wrong):
#   * clean-tree assert BEFORE the first mutation — the revert baseline is
#     `git checkout -- <file>`, which destroys uncommitted work on line one
#   * exactly-one-anchor assert per mutation — a stale pattern no-ops silently
#     and reports a false SURVIVED
#   * bidirectional arms — an advisory check gets an arm proving it does NOT gate
#   * fsmonitor disabled — a dead daemon makes `git status` report a clean tree
#     while files are modified, voiding the guard above
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2

GATE="skills/tooling/skillify/scripts/skillify_check.py"
LINT="scripts/lint_skill_md.py"
GATE_TESTS="skills/tooling/skillify/tests/"
LINT_TESTS="tests/test_lint_skill_md.py"

if [ -n "$(git -c core.fsmonitor=false status --porcelain)" ]; then
  echo "ABORT: working tree is dirty. This script reverts to HEAD and would"
  echo "       destroy uncommitted work. Commit first."
  git -c core.fsmonitor=false status --porcelain
  exit 2
fi

# The baseline suite MUST be green before any mutation runs. Without this the
# whole report inverts: one pre-existing failure makes every mutation "KILLED"
# and the harness cheerfully prints "all mutations killed" while proving nothing.
for t in "$GATE_TESTS" "$LINT_TESTS"; do
  if ! python3 -m pytest "$t" -q >/dev/null 2>&1; then
    echo "ABORT: baseline suite is RED before mutating ($t)."
    echo "       Every mutation would report KILLED for the wrong reason."
    exit 2
  fi
done
echo "baseline: both suites green"

killed=0 survived=0

# mutate <file> <tests> <label> <find> <replace>
mutate() {
  local file="$1" tests="$2" label="$3" find="$4" repl="$5"
  local n
  n=$(python3 - "$file" "$find" <<'PY'
import sys
print(open(sys.argv[1], encoding="utf-8").read().count(sys.argv[2]))
PY
)
  if [ "$n" != "1" ]; then
    echo "  ✗ ANCHOR  $label — matched $n times, expected exactly 1 (stale pattern?)"
    survived=$((survived + 1))
    return
  fi
  python3 - "$file" "$find" "$repl" <<'PY'
import sys
p, find, repl = sys.argv[1], sys.argv[2], sys.argv[3]
t = open(p, encoding="utf-8").read()
open(p, "w", encoding="utf-8").write(t.replace(find, repl, 1))
PY
  if python3 -m pytest "$tests" -q >/dev/null 2>&1; then
    echo "  ✗ SURVIVED  $label — check is unbound to any test"
    survived=$((survived + 1))
  else
    echo "  ✓ KILLED    $label"
    killed=$((killed + 1))
  fi
  git checkout -- "$file"
}

echo "=== skillify_check.py — spec conformance (step 1) ==="
mutate "$GATE" "$GATE_TESTS" "description cap not enforced" \
  "if len(desc) > SPEC_MAX_DESCRIPTION:" "if False:"
mutate "$GATE" "$GATE_TESTS" "name length cap not enforced" \
  "if len(name) > SPEC_MAX_NAME:" "if False:"
mutate "$GATE" "$GATE_TESTS" "name charset not enforced" \
  "elif not SPEC_NAME_RE.match(name):" "elif False:"
mutate "$GATE" "$GATE_TESTS" "compatibility cap not enforced" \
  "if len(compat) > SPEC_MAX_COMPATIBILITY:" "if False:"
mutate "$GATE" "$GATE_TESTS" "silent-band wording dropped from message" \
  'if len(desc) <= OBSERVED_RENDER_CAP' 'if False'

echo "=== skillify_check.py — the latent_only hole (step 5) ==="
mutate "$GATE" "$GATE_TESTS" "purely-latent never requires a trigger eval" \
  "purely_latent = bool(latent_only) and not code" "purely_latent = False"
mutate "$GATE" "$GATE_TESTS" "evals forced required for EVERY skill (over-correction)" \
  "purely_latent = bool(latent_only) and not code" "purely_latent = True"

echo "=== skillify_check.py — advisory checks (1d / 1e / 1f) ==="
mutate "$GATE" "$GATE_TESTS" "when-clause always considered present" \
  "elif _WHEN_CLAUSE_RE.search(desc_text):" "elif True:"
mutate "$GATE" "$GATE_TESTS" "gotchas section always considered present" \
  "if _GOTCHA_SECTION_RE.search(body):" "if True:"
mutate "$GATE" "$GATE_TESTS" "body budget never warns" \
  "if body_lines > SPEC_RECOMMENDED_BODY_LINES:" "if False:"

echo "=== lint_skill_md.py — the four ratchet rules ==="
# Mutate the GATING BRANCH, not the message. Rewording the error still fails the
# test (which asserts on message content) and reports KILLED while new over-cap
# debt is in fact still rejected — a mutation that proves nothing.
mutate "$LINT" "$LINT_TESTS" "rule 1: new over-cap debt accepted" \
  "            if prior is None:" "            if False:"
mutate "$LINT" "$LINT_TESTS" "rule 2: growth beyond the frozen length accepted" \
  "elif dlen > prior:" "elif False:"
mutate "$LINT" "$LINT_TESTS" "rule 3: fixed-but-still-listed entry allowed to rot" \
  "elif prior is not None:" "elif False:"
mutate "$LINT" "$LINT_TESTS" "rule 4: stale grandfather entry accepted" \
  "for stale in sorted(set(grandfathered) - seen):" "for stale in sorted(set()):"
mutate "$LINT" "$LINT_TESTS" "vendored .venv skills linted after all" \
  'if "extensions" in parts or VENDORED.intersection(parts):' "if False:"
mutate "$LINT" "$LINT_TESTS" "name-vs-parent-dir rule dropped" \
  "elif name != md.parent.name:" "elif False:"

echo "=== P20 round 1 fixes (CodeRabbit) ==="
mutate "$LINT" "$LINT_TESTS" "name regex diverges from skillify_check (no leading digit)" \
  'NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")' \
  'NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")'
mutate "$LINT" "$LINT_TESTS" "delimiters matched as substrings again" \
  'close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)' \
  'close = next((i for i in range(1, len(lines)) if lines[i].startswith("---")), None)'
mutate "$LINT" "$LINT_TESTS" "opening delimiter accepts a prefix again" \
  'if not lines or lines[0].strip() != "---":' \
  'if not lines or not lines[0].startswith("---"):'
mutate "$LINT" "$LINT_TESTS" "empty compatibility accepted" \
  'elif not compat.strip():' 'elif False:'
mutate "$LINT" "$LINT_TESTS" "seen recorded after description validation (double-report)" \
  "        seen.add(key)
        fm, err = _parse(md)" \
  "        fm, err = _parse(md)"
mutate "$GATE" "$GATE_TESTS" "gate accepts a truncating body delimiter again" \
  'r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)"' 'r"^---\n(.*?)\n---"'
mutate "$GATE" "$GATE_TESTS" "gate accepts empty compatibility" \
  'if not compat.strip():' 'if False:'

echo "=== P20 round 1 blockers (Codex Strata A) ==="
mutate "$LINT" "$LINT_TESTS" "BLOCKER: ratchet baseline no longer immutable (new entries allowed)" \
  "        if key not in base:" "        if False:"
mutate "$LINT" "$LINT_TESTS" "BLOCKER: frozen lengths allowed to rise" \
  "        elif length > base[key]:" "        elif False:"
mutate "$GATE" "$GATE_TESTS" "BLOCKER: trigger key presence counts as an assertion again" \
  "    return len(_trigger_polarities(node)) >= 2" "    return _trigger_polarities(node) is not None"
mutate "$GATE" "$GATE_TESTS" "BLOCKER: single polarity accepted (positive-only suite)" \
  "    return len(_trigger_polarities(node)) >= 2" "    return len(_trigger_polarities(node)) >= 1"
mutate "$GATE" "$GATE_TESTS" "BLOCKER: latent_only adjudicated on scripts/ only again" \
  "    purely_latent = bool(latent_only) and not any_code" \
  "    purely_latent = bool(latent_only) and not code"
mutate "$GATE" "$GATE_TESTS" "BLOCKER: latent_only contradiction ignores nested code" \
  "    if latent_only and any_code:" "    if latent_only and code:"
mutate "$GATE" "$GATE_TESTS" "BLOCKER: non-string frontmatter fields laundered again" \
  "        if field in data and not isinstance(data[field], str):" \
  "        if False:"
mutate "$GATE" "$GATE_TESTS" "over-correction guard: key-groups-prompts schema rejected" \
  "                elif isinstance(v, (list, str)) and len(v) > 0:" "                elif False:"
mutate "$GATE" "$GATE_TESTS" "MINOR: when-clause counts negations" \
  "    desc_affirmative = _WHEN_NEGATION_RE.sub(\" \", desc_text)" \
  "    desc_affirmative = desc_text"
mutate "$GATE" "$GATE_TESTS" "MINOR: gotchas heading inside a fence counts" \
  "    body_prose = _strip_fences(body)" "    body_prose = body"

echo
echo "killed=$killed survived=$survived"
if [ -n "$(git -c core.fsmonitor=false status --porcelain)" ]; then
  echo "ERROR: tree left dirty — a revert failed"
  exit 2
fi
[ "$survived" -eq 0 ] || exit 1
echo "all mutations killed — every check is bound to a test"
