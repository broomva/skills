#!/usr/bin/env bash
# mutation-proof.sh — bstack P20 mutation-proof runner
#
# "Every fix mutation-proven" is a P20 discipline that, until this script, lived
# only in prose. This makes it machine-checkable: neuter the target, re-run the
# test command, and compare.
#
#   green before + RED after   → the test discriminates. PROVEN.
#   green before + GREEN after → the test is decoration with respect to the
#                                target. UNPROVEN. That is the finding.
#   not green before           → nothing can be proven. INCONCLUSIVE.
#
# The working tree is never mutated. The tree is copied to a scratch dir under
# mktemp, the copy is mutated, and the test command runs with cwd = the copy.
#
# Usage:
#   mutation-proof run --target PATH --test CMD [options]
#   mutation-proof version
#   mutation-proof --help
#
# Options:
#   --target PATH      File to neuter. Absolute, or relative to --root when
#                      --root is given, else relative to the current directory.
#                      Repeatable, and accepts a comma-separated list. Each
#                      target is mutated alone, from a pristine copy.
#   --test CMD         Test command. Run via `bash -c` with cwd = scratch copy.
#   --strategy NAME    stub (default) | revert
#                        stub   — replace the target with a trivially-succeeding
#                                 no-op for its type (shell / python / node),
#                                 detected by extension then shebang.
#                        revert — restore the target from a git ref, so a fix is
#                                 proven against its own pre-fix state.
#   --ref REF          Git ref for --strategy revert (e.g. HEAD~1, origin/main).
#   --root DIR         Tree root to copy. Default: git toplevel containing the
#                      first target, else that target's directory.
#   --paths LIST       Comma-separated subset of --root to copy instead of the
#                      whole tree. Use on large repos.
#   --include-git      Also copy .git (excluded by default). Needed when the
#                      test command itself depends on repo history.
#   --emit-receipt P   Write (merge into) a probe-receipt JSON at P, in the
#                      unhobble `--probe-receipts` schema. ONLY the leg this
#                      runner actually observes is written:
#                      `neutered_check_went_red`. See "Receipts" below.
#   --receipt-key K    Receipt key for the target, when the reference as written
#                      in the audited prose differs from its path under --root.
#                      Single-target runs only.
#   --timeout SECS     Per test run (default 300). Needs timeout/gtimeout on
#                      PATH; without one, runs unbounded and says so.
#   --max-mb N         Refuse to copy more than N MB (default 512).
#   --keep-scratch     Leave the scratch dir behind for inspection.
#
# Exit codes:
#   0  PROVEN        every target's test went green → red
#   1  UNPROVEN      at least one target's test stayed green after mutation
#   2  usage or setup error
#   3  INCONCLUSIVE  the baseline was not green, so nothing can be proven
#
# Environment set for the test command:
#   MUTATION_PROOF_ACTIVE=1   — lets a suite skip its own self-referential case
#                               instead of recursing forever.
#
# Receipts (--emit-receipt):
#   unhobble's probe has three legs — fires_on_trigger, silent_on_non_trigger,
#   neutered_check_went_red — and reads a receipt as `fires` only when all three
#   are true. This runner owns exactly one of them: it neuters the target and
#   observes whether the check went red. It writes that leg, with its evidence,
#   and DELIBERATELY LEAVES THE OTHER TWO ABSENT, so unhobble reads `incomplete`.
#   Defaulting them to true for convenience would forge two untested legs and
#   hand back a free-to-delete verdict on no evidence — the same defect the
#   receipt exists to close, one level up. An honest `incomplete` is correct.
#
#   `neutered_check_went_red: false` is a RESULT, not a gap: it means the probe
#   ran and the check did not go red. It is written. Nothing is written when the
#   baseline was not green, because then nothing was observed.
#
#   Requires python3 (JSON, atomically). Merging preserves legs recorded by
#   other producers; only this runner's leg and its evidence block are replaced.

set -euo pipefail

# ─── Defaults ─────────────────────────────────────────────────────────────
COMMAND=""
TARGETS=""
TEST_CMD=""
STRATEGY="stub"
REF=""
ROOT=""
PATHS=""
INCLUDE_GIT=0
TIMEOUT_SECS=300
MAX_MB=512
KEEP_SCRATCH=0
RECEIPT=""
RECEIPT_KEY=""

SCRATCH=""

die_usage() {
    echo "mutation-proof: $1" >&2
    echo "  run with --help for usage" >&2
    exit 2
}

# Invoked by the EXIT trap below, which shellcheck does not follow. Older
# versions flag the body as unreachable (SC2317), newer ones flag the function
# as uncalled (SC2329); CI and dev machines disagree on which, so disable both.
# shellcheck disable=SC2317,SC2329
cleanup() {
    if [ -n "$SCRATCH" ] && [ -d "$SCRATCH" ]; then
        if [ "$KEEP_SCRATCH" = "1" ]; then
            echo "  [keep] scratch retained: $SCRATCH"
        else
            rm -rf -- "$SCRATCH"
        fi
    fi
}
trap cleanup EXIT

# ─── Arg parsing ──────────────────────────────────────────────────────────
if [ $# -eq 0 ]; then
    echo "mutation-proof: no command. Run with --help" >&2
    exit 2
fi

COMMAND="$1"
shift

case "$COMMAND" in
    --help|-h|help)
        # `\?` is a GNU extension BSD sed does not honour, so strip in two
        # POSIX steps instead — the help text renders identically on macOS and CI.
        sed -n '/^# Usage:/,/^set -euo/p' "${BASH_SOURCE[0]}" \
            | sed '$d' \
            | sed -e 's/^#$//' -e 's/^# //'
        exit 0
        ;;
    version)
        echo "mutation-proof v0.0.1 (bstack P20 — does the test discriminate?)"
        exit 0
        ;;
    run) ;;
    *)
        echo "mutation-proof: unknown command '$COMMAND' (try: run | version | --help)" >&2
        exit 2
        ;;
esac

add_targets() {
    # Split a comma-separated list into the newline-separated TARGETS accumulator.
    local raw="$1" item
    local IFS=','
    for item in $raw; do
        [ -n "$item" ] || continue
        TARGETS="${TARGETS}${item}
"
    done
}

need_value() {
    # $1 flag name, $2 remaining arg count
    [ "$2" -gt 0 ] || die_usage "$1 requires a value"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --target=*)     add_targets "${1#*=}" ;;
        --target)       shift; need_value --target $#; add_targets "$1" ;;
        --test=*)       TEST_CMD="${1#*=}" ;;
        --test)         shift; need_value --test $#; TEST_CMD="$1" ;;
        --strategy=*)   STRATEGY="${1#*=}" ;;
        --strategy)     shift; need_value --strategy $#; STRATEGY="$1" ;;
        --ref=*)        REF="${1#*=}" ;;
        --ref)          shift; need_value --ref $#; REF="$1" ;;
        --root=*)       ROOT="${1#*=}" ;;
        --root)         shift; need_value --root $#; ROOT="$1" ;;
        --paths=*)      PATHS="${1#*=}" ;;
        --paths)        shift; need_value --paths $#; PATHS="$1" ;;
        --timeout=*)    TIMEOUT_SECS="${1#*=}" ;;
        --timeout)      shift; need_value --timeout $#; TIMEOUT_SECS="$1" ;;
        --max-mb=*)     MAX_MB="${1#*=}" ;;
        --max-mb)       shift; need_value --max-mb $#; MAX_MB="$1" ;;
        --emit-receipt=*) RECEIPT="${1#*=}" ;;
        --emit-receipt)   shift; need_value --emit-receipt $#; RECEIPT="$1" ;;
        --receipt-key=*)  RECEIPT_KEY="${1#*=}" ;;
        --receipt-key)    shift; need_value --receipt-key $#; RECEIPT_KEY="$1" ;;
        --include-git)  INCLUDE_GIT=1 ;;
        --keep-scratch) KEEP_SCRATCH=1 ;;
        *) die_usage "unknown flag '$1'" ;;
    esac
    shift
done

[ -n "$TARGETS" ]  || die_usage "run requires --target PATH"
[ -n "$TEST_CMD" ] || die_usage "run requires --test CMD"

case "$STRATEGY" in
    stub) ;;
    revert)
        [ -n "$REF" ] || die_usage "--strategy revert requires --ref REF"
        ;;
    *) die_usage "unknown strategy '$STRATEGY' (try: stub | revert)" ;;
esac

case "$TIMEOUT_SECS" in ''|*[!0-9]*) die_usage "--timeout must be a whole number of seconds" ;; esac
case "$MAX_MB"       in ''|*[!0-9]*) die_usage "--max-mb must be a whole number" ;; esac

if [ -n "$RECEIPT" ]; then
    command -v python3 >/dev/null 2>&1 || die_usage "--emit-receipt needs python3 on PATH"
fi
if [ -n "$RECEIPT_KEY" ]; then
    [ -n "$RECEIPT" ] || die_usage "--receipt-key has no effect without --emit-receipt"
    # One key cannot stand for several targets, and silently applying it to the
    # first would file a real observation under the wrong mechanism.
    N_TARGETS=$(printf '%s' "$TARGETS" | grep -c . || true)
    [ "$N_TARGETS" = "1" ] || die_usage "--receipt-key requires exactly one --target (got $N_TARGETS)"
fi

# ─── Path resolution ──────────────────────────────────────────────────────
abs_path() {
    # Absolute, symlink-resolved path for a file that must already exist.
    local d b
    d=$(cd "$(dirname "$1")" 2>/dev/null && pwd -P) || return 1
    b=$(basename "$1")
    printf '%s/%s\n' "$d" "$b"
}

FIRST_TARGET=$(printf '%s' "$TARGETS" | head -1)
ROOT_GIVEN=1
[ -n "$ROOT" ] || ROOT_GIVEN=0

if [ -z "$ROOT" ]; then
    # No --root: the first target has to resolve from the current directory,
    # and the tree to copy is the repo it lives in.
    [ -e "$FIRST_TARGET" ] || die_usage "target '$FIRST_TARGET' does not exist"
    FT_DIR=$(cd "$(dirname "$FIRST_TARGET")" && pwd -P)
    ROOT=$(git -C "$FT_DIR" rev-parse --show-toplevel 2>/dev/null || echo "$FT_DIR")
fi
[ -d "$ROOT" ] || die_usage "--root '$ROOT' is not a directory"
ROOT_ABS=$(cd "$ROOT" && pwd -P)

# Map every target to a ROOT-relative path, rejecting anything outside ROOT.
# When --root is given it wins for relative targets: the flag names the tree
# under proof, and resolving against the current directory instead would
# silently mutate a same-named file in an unrelated checkout. Without --root,
# the current directory is the only sensible base.
RELS=""
while IFS= read -r t; do
    [ -n "$t" ] || continue
    case "$t" in
        /*) ;;
        *)
            if [ "$ROOT_GIVEN" = "1" ] && [ -e "$ROOT_ABS/$t" ]; then
                t="$ROOT_ABS/$t"
            elif [ ! -e "$t" ] && [ -e "$ROOT_ABS/$t" ]; then
                t="$ROOT_ABS/$t"
            fi
            ;;
    esac
    [ -e "$t" ] || die_usage "target '$t' does not exist (looked in . and $ROOT_ABS)"
    [ -f "$t" ] || die_usage "target '$t' is not a regular file"
    tabs=$(abs_path "$t") || die_usage "cannot resolve target '$t'"
    case "$tabs" in
        "$ROOT_ABS"/*) ;;
        *) die_usage "target '$t' is outside --root '$ROOT_ABS'" ;;
    esac
    RELS="${RELS}${tabs#"$ROOT_ABS"/}
"
done <<EOF
$TARGETS
EOF

# With --paths, a target outside the copied subset would be mutated in a tree the
# test never sees — a silent false UNPROVEN. Reject it instead.
if [ -n "$PATHS" ]; then
    while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        covered=0
        old_ifs="$IFS"; IFS=','
        for p in $PATHS; do
            p="${p%/}"
            case "$rel" in "$p"|"$p"/*) covered=1 ;; esac
        done
        IFS="$old_ifs"
        [ "$covered" = "1" ] || die_usage "target '$rel' is not under --paths '$PATHS'"
    done <<EOF
$RELS
EOF
fi

# ─── Timeout binary ───────────────────────────────────────────────────────
TIMEOUT_BIN=""
if command -v timeout >/dev/null 2>&1; then
    TIMEOUT_BIN="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
    TIMEOUT_BIN="gtimeout"
fi

# ─── Scratch copy ─────────────────────────────────────────────────────────
copy_tree() {
    SCRATCH=$(mktemp -d "${TMPDIR:-/tmp}/mutproof.XXXXXX")
    local kb=0 used
    if [ -n "$PATHS" ]; then
        local old_ifs="$IFS"; IFS=','
        for p in $PATHS; do
            [ -e "$ROOT_ABS/$p" ] || { IFS="$old_ifs"; die_usage "--paths entry '$p' not found under $ROOT_ABS"; }
            used=$(du -sk "$ROOT_ABS/$p" 2>/dev/null | awk '{print $1}')
            kb=$((kb + ${used:-0}))
        done
        IFS="$old_ifs"
    else
        used=$(du -sk "$ROOT_ABS" 2>/dev/null | awk '{print $1}')
        kb=${used:-0}
    fi
    if [ "$kb" -gt $((MAX_MB * 1024)) ]; then
        echo "mutation-proof: refusing to copy $((kb / 1024)) MB (limit ${MAX_MB} MB)." >&2
        echo "  narrow the copy with --paths, or raise --max-mb." >&2
        exit 2
    fi

    if [ -n "$PATHS" ]; then
        local old_ifs="$IFS"; IFS=','
        for p in $PATHS; do
            ( cd "$ROOT_ABS" && tar -cf - "$p" ) | ( cd "$SCRATCH" && tar -xf - )
        done
        IFS="$old_ifs"
    elif [ "$INCLUDE_GIT" = "1" ]; then
        ( cd "$ROOT_ABS" && tar -cf - . ) | ( cd "$SCRATCH" && tar -xf - )
    else
        ( cd "$ROOT_ABS" && tar -cf - '--exclude=./.git' '--exclude=./.git/*' . ) \
            | ( cd "$SCRATCH" && tar -xf - )
    fi
}

# ─── Mutation strategies ──────────────────────────────────────────────────
detect_kind() {
    local f="$1" first
    case "$f" in
        *.sh|*.bash|*.zsh) echo shell; return ;;
        *.py)              echo python; return ;;
        *.js|*.mjs|*.cjs|*.ts) echo node; return ;;
    esac
    first=$(head -1 "$f" 2>/dev/null || true)
    case "$first" in
        '#!'*bash*|'#!'*/sh*|'#!'*zsh*|'#!'*' sh'*) echo shell; return ;;
        '#!'*python*)                               echo python; return ;;
        '#!'*node*|'#!'*bun*|'#!'*deno*)            echo node; return ;;
    esac
    echo unknown
}

write_stub() {
    # $1 = file in the scratch copy, $2 = kind
    case "$2" in
        shell)
            cat >"$1" <<'STUB'
#!/usr/bin/env bash
# mutation-proof stub — the real implementation was removed for this run.
exit 0
STUB
            ;;
        python)
            cat >"$1" <<'STUB'
#!/usr/bin/env python3
"""mutation-proof stub — the real implementation was removed for this run."""


def main() -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
STUB
            ;;
        node)
            cat >"$1" <<'STUB'
#!/usr/bin/env node
// mutation-proof stub — the real implementation was removed for this run.
process.exit(0);
STUB
            ;;
        *) return 1 ;;
    esac
}

apply_mutation() {
    # $1 = ROOT-relative path. Echoes a human label for the mutation applied.
    local rel="$1" dst="$SCRATCH/$1" kind
    if [ "$STRATEGY" = "stub" ]; then
        kind=$(detect_kind "$ROOT_ABS/$rel")
        if [ "$kind" = "unknown" ]; then
            echo "mutation-proof: cannot infer a no-op stub for '$rel'" >&2
            echo "  no known extension and no recognised shebang. Use --strategy revert --ref REF." >&2
            exit 2
        fi
        write_stub "$dst" "$kind"
        chmod +x "$dst" 2>/dev/null || true
        echo "stub ($kind)"
        return
    fi

    # revert
    if ! git -C "$ROOT_ABS" rev-parse --git-dir >/dev/null 2>&1; then
        echo "mutation-proof: --strategy revert needs --root to be inside a git repo ($ROOT_ABS is not)" >&2
        exit 2
    fi
    if ! git -C "$ROOT_ABS" rev-parse --verify --quiet "$REF" >/dev/null 2>&1; then
        echo "mutation-proof: ref '$REF' does not resolve in $ROOT_ABS" >&2
        exit 2
    fi
    # The path git knows may differ from the path relative to --root when --root
    # is a subdirectory of the repo. Resolve against the repo toplevel.
    local top gitrel
    top=$(git -C "$ROOT_ABS" rev-parse --show-toplevel)
    gitrel="${ROOT_ABS#"$top"/}"
    if [ "$gitrel" = "$ROOT_ABS" ]; then gitrel=""; else gitrel="$gitrel/"; fi
    if git -C "$ROOT_ABS" cat-file -e "$REF:$gitrel$rel" 2>/dev/null; then
        git -C "$ROOT_ABS" show "$REF:$gitrel$rel" >"$dst"
        chmod +x "$dst" 2>/dev/null || true
        echo "revert to $REF"
    else
        # Absent at that ref: the pre-fix state IS absence. Deleting is the
        # faithful mutation, not an error.
        rm -f -- "$dst"
        echo "revert to $REF (absent → deleted)"
    fi
}

restore_target() {
    local rel="$1"
    mkdir -p "$(dirname "$SCRATCH/$rel")"
    cp -p "$ROOT_ABS/$rel" "$SCRATCH/$rel"
}

# ─── Test execution ───────────────────────────────────────────────────────
RC=0
run_test() {
    # $1 = file to capture combined output into. Sets RC.
    local out="$1"
    set +e
    if [ -n "$TIMEOUT_BIN" ]; then
        ( cd "$SCRATCH" && MUTATION_PROOF_ACTIVE=1 "$TIMEOUT_BIN" "$TIMEOUT_SECS" bash -c "$TEST_CMD" ) >"$out" 2>&1
    else
        ( cd "$SCRATCH" && MUTATION_PROOF_ACTIVE=1 bash -c "$TEST_CMD" ) >"$out" 2>&1
    fi
    RC=$?
    set -e
}

# ─── Check counting ───────────────────────────────────────────────────────
# Best-effort. Two families are recognised: per-check markers ([ok]/[pass]/ok N/✓
# against [FAIL]/not ok N/✗) and a pytest-style tail summary. Anything else is
# reported as unparseable rather than guessed at — an invented count would be
# exactly the kind of decorative signal this tool exists to catch.
COUNT_OK=0
COUNT_FAIL=0
COUNT_PARSED=0
count_marks() {
    local f="$1"
    COUNT_OK=$(grep -cE '(\[(ok|OK|pass|PASS|PASSED)\])|(^ *ok [0-9])|✓' "$f" || true)
    COUNT_FAIL=$(grep -cE '(\[(FAIL|fail|FAILED|ERROR|error)\])|(^ *not ok [0-9])|✗' "$f" || true)
    if [ "$COUNT_OK" -gt 0 ] || [ "$COUNT_FAIL" -gt 0 ]; then
        COUNT_PARSED=1
        return
    fi
    # pytest-style summary line, e.g. "3 failed, 64 passed in 1.20s"
    local p f2
    p=$(grep -oE '[0-9]+ passed' "$f" | tail -1 | grep -oE '[0-9]+' || true)
    f2=$(grep -oE '[0-9]+ failed' "$f" | tail -1 | grep -oE '[0-9]+' || true)
    if [ -n "$p" ] || [ -n "$f2" ]; then
        COUNT_OK=${p:-0}
        COUNT_FAIL=${f2:-0}
        COUNT_PARSED=1
        return
    fi
    COUNT_OK=0
    COUNT_FAIL=0
    COUNT_PARSED=0
}

# ─── Probe receipt emission ───────────────────────────────────────────────
# Writes ONE leg: neutered_check_went_red. The other two legs of unhobble's
# probe describe trigger behaviour this runner never exercises, so they are
# left absent and unhobble reads `incomplete`. See the header comment.
emit_receipt() {
    # $1 key  $2 went_red (true|false)  $3 mutation label
    # $4 rc_before  $5 rc_after  $6 flipped
    if ! python3 - "$RECEIPT" "$1" "$2" "$3" "$4" "$5" "$6" "$STRATEGY" "$REF" "$TEST_CMD" <<'PY'
import datetime
import json
import os
import sys
import tempfile

(path, key, went_red, mutation, rc_before, rc_after,
 flipped, strategy, ref, test_cmd) = sys.argv[1:11]

LEG = "neutered_check_went_red"

# Merge, never clobber: another producer may own the legs this runner does not.
doc = {"probes": {}}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as fh:
            existing = json.load(fh)
        if isinstance(existing, dict) and isinstance(existing.get("probes"), dict):
            doc = existing
        else:
            print(f"mutation-proof: {path} is not a probe-receipt file "
                  "(no top-level 'probes' object); refusing to overwrite it",
                  file=sys.stderr)
            raise SystemExit(1)
    except json.JSONDecodeError as e:
        print(f"mutation-proof: {path} is not valid JSON ({e}); refusing to overwrite it",
              file=sys.stderr)
        raise SystemExit(1) from e

entry = doc["probes"].get(key)
if not isinstance(entry, dict):
    entry = {}

# The observed leg, and only the observed leg.
entry[LEG] = went_red == "true"
entry["evidence"] = {
    "producer": "mutation-proof v0.0.1 (broomva/skills cross-review)",
    "recorded_at": datetime.datetime.now(datetime.timezone.utc)
                   .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "legs_observed": [LEG],
    "legs_not_observed": ["fires_on_trigger", "silent_on_non_trigger"],
    "strategy": strategy + (f" (ref {ref})" if ref else ""),
    "mutation": mutation,
    "test_command": test_cmd,
    "exit_code_baseline": int(rc_before),
    "exit_code_mutated": int(rc_after),
    "checks_flipped": None if flipped == "n/a" else int(flipped),
}
doc["probes"][key] = entry

# Atomic: a half-written receipt read by an auditor is worse than none.
d = os.path.dirname(os.path.abspath(path)) or "."
os.makedirs(d, exist_ok=True)
fd, tmp = tempfile.mkstemp(dir=d, prefix=".mutation-proof-receipt.")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
except BaseException:
    os.unlink(tmp)
    raise
PY
    then
        echo "mutation-proof: could not write the receipt at $RECEIPT" >&2
        exit 2
    fi
    echo "  [receipt] $RECEIPT — ${1}.neutered_check_went_red = $2"
    echo "            fires_on_trigger and silent_on_non_trigger left ABSENT:"
    echo "            not observed here, so unhobble must read this as incomplete."
}

fmt_counts() {
    # $1 parsed flag, $2 ok, $3 fail
    if [ "$1" = "1" ]; then
        printf '%s ok / %s fail' "$2" "$3"
    else
        printf 'checks not parseable'
    fi
}

# ─── Header ───────────────────────────────────────────────────────────────
echo "  ┌───────────────────────────────────────────────────────────┐"
echo "  │  mutation-proof — does the test discriminate?              │"
echo "  └───────────────────────────────────────────────────────────┘"
echo ""
echo "  Root:        $ROOT_ABS"
echo "  Strategy:    $STRATEGY${REF:+ (ref $REF)}"
echo "  Test:        $TEST_CMD"
[ -n "$PATHS" ] && echo "  Paths:       $PATHS"
if [ -z "$TIMEOUT_BIN" ]; then
    echo "  Timeout:     none — no timeout/gtimeout on PATH, runs unbounded"
else
    echo "  Timeout:     ${TIMEOUT_SECS}s ($TIMEOUT_BIN)"
fi
echo ""

copy_tree
echo "  Scratch:     $SCRATCH"
echo ""

# ─── Baseline ─────────────────────────────────────────────────────────────
BASE_OUT="$SCRATCH/.mutation-proof-baseline.log"
echo "  ─── baseline (unmutated) ────────────────────────────────────"
run_test "$BASE_OUT"
RC_BEFORE=$RC
count_marks "$BASE_OUT"
BASE_PARSED=$COUNT_PARSED
BASE_OK=$COUNT_OK
BASE_FAIL=$COUNT_FAIL
echo "  exit $RC_BEFORE  ·  $(fmt_counts "$BASE_PARSED" "$BASE_OK" "$BASE_FAIL")"
echo ""

if [ "$RC_BEFORE" != "0" ]; then
    echo "  ─── verdict ─────────────────────────────────────────────────"
    echo ""
    echo "  INCONCLUSIVE — the baseline was not green (exit $RC_BEFORE)."
    echo "    Nothing can be proven about a test that does not pass to begin with."
    if [ "$INCLUDE_GIT" = "0" ] && grep -qiE 'not a git repository|fatal: .*git' "$BASE_OUT"; then
        echo "    The output mentions git: .git is excluded from the copy by default."
        echo "    Re-run with --include-git if the test needs repo history."
    fi
    echo ""
    if [ -n "$RECEIPT" ]; then
        echo "    [receipt] nothing written. The neuter leg was never observed, and a"
        echo "              receipt asserting a leg that was not observed is a forgery."
        echo ""
    fi
    echo "  ─── baseline output (last 20 lines) ─────────────────────────"
    tail -20 "$BASE_OUT" | sed 's/^/  | /'
    echo ""
    echo "mutation-proof: verdict=INCONCLUSIVE rc_before=$RC_BEFORE"
    exit 3
fi

# ─── Per-target mutations ─────────────────────────────────────────────────
ANY_UNPROVEN=0
while IFS= read -r rel; do
    [ -n "$rel" ] || continue

    LABEL=$(apply_mutation "$rel")
    MUT_OUT="$SCRATCH/.mutation-proof-mutated.log"
    run_test "$MUT_OUT"
    RC_AFTER=$RC
    count_marks "$MUT_OUT"
    MUT_PARSED=$COUNT_PARSED
    MUT_OK=$COUNT_OK
    MUT_FAIL=$COUNT_FAIL
    restore_target "$rel"

    # Flip count: only claimed when both runs parsed AND the suite ran the same
    # number of checks. A suite that aborted early has a different shape, and
    # subtracting across shapes would invent a number.
    FLIPPED="n/a"
    FLIP_NOTE=""
    if [ "$BASE_PARSED" = "1" ] && [ "$MUT_PARSED" = "1" ]; then
        BASE_TOTAL=$((BASE_OK + BASE_FAIL))
        MUT_TOTAL=$((MUT_OK + MUT_FAIL))
        if [ "$BASE_TOTAL" = "$MUT_TOTAL" ]; then
            FLIPPED=$((MUT_FAIL - BASE_FAIL))
        else
            FLIP_NOTE="check count changed ${BASE_TOTAL} → ${MUT_TOTAL}: the suite did not run the same shape, so no flip count is claimed"
        fi
    else
        FLIP_NOTE="output is not parseable as per-check results — exit codes only"
    fi

    echo "  ─── mutated: $rel ───"
    echo "  Mutation:    $LABEL"
    echo "  exit $RC_AFTER  ·  $(fmt_counts "$MUT_PARSED" "$MUT_OK" "$MUT_FAIL")"
    echo ""

    if [ "$RC_AFTER" != "0" ]; then
        echo "  PROVEN — the test discriminates."
        echo "    exit $RC_BEFORE → $RC_AFTER with $rel neutered."
        if [ "$FLIPPED" != "n/a" ]; then
            echo "    $FLIPPED check(s) flipped ok → FAIL."
        else
            echo "    $FLIP_NOTE"
        fi
    else
        ANY_UNPROVEN=1
        echo "  UNPROVEN — the test passed WITH and WITHOUT $rel."
        echo "    exit $RC_BEFORE → $RC_AFTER. This test does not discriminate on that"
        echo "    target: it is decoration with respect to it. Either the test exercises"
        echo "    a different code path than the one that matters, or 'rc 0 + empty"
        echo "    output' is indistinguishable from a dead implementation."
        if [ "$FLIPPED" != "n/a" ] && [ "$FLIPPED" != "0" ]; then
            echo "    (note: $FLIPPED check(s) did flip, but the suite still exited 0 —"
            echo "     the runner is swallowing its own failures.)"
        fi
    fi

    if [ -n "$RECEIPT" ]; then
        echo ""
        WENT_RED=false
        if [ "$RC_AFTER" != "0" ]; then WENT_RED=true; fi
        KEY="$rel"
        if [ -n "$RECEIPT_KEY" ]; then KEY="$RECEIPT_KEY"; fi
        emit_receipt "$KEY" "$WENT_RED" "$LABEL" "$RC_BEFORE" "$RC_AFTER" "$FLIPPED"
    fi
    echo ""
    echo "mutation-proof: verdict=$([ "$RC_AFTER" != "0" ] && echo PROVEN || echo UNPROVEN) target=$rel strategy=$STRATEGY rc_before=$RC_BEFORE rc_after=$RC_AFTER flipped=$FLIPPED"
    echo ""
done <<EOF
$RELS
EOF

if [ "$ANY_UNPROVEN" = "1" ]; then
    exit 1
fi
exit 0
