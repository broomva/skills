#!/usr/bin/env bash
# check.sh — model-check p9's P20 verdict gate (P9Lifecycle.tla) under every variant.
#
# Each configuration states the outcome it must produce. A safe variant must
# finish with no error; a broken variant MUST produce a counterexample, so a
# model that has stopped being able to fail is caught as a failure too.
#
#   p9.cfg                 the rule as implemented        SafeMerge holds; no merge after a base update
#   exempt.cfg             + derived exemption, CI check   SafeMerge holds
#   exempt_probe.cfg       + derived exemption, CI check   a merge after a base update IS reachable
#   exempt_unchecked.cfg   + derived exemption, no CI      SafeMerge violated (hand-edited generated file)
#   anypass.cfg            any PASS clears the PR          SafeMerge violated
#   reviewedonly.cfg       only reviewed files void it     SafeMerge violated (file added after review)
#
# TLA+ tools are pinned (version and sha256) and cached outside the repo.
# Usage: bash check.sh            exit 0 iff every configuration produced its expected outcome
set -euo pipefail

TLA_VERSION=v1.7.4
TLA_SHA256=936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88
JAR="${TLA2TOOLS_JAR:-${XDG_CACHE_HOME:-$HOME/.cache}/tlaplus/$TLA_VERSION/tla2tools.jar}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v java >/dev/null || { echo "check.sh: java not found (needs a JRE 11+)" >&2; exit 2; }
if [ ! -f "$JAR" ]; then
  mkdir -p "$(dirname "$JAR")"
  curl -sSL --max-time 120 -o "$JAR.part" \
    "https://github.com/tlaplus/tlaplus/releases/download/$TLA_VERSION/tla2tools.jar"
  mv "$JAR.part" "$JAR"
fi
actual=$(shasum -a 256 "$JAR" 2>/dev/null | cut -d' ' -f1 || sha256sum "$JAR" | cut -d' ' -f1)
[ "$actual" = "$TLA_SHA256" ] || { echo "check.sh: $JAR sha256 $actual != pinned $TLA_SHA256" >&2; exit 2; }

fail=0

# Kept in step with the code: the model describes _p20_verdict as of confirmed_at.
# If that function's source changed since, the model may describe a rule p9 no
# longer has, so a stale model fails here instead of passing quietly.
if ! python3 - "$HERE" <<'PY'
import ast, hashlib, json, sys
from pathlib import Path
here = Path(sys.argv[1]); sync = json.loads((here / "sync.json").read_text())
for c in sync["covers"]:
    src = (here.parent / c["file"]).read_text()
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == c["function"])
    digest = hashlib.sha256(ast.get_source_segment(src, fn).encode()).hexdigest()
    if digest != sync["sha256"]:
        print(f"  FAIL  {c['file']}::{c['function']} changed since the model was confirmed at "
              f"{sync['confirmed_at'][:12]}. Re-read it against P9Lifecycle.tla, update the model if the "
              f"rule changed, then set sha256={digest} and confirmed_at in formal/sync.json.")
        sys.exit(1)
print(f"  ok    model in step with {', '.join(c['function'] for c in sync['covers'])} "
      f"(confirmed at {sync['confirmed_at'][:12]})")
PY
then fail=1; fi

run() {  # run <cfg> <expect: pass|violates:<Invariant>>
  local cfg=$1 expect=$2 meta out
  meta=$(mktemp -d)
  # -deadlock: a bounded model has terminal states by design (no commits left, merged or blocked).
  out=$(cd "$HERE" && java -XX:+UseParallelGC -cp "$JAR" tlc2.TLC -deadlock -workers auto -metadir "$meta" \
          -config "$cfg" P9Lifecycle.tla 2>&1) || true
  rm -rf "$meta"
  local states
  states=$(printf '%s\n' "$out" | grep -Eo '[0-9,]+ distinct states found' | tail -1 || true)
  case "$expect" in
    pass)
      if printf '%s\n' "$out" | grep -q "Model checking completed. No error has been found."; then
        echo "  ok    $cfg: no error ($states)"
      else
        echo "  FAIL  $cfg: expected no error"; printf '%s\n' "$out" | grep -E "Error|violated|is violated" | head -5; fail=1
      fi ;;
    violates:*)
      local inv=${expect#violates:}
      if printf '%s\n' "$out" | grep -q "Invariant $inv is violated"; then
        echo "  ok    $cfg: $inv violated, as it must be (counterexample found)"
      else
        echo "  FAIL  $cfg: expected a counterexample to $inv, found none"; fail=1
      fi ;;
  esac
}

echo "p9 P20 verdict gate — TLC $TLA_VERSION"
run p9.cfg                pass
run exempt.cfg            pass
run exempt_probe.cfg      violates:NoMergeAfterBaseUpdate
run exempt_unchecked.cfg  violates:SafeMerge
run anypass.cfg           violates:SafeMerge
run reviewedonly.cfg      violates:SafeMerge
exit $fail
