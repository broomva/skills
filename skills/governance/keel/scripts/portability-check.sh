#!/usr/bin/env bash
# portability-check.sh — refuse to ship a machine-specific path.
#
# Keel is installed by strangers (`npx skills add broomva/skills --skill keel`)
# and cloned by contributors. Anything committed here runs on their machine, not
# ours, so a hardcoded `/Users/<someone>/...` is a latent break that is invisible
# on the machine that introduced it — the one place it happens to work.
#
# Anchored by construction: it greps the actual committed bytes and exits
# non-zero. The signal comes from the file contents, which no assertion in this
# skill can talk out of.
#
# Usage:
#   scripts/portability-check.sh            # scan tracked files under the skill
#   scripts/portability-check.sh --staged   # scan staged files (pre-commit)

set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SKILL_DIR" || exit 1

MODE="${1:-tracked}"
if [ "$MODE" = "--staged" ]; then
    mapfile -t FILES < <(git diff --cached --name-only --diff-filter=ACM -- "$SKILL_DIR" \
                         | sed "s|^skills/governance/keel/||")
    SCOPE="staged"
else
    mapfile -t FILES < <(git ls-files -- "$SKILL_DIR" | sed "s|^skills/governance/keel/||")
    SCOPE="tracked"
fi

# ── Exemptions, stated out loud rather than silently skipped ────────────────
# This script is exempt because it contains the patterns it searches for.
#
# Measurement artifacts under reports/ are PARTIALLY exempt, and the boundary
# matters. Keel's whole method is to carry the LITERAL snippet of a target's
# verification edge into `raw` and reason over the real text, because a summary
# is already a judgment. So a report legitimately quotes whatever the measured
# repository contained — openai-python's CI really does reference `/home/codex`,
# and rewriting that would falsify the evidence a reader is meant to check the
# verdict against.
#
# But the old form of this exemption covered reports/ WHOLESALE, and delegated
# our own paths to a publish step that rewrote them at the publish boundary.
# That step does not exist any more, and while it did, the exemption is exactly
# what let a curve disclosure ship reading "15 runs from /Users/<someone>/keel/
# reports" and a probe warning name an absolute shadowed-version path. The gate
# was green the whole time, over the one directory where the defect lived.
#
# So reports/ is exempt from rule 1 for QUOTED CONTENT only. An absolute home
# path whose remainder names a Keel-owned artifact is ours, not the target's,
# and is always a finding — that discriminator holds because our workspace
# path contains "keel" and a measured third-party target's does not. When Keel
# measures Keel, the path is genuinely ours and genuinely should be caught.
is_exempt() {
    case "$1" in
        scripts/portability-check.sh) return 0 ;;
        *) return 1 ;;
    esac
}

# Files whose absolute home paths are quoted evidence from a measured target
# rather than our own configuration.
is_quoted_evidence() {
    case "$1" in
        reports/*|tests/fixtures/*) return 0 ;;
        *) return 1 ;;
    esac
}

# Operational files: read by a tool at run time, so a personal-workspace path
# here is a functional break, not a stale sentence.
is_operational() {
    case "$1" in
        scripts/*|schemas/*|probes/*|templates/*|package.json|tsconfig.json) return 0 ;;
        *) return 1 ;;
    esac
}

fail=0
exempted=()

report() { printf '  %-52s %s\n' "$1" "$2"; fail=1; }

for f in "${FILES[@]}"; do
    [ -f "$f" ] || continue
    if is_exempt "$f"; then exempted+=("$f"); continue; fi

    if is_quoted_evidence "$f"; then
        # Rule 1b — OUR path, wearing a measurement's clothes. An absolute home
        # path that goes on to name a Keel artifact was written by this project
        # about itself; nothing a third-party target contains looks like this.
        while IFS= read -r hit; do
            [ -n "$hit" ] && report "$f:${hit%%:*}" "own machine path in a measurement artifact"
        done < <(grep -nE '/(Users|home)/[A-Za-z0-9._-]+/[^ "]*keel' "$f" 2>/dev/null | head -5)
        continue
    fi

    # Rule 1 — absolute home directories. Breaks on every other machine.
    while IFS= read -r hit; do
        [ -n "$hit" ] && report "$f:${hit%%:*}" "absolute home path: $(echo "${hit#*:}" | grep -oE '/(Users|home)/[A-Za-z0-9._-]+' | head -1)"
    done < <(grep -nE '/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+' "$f" 2>/dev/null \
             | grep -vE '/home/runner' | head -5)

    # Rule 2 — a personal workspace root, in a file a tool actually reads.
    if is_operational "$f"; then
        while IFS= read -r hit; do
            [ -n "$hit" ] && report "$f:${hit%%:*}" "personal workspace ref (use discovery, not a fixed root)"
        done < <(grep -nE '~/broomva|\$HOME/broomva|\$\{HOME\}/broomva' "$f" 2>/dev/null | head -5)
    fi
done

echo "[portability] scanned ${#FILES[@]} $SCOPE file(s)"
if [ ${#exempted[@]} -gt 0 ]; then
    echo "[portability] exempt (contains its own search patterns): ${#exempted[@]}"
    for e in "${exempted[@]}"; do echo "    - $e"; done
fi

if [ "$fail" -ne 0 ]; then
    echo "[portability] FAIL — commit machine-independent paths instead."
    exit 1
fi
echo "[portability] OK"
