#!/usr/bin/env bash
# record_evidence.sh — regenerate evidence/ for the KG Claims mod from the synthetic fixtures.
#
# Runs the lab end to end against the real Obsidian app (lab profile, mock keychain, lab HOME;
# see lab.py), and writes one transcript per check into ../evidence/. Every line starting with
# "$ " is the exact command; the lines after it are its output.
#
#   bash harness/record_evidence.sh          (from examples/obsidian-kg-claims/)
#
# Needs macOS, /Applications/Obsidian.app (1.12+ for the CLI) and python3. A fresh lab
# profile downloads the current Obsidian app code from GitHub once (the app's own updater).
set -euo pipefail
cd "$(dirname "$0")/.."
H=harness/lab.py
EV=evidence
mkdir -p "$EV"
LAB=$(mktemp -d /tmp/mod-anything-lab.XXXX)
SLUGS="concept/tide-table concept/sourdough-starter concept/lighthouse concept/bicycle-gearing concept/garden-map tool/garden-map"

# run FILE CMD...: append "$ CMD" and its output to FILE (CLI commands go through lab.py cli)
run() { local f=$1; shift; echo "\$ obsidian $*" >>"$f"; python3 "$H" cli "$LAB" "$@" >>"$f" 2>&1 || echo "(exit $?)" >>"$f"; }
note() { local f=$1; shift; echo "# $*" >>"$f"; }
# shot NAME FILE: Obsidian's dev:screenshot sometimes returns before (or without) writing the
# file; retry until it exists, then copy it into evidence/. Fails loudly if it never appears.
shot() {
  local name=$1 f=$2 i
  for i in 1 2 3; do
    run "$f" dev:screenshot "path=$LAB/$name"
    for _ in $(seq 1 20); do [ -s "$LAB/$name" ] && { cp "$LAB/$name" "$EV/$name"; return 0; }; sleep 0.5; done
    echo "# screenshot attempt $i wrote no file; retrying" >>"$f"
  done
  echo "ERROR: $name was never written" >&2; return 1
}
claims() { run "$1" dev:dom "selector=.markdown-reading-view .kg-claim" all text; }

cleanup() { python3 "$H" stop "$LAB" >/dev/null 2>&1 || true; }
trap cleanup EXIT

python3 "$H" setup "$LAB" --entities harness/fixtures/entities --slugs $SLUGS >/dev/null
python3 "$H" launch "$LAB" >/dev/null

f=$EV/cli-session.txt; : >"$f"
note "$f" "session: enable the plugin in the lab vault, open the fixture note in reading view"
run "$f" version
run "$f" plugins:restrict off
python3 "$H" install "$LAB" >/dev/null; echo "\$ lab.py install (copies plugin/ into <lab>/vault/.obsidian/plugins/kg-claims)" >>"$f"
run "$f" reload
sleep 3
run "$f" plugin:enable id=kg-claims
run "$f" open path=Notes/reading-test.md
sleep 3
note "$f" "expected: five claims (the five entity links, the alias and #heading forms included); none for [[plain-note]] or [[no-such-entity]]"
claims "$f"
note "$f" "the hover title carries the same claim"
run "$f" dev:dom "selector=a.internal-link[data-kg-claim]" all attr=title
shot reading-view.png "$f"

f=$EV/cli-live-update.txt; : >"$f"
note "$f" "live update: change the LAB COPY of bicycle-gearing's core_claim through the app; the open note updates"
run "$f" property:set name=core_claim "value=LAB EDIT: claim changed while the note is open" path=entities/concept/bicycle-gearing.md
sleep 2
claims "$f"

f=$EV/cli-restart.txt; : >"$f"
note "$f" "restart: stop the lab instance by PID, launch again, no other action"
python3 "$H" stop "$LAB" >>"$f" 2>&1
python3 "$H" launch "$LAB" >>"$f" 2>&1
sleep 3
run "$f" plugins:enabled filter=community
run "$f" open path=Notes/reading-test.md
sleep 3
claims "$f"
shot after-restart.png "$f"

f=$EV/cli-disable.txt; : >"$f"
note "$f" "uninstall path: disabling the plugin must remove everything it added"
run "$f" plugin:disable id=kg-claims
sleep 1
run "$f" dev:dom "selector=.kg-claim" total
run "$f" dev:dom "selector=a.internal-link[data-kg-claim]" total

echo "lab: $LAB"
