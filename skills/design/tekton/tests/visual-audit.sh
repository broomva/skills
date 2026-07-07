#!/usr/bin/env bash
# Tekton visual/geometry audit — headless-Chrome layout QA for a rendered viewer.
# Usage: bash tests/visual-audit.sh <model.arch.yaml> [outdir]
# For each view: screenshot + DOM dump, then a geometry parse reporting
# node overlaps, label-on-node hits, and label-label collisions.
# Requires Google Chrome. Exit 1 if any view has node overlaps.
set -u
MODEL="${1:?usage: visual-audit.sh <model.arch.yaml> [outdir]}"
OUT="${2:-$(mktemp -d)}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHROME=""
for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
         "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
         "$(command -v google-chrome || true)" \
         "$(command -v chromium-browser || true)" \
         "$(command -v chromium || true)"; do
  [ -n "$c" ] && [ -x "$c" ] && CHROME="$c" && break
done
[ -n "$CHROME" ] || { echo "skip: no Chrome/Chromium found"; exit 0; }

python3 "$HERE/../scripts/tekton.py" render "$MODEL" >/dev/null || exit 1
HTML="${MODEL%.yaml}.view.html"
HTML="$(cd "$(dirname "$HTML")" && pwd)/$(basename "$HTML")"   # file:// needs absolute
mkdir -p "$OUT"
VIEWS=$(python3 "$HERE/../scripts/tekton.py" views | awk '{print $1}')
for V in $VIEWS; do
  "$CHROME" --headless=new --disable-gpu --window-size=1720,1080 --hide-scrollbars \
    --virtual-time-budget=9000 --screenshot="$OUT/$V.png" "file://$HTML#$V" >/dev/null 2>&1
  "$CHROME" --headless=new --disable-gpu --window-size=1720,1080 \
    --virtual-time-budget=9000 --dump-dom "file://$HTML#$V" 2>/dev/null > "$OUT/$V.html"
done

python3 - "$OUT" $VIEWS <<'PY'
import re, sys, os
out, views = sys.argv[1], sys.argv[2:]
fail = False
for v in views:
    p = os.path.join(out, f"{v}.html")
    if not os.path.exists(p): continue
    d = open(p).read()
    nodes=[]
    for m in re.finditer(r'class="node[^"]*" data-id="([^"]+)"[^>]*style="([^"]*)"', d):
        s=m.group(2)
        x=re.search(r'left:\s*([\d.]+)px',s); y=re.search(r'top:\s*([\d.]+)px',s); w=re.search(r'width:\s*([\d.]+)px',s)
        if x and y: nodes.append((m.group(1),float(x.group(1)),float(y.group(1)),float(w.group(1)) if w else 150,54))
    ov=[f"{a[0]}x{b[0]}" for i,a in enumerate(nodes) for b in nodes[i+1:]
        if a[1]<b[1]+b[3] and b[1]<a[1]+a[3] and a[2]<b[2]+b[4] and b[2]<a[2]+a[4]]
    labs=[(float(a),float(b)) for a,b in re.findall(r'class="elabel"[^>]*style="left:\s*([\d.]+)px;\s*top:\s*([\d.]+)px', d)]
    lon=sum(1 for lx,ly in labs for n in nodes if n[1]<lx<n[1]+n[3] and n[2]<ly<n[2]+n[4])
    ll=sum(1 for i in range(len(labs)) for j in range(i+1,len(labs)) if abs(labs[i][0]-labs[j][0])<50 and abs(labs[i][1]-labs[j][1])<12)
    # nodes=0 means the page never laid out (CDN race / load failure) — that is
    # a FAILED capture, not a passing view. A 100%-pass audit that can pass on
    # an empty page is insensitive.
    flag = "FAIL" if (ov or not nodes) else "ok"
    if ov or not nodes: fail = True
    note = " EMPTY-CAPTURE" if not nodes else ""
    print(f"  {flag}: {v:10} nodes={len(nodes):2} overlaps={len(ov)} {ov[:3]} labels-on-nodes={lon} label-collisions={ll}{note}")
print(f"\nshots + dumps in: {out}")
sys.exit(1 if fail else 0)
PY
