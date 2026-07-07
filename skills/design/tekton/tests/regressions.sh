#!/usr/bin/env bash
# Tekton regression suite — one test per P20 review finding (rounds 1 + 2).
# Run from anywhere: bash skills/tekton/tests/regressions.sh
# Exit 0 = all pass; exit 1 = failures (CI-gateable).
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEKTON="python3 $HERE/../scripts/tekton.py"
SELF="$HERE/../examples/tekton-self.arch.yaml"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
FAIL=0
ok(){ echo "  ok: $1"; }
bad(){ echo "  FAIL: $1"; FAIL=1; }
expect_rc(){ [ "$1" = "$2" ] && ok "$3" || bad "$3 (rc=$1 want $2)"; }
expect_grep(){ echo "$1" | grep -q "$2" && ok "$3" || bad "$3"; }
no_traceback(){ echo "$1" | grep -q "Traceback" && bad "$2 leaked a traceback" || ok "$2: no traceback"; }

# ── R1-F1: duplicate ids error (within and across blocks) ──────────────
printf 'name: t\nnodes:\n - {id: api, type: component, label: A}\n - {id: api, type: datastore, label: B}\n' > "$T/dup.yaml"
out=$($TEKTON validate "$T/dup.yaml" 2>&1); expect_rc $? 1 "R1-F1 dup id exits 1"
expect_grep "$out" "duplicate id 'api'" "R1-F1 dup message"
printf 'name: t\nnodes:\n - {id: x, type: component, label: A}\nqualities:\n - {id: x, label: Q}\n' > "$T/dupx.yaml"
out=$($TEKTON validate "$T/dupx.yaml" 2>&1); expect_rc $? 1 "R1-F1 cross-block dup exits 1"

# ── R1-F2: via as bare string still fires ───────────────────────────────
printf 'name: t\nnodes:\n - {id: v, type: component, label: V}\n - {id: s, type: datastore, label: S}\nedges:\n - {from: v, to: s, type: writes}\nrules:\n - {id: ro, rule: forbid-dep, from: {id: v}, to: {id: s}, via: writes}\n' > "$T/via.yaml"
out=$($TEKTON lint "$T/via.yaml" 2>&1); expect_rc $? 1 "R1-F2 string via fires"
expect_grep "$out" "forbidden dependency: v" "R1-F2 violation reported"

# ── R1-F3: typo'd rule key error; stale id warn ─────────────────────────
printf 'name: t\nnodes:\n - {id: a, type: component, label: A}\nrules:\n - {id: r1, rule: forbid-dep, frm: {id: a}, to: {id: a}}\n - {id: r2, rule: forbid-dep, from: {id: ghost}, to: {id: a}}\n' > "$T/sel.yaml"
out=$($TEKTON lint "$T/sel.yaml" 2>&1)
expect_grep "$out" "unknown key(s) \['frm'\]" "R1-F3a typo key caught"
expect_grep "$out" "matches no node" "R1-F3b stale id warned"

# ── R1-F4: </script> label cannot break DATA block ─────────────────────
printf 'name: t\nnodes:\n - {id: x, type: component, label: "</script><img src=x onerror=alert(1)>"}\n' > "$T/xss.yaml"
$TEKTON render "$T/xss.yaml" -o "$T/xss.html" >/dev/null 2>&1
if python3 - "$T/xss.html" <<'PY'
import sys
line = [l for l in open(sys.argv[1]) if l.startswith("const DATA")][0]
assert "</script>" not in line and "<\\/script>" in line
PY
then ok "R1-F4 </script> breakout neutralized"; else bad "R1-F4 breakout"; fi

# ── R1-F5: malformed inputs → clean errors ──────────────────────────────
printf 'name: t\nnodes:\n - {type: component, label: NoId}\nedges:\n - {from: a}\n' > "$T/mal.yaml"
out=$($TEKTON validate "$T/mal.yaml" 2>&1); expect_rc $? 1 "R1-F5 malformed exits 1"; no_traceback "$out" "R1-F5 malformed"
printf -- '- just\n- a list\n' > "$T/scalar.yaml"
out=$($TEKTON validate "$T/scalar.yaml" 2>&1); expect_grep "$out" "must be a YAML mapping" "R1-F5 non-mapping rejected"

# ── R1-F6: 1500-node chain, no RecursionError ───────────────────────────
python3 - > "$T/deep.yaml" <<'PY'
print("name: deep\nnodes:")
for i in range(1500): print(f" - {{id: n{i}, type: component, label: N{i}}}")
print("edges:")
for i in range(1499): print(f" - {{from: n{i}, to: n{i+1}, type: calls}}")
print("rules:\n - {id: ac, rule: no-cycle, via: [calls]}")
PY
out=$($TEKTON lint "$T/deep.yaml" 2>&1); expect_rc $? 0 "R1-F6 1500-deep lints (iterative DFS)"

# ── R1-F7: query truncation on a multi-path pair; no spurious flag ─────
out=$($TEKTON query "$SELF" s_model repo --limit 2 2>&1); expect_grep "$out" "TRUNCATED" "R1-F7 limit honored"
out=$($TEKTON query "$SELF" carlos repo 2>&1); echo "$out" | grep -q "TRUNCATED" && bad "R1-F7 spurious truncation" || ok "R1-F7 no spurious flag"

# ── R1-F8 + R2: sentinels in model text survive; __DATA__ in name doesn't leak JSON ──
printf 'name: "X __TITLE__ __DATA__ Y"\nnodes:\n - {id: a, type: component, label: "has __DESC__ inside"}\n' > "$T/ph.yaml"
$TEKTON render "$T/ph.yaml" -o "$T/ph.html" >/dev/null 2>&1
if python3 - "$T/ph.html" <<'PY'
import sys
d = open(sys.argv[1]).read()
line = [l for l in d.split("\n") if l.startswith("const DATA")][0]
assert "__DESC__" in line and "__TITLE__" in line          # model text intact
title = d.split("<title>")[1].split("</title>")[0]
assert "const" not in title and len(title) < 200            # no JSON leak into <title>
assert "__DATA__" in title                                  # sentinel preserved as text
PY
then ok "R1-F8/R2 sentinel handling (incl. __DATA__-in-name leak)"; else bad "R1-F8/R2 sentinels"; fi

# ── R1-F9: layer-order surfaces unlayered exemptions ────────────────────
printf 'name: t\nnodes:\n - {id: a, type: component, label: A, layer: interface}\n - {id: b, type: component, label: B}\nedges:\n - {from: a, to: b, type: calls}\nrules:\n - {id: lo, rule: layer-order, layers: [interface, data], via: [calls]}\n' > "$T/layer.yaml"
out=$($TEKTON lint "$T/layer.yaml" 2>&1); expect_grep "$out" "EXEMPT from layering: b" "R1-F9 unlayered warned"

# ── R1-F10: render refuses invalid model (parent cycle) ─────────────────
printf 'name: t\nnodes:\n - {id: a, type: component, label: A, parent: b}\n - {id: b, type: component, label: B, parent: a}\n' > "$T/pc.yaml"
$TEKTON render "$T/pc.yaml" -o "$T/pc.html" >/dev/null 2>&1; expect_rc $? 1 "R1-F10 render refuses parent cycle"

# ── R2-MF2: via with non-string non-list → clean ERROR, no crash ───────
printf 'name: t\nnodes:\n - {id: a, type: component, label: A}\nrules:\n - {id: r, rule: no-cycle, via: 7}\n' > "$T/via7.yaml"
out=$($TEKTON lint "$T/via7.yaml" 2>&1); expect_rc $? 1 "R2-MF2 via:7 exits 1"
no_traceback "$out" "R2-MF2 via:7"; expect_grep "$out" "'via' must be a string or list" "R2-MF2 message"

# ── R2 follow-ups: exotic-typed fields → clean errors ───────────────────
printf 'name: t\nnodes:\n - {id: a, type: component, label: A}\ndecisions:\n - {id: d1, label: D, status: accepted, supersedes: [x, y]}\n - {id: d2, label: D2, status: accepted, governs: a}\n' > "$T/refs.yaml"
out=$($TEKTON validate "$T/refs.yaml" 2>&1); no_traceback "$out" "R2 supersedes-list/governs-string"
echo "$out" | grep -q "missing node 'x'" && ok "R2 supersedes list accepted (refs still checked)" || bad "R2 supersedes list"
printf 'name: t\nnodes:\n - {id: a, type: component, label: A}\ndecisions:\n - {id: d3, label: D3, status: accepted, governs: {bad: map}}\n' > "$T/refs2.yaml"
out=$($TEKTON validate "$T/refs2.yaml" 2>&1); expect_rc $? 1 "R2 governs-mapping exits 1"; no_traceback "$out" "R2 governs-mapping"
printf 'name: 123\nnodes:\n - {id: a, type: component, label: A}\n' > "$T/intname.yaml"
out=$($TEKTON render "$T/intname.yaml" -o "$T/intname.html" 2>&1); expect_rc $? 0 "R2 numeric name renders"
printf 'name: [broken\n' > "$T/broken.yaml"
out=$($TEKTON validate "$T/broken.yaml" 2>&1); expect_rc $? 1 "R2 broken YAML exits 1"; no_traceback "$out" "R2 broken YAML"

# ── Positive suite: self-model stays green ──────────────────────────────
$TEKTON validate "$SELF" >/dev/null 2>&1; expect_rc $? 0 "self-model validates"
$TEKTON lint "$SELF" >/dev/null 2>&1; expect_rc $? 0 "self-model lints PASS"
$TEKTON render "$SELF" -o "$T/self.html" >/dev/null 2>&1; expect_rc $? 0 "self-model renders"
out=$($TEKTON query "$SELF" q_difffriendly repo 2>&1); expect_grep "$out" "constrains" "cross-tier query works"

echo
if [ $FAIL -eq 0 ]; then echo "ALL REGRESSION TESTS PASS"; exit 0
else echo "REGRESSION FAILURES PRESENT"; exit 1; fi
