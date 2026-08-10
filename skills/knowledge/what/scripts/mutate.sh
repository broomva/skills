#!/usr/bin/env bash
# Mutation proof for skills/knowledge/what/scripts/what_concepts.py.
# Each mutation must be KILLED (suite fails). A SURVIVED mutation means the
# corresponding test cannot fail and is decoration.
set -uo pipefail

SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$SKILL/scripts/what_concepts.py"
cd "$SKILL" || exit 1

# The baseline revert runs before the first mutation, so uncommitted work in the
# target would be destroyed on line one. Assert a clean tree instead.
if [ -n "$(git status --porcelain -- scripts/ SKILL.md)" ]; then
  echo "ABORT: tree is dirty under $SKILL — commit first (revert-to-HEAD would destroy it)"
  exit 1
fi

killed=0; survived=0
declare -a SURVIVORS=()

mutate() {
  local name="$1" anchor="$2" replacement="$3"
  git checkout -q -- scripts/what_concepts.py

  # A stale anchor no-ops silently and reports a false SURVIVED. Assert exactly one.
  local n
  n=$(python3 - "$SRC" "$anchor" <<'PY'
import sys
src, anchor = sys.argv[1], sys.argv[2]
print(open(src, encoding="utf-8").read().count(anchor))
PY
)
  if [ "$n" != "1" ]; then
    echo "  ANCHOR-ERROR [$name]: anchor matched $n times (expected exactly 1)"
    SURVIVORS+=("ANCHOR-ERROR: $name")
    survived=$((survived+1))
    return
  fi

  python3 - "$SRC" "$anchor" "$replacement" <<'PY'
import sys
src, anchor, repl = sys.argv[1], sys.argv[2], sys.argv[3]
t = open(src, encoding="utf-8").read()
open(src, "w", encoding="utf-8").write(t.replace(anchor, repl, 1))
PY

  if PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest scripts/test_what_concepts.py -q -p no:cacheprovider >/dev/null 2>&1; then
    echo "  SURVIVED [$name]  <-- no test catches this"
    SURVIVORS+=("$name")
    survived=$((survived+1))
  else
    echo "  killed   [$name]"
    killed=$((killed+1))
  fi
}

# Two-anchor variant: some properties are defended by two independent mechanisms,
# so no single-point mutation can kill them. Removing one arm at a time then
# reports a false SURVIVED. Both arms must go at once.
mutate2() {
  local name="$1" a1="$2" r1="$3" a2="$4" r2="$5"
  git checkout -q -- scripts/what_concepts.py
  local ok
  ok=$(python3 - "$SRC" "$a1" "$a2" <<'PY'
import sys
src, a1, a2 = sys.argv[1], sys.argv[2], sys.argv[3]
t = open(src, encoding="utf-8").read()
print("yes" if t.count(a1) == 1 and t.count(a2) == 1 else "no")
PY
)
  if [ "$ok" != "yes" ]; then
    echo "  ANCHOR-ERROR [$name]: one of the two anchors did not match exactly once"
    SURVIVORS+=("ANCHOR-ERROR: $name"); survived=$((survived+1)); return
  fi
  python3 - "$SRC" "$a1" "$r1" "$a2" "$r2" <<'PY'
import sys
src, a1, r1, a2, r2 = sys.argv[1:6]
t = open(src, encoding="utf-8").read().replace(a1, r1, 1).replace(a2, r2, 1)
open(src, "w", encoding="utf-8").write(t)
PY
  if PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest scripts/test_what_concepts.py -q -p no:cacheprovider >/dev/null 2>&1; then
    echo "  SURVIVED [$name]  <-- no test catches this"
    SURVIVORS+=("$name"); survived=$((survived+1))
  else
    echo "  killed   [$name]"; killed=$((killed+1))
  fi
}

# Bytecode isolation: a length-preserving mutation written inside the same
# wall-clock second reuses stale .pyc and never executes, reporting a false
# SURVIVED (measured 2/10 before -B + no:cacheprovider).
rm -rf scripts/__pycache__ .pytest_cache
echo "== baseline =="
git checkout -q -- scripts/what_concepts.py
PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest scripts/test_what_concepts.py -q -p no:cacheprovider 2>&1 | tail -1

echo "== mutations =="

# 1. tool_result plumbing leaks in as a human turn
mutate "tool_results-become-human-turns" \
  'if isinstance(content, str) and content.strip():' \
  'if content:'

# 2. thinking blocks get mined
mutate "thinking-blocks-mined" \
  'if btype == "text" and isinstance(block.get("text"), str):' \
  'if btype in ("text", "thinking") and isinstance(block.get("text", block.get("thinking")), str):'

# 3. sidechain exclusion inverted
mutate "sidechains-always-included" \
  'if row.get("isSidechain") and not include_sidechains:' \
  'if row.get("isSidechain") and False:'

# 4. scope cuts at the FIRST /what instead of the last
mutate "scope-cuts-at-first-what" \
  'return turns[markers[-1] + 1:end], "since-last-what"' \
  'return turns[markers[0] + 1:end], "since-last-what"'

# 5. /what matched anywhere in the turn, not just at the start.
#    "start of turn" is defended TWICE: the `^` in the pattern and .match()'s own
#    anchoring. Removing either alone is inert and reports a false SURVIVED, so
#    both arms go together.
mutate2 "what-marker-matches-midsentence" \
  'WHAT_INVOCATION = re.compile(r"^\s*/what\b", re.IGNORECASE)' \
  'WHAT_INVOCATION = re.compile(r"\s*/what\b", re.IGNORECASE)' \
  '    return bool(WHAT_INVOCATION.match(text))' \
  '    return bool(WHAT_INVOCATION.search(text))'

# 6. frequency cap removed -> loud terms dominate the ranking again
mutate "frequency-cap-removed" \
  'min(FREQ_WEIGHT * math.log1p(uses), FREQ_CAP)' \
  '(FREQ_WEIGHT * math.log1p(uses))'

# 7. agent-introduced signal always true
mutate "agent-introduced-always-true" \
  'agent_introduced = normalize(term) not in human_norm' \
  'agent_introduced = True'

# 8. inline-gloss detection disabled -> everything looks unexplained
mutate "definitional-always-false" \
  'return any(re.search(p, text, re.IGNORECASE) for p in patterns)' \
  'return False'

# 9. grounding no longer rescues a term from the shape heuristics
mutate "grounding-does-not-rescue" \
  '    if grounded:
        return False' \
  '    if grounded and False:
        return False'

# 10. prefix-compound filter removed
mutate "prefix-filter-removed" \
  'if len(segs) == 2 and segs[0] in PREFIX_SEGMENTS:' \
  'if len(segs) == 2 and segs[0] in set():'

# 11. identifier-tail filter removed
mutate "ident-tail-filter-removed" \
  'if IDENT_TAIL.fullmatch(segs[-1]):' \
  'if False:'

# 12. named primitive no longer suppresses its bare NAME (live for CamelCase names)
mutate "primitive-name-suppression-removed" \
  '        suppress.add(m.group(1))' \
  '        pass'

# 12b. named primitive no longer suppresses its bare Pn form
mutate "primitive-number-suppression-removed" \
  '        suppress.add(f"P{int(m.group(2))}")' \
  '        pass'

# 13. bare-primitive range widened past P20
mutate "primitive-range-widened" \
  'PRIMITIVE_BARE = re.compile(r"\bP([1-9]|1[0-9]|20)\b")' \
  'PRIMITIVE_BARE = re.compile(r"\bP(\d{1,2})\b")'

# 14. alias never shadowed by a real slug
mutate "alias-shadows-real-slug" \
  '    for shadowed in set(aliases) & set(entities):
        del aliases[shadowed]' \
  '    pass'

# 15. dedupe merges everything that shares a path, including distinct primitives
mutate "dedupe-merges-distinct-primitives" \
  'f"g::{c.entity_path}::{c.claim}"' \
  'f"g::{c.entity_path}"'

# 16. min_freq threshold ignored
mutate "min-freq-ignored" \
  '        if uses < min_freq:
            continue' \
  '        pass'

# 17. --top truncation removed
mutate "top-truncation-removed" \
  ')[: args.top]' \
  ')[:]'

# 18. bad thresholds no longer rejected
mutate "usage-validation-removed" \
  'if args.top < 1 or args.min_freq < 1:' \
  'if False:'

# 19. missing source returns OK instead of exit 1
mutate "missing-source-exits-ok" \
  '        return EXIT_NO_SOURCE
    turns, source = loaded' \
  '        return EXIT_OK
    turns, source = loaded'

# 20. transcript resolution stops walking up parent dirs
mutate "transcript-no-parent-walk" \
  'for cand_dir in [cwd.resolve(), *cwd.resolve().parents]:' \
  'for cand_dir in [cwd.resolve()]:'

# 21. fenced code no longer stripped
mutate "fences-not-stripped" \
  '    if not keep_code:
        text = FENCE.sub(" ", text)' \
  '    pass'

# 22. re-pitch guidance dropped from empty render
mutate "repitch-message-dropped" \
  '        lines.append(REPITCH)' \
  '        lines.append("nothing found")'

# 23. undefined terms no longer flagged loudly in the table
mutate "undefined-flag-softened" \
  "| {'yes' if c.defined_inline else 'NO'} |" \
  "| {'yes' if c.defined_inline else 'no'} |"

# 24. P6 candidate section removed from the report
mutate "p6-scoring-gate-dropped-from-report" \
  'through the P6 gate (>= 5/9) and file only what clears it.' \
  'and file them.'

# 25. ranking tie-break made nondeterministic in shape (drops term ordering)
mutate "ranking-loses-total-order" \
  'concepts.sort(key=lambda c: (-c.score, -c.uses, c.term))' \
  'concepts.sort(key=lambda c: -c.score)'

# --- round-2 mutations: behaviours the P20 review found unpinned ---

mutate "scope-ignores-xml-command-form" \
  'm = COMMAND_NAME.search(text)' \
  'm = None'

mutate "scope-accepts-any-slash-command-as-what" \
  'return m.group(1).lower() == "what"' \
  'return True'

mutate "scope-keeps-the-live-invocation-turn" \
  '        end = len(turns) - 1' \
  '        end = len(turns)'

mutate "undefined-bonus-restored-to-broken-value" \
  'UNDEFINED_BONUS = 5.0' \
  'UNDEFINED_BONUS = 2.4'

mutate "coverage-weight-flattened" \
  'COVERAGE_WEIGHT = {"grounded": 1.0, "partial": 1.25, "ungrounded": 1.5}' \
  'COVERAGE_WEIGHT = {"grounded": 1.0, "partial": 1.0, "ungrounded": 1.0}'

mutate "kind-weight-flattened" \
  'KIND_WEIGHT = {"primitive": 2.0, "kebab": 1.5, "camel": 1.0, "acronym": 1.0, "snake": 0.5}' \
  'KIND_WEIGHT = {"primitive": 1.0, "kebab": 1.0, "camel": 1.0, "acronym": 1.0, "snake": 1.0}'

mutate "acronym-recount-uses-strict-boundary" \
  'pattern = rf"\b{re.escape(term)}\b"' \
  'pattern = rf"(?<![\w-]){re.escape(term)}(?![\w-])"'

mutate "definitional-treats-a-bare-hyphen-as-a-gloss" \
  'rf"{t}{end}\s*[—–]\s*\w",          # em/en dash gloss (never a plain hyphen)' \
  'rf"{t}\s*[—–:=-]\s*\w",'

mutate "dedupe-does-not-recompute-score" \
  '            "score": score_concept(uses, c.agent_introduced, c.defined_inline, c.kind, c.coverage),' \
  '            "score": c.score,'

mutate "dedupe-keeps-first-not-best" \
  'if prev is None or (c.score, c.term) > (prev.score, prev.term):' \
  'if prev is None:'

mutate "dedupe-final-sort-drops-tiebreak" \
  'out.sort(key=lambda c: (-c.score, -c.uses, c.term))' \
  'out.sort(key=lambda c: -c.score)'

mutate "partial-tier-accepts-short-generic-segments" \
  'PARTIAL_SEGMENT_MIN = 6' \
  'PARTIAL_SEGMENT_MIN = 1'

mutate "path-token-filter-removed" \
  'if "/" not in tok and not PATH_EXT.search(tok.rstrip(".,;:)]}"))' \
  'if True'

git checkout -q -- scripts/what_concepts.py
echo
echo "== result: killed=$killed survived=$survived =="
if [ ${#SURVIVORS[@]} -gt 0 ]; then
  printf '  survivor: %s\n' "${SURVIVORS[@]}"
  exit 1
fi
