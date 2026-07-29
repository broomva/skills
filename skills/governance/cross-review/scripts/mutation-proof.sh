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
# Test output lives OUTSIDE the copied tree. Writing it inside made the runner's
# own litter part of the fixture: a test merely counting files at the root saw
# one harness file in the baseline and two in the mutated run, and was reported
# PROVEN without ever referencing the target. A false PROVEN is the worse
# polarity for a proof tool — it manufactures the evidence for "mutation-proven".
LOGDIR=""
VERDICT_REACHED=0

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
    for d in "$SCRATCH" "$LOGDIR"; do
        [ -n "$d" ] && [ -d "$d" ] || continue
        if [ "$KEEP_SCRATCH" = "1" ]; then
            echo "  [keep] retained: $d"
        else
            rm -rf -- "$d"
        fi
    done
}
trap cleanup EXIT

# Any failure before a verdict is a SETUP failure, and must not borrow exit 1 —
# that is the documented UNPROVEN code. Reporting "your test is decoration" when
# the truth is "the runner fell over" is the worst lie this tool can tell, and it
# is what a symlinked target used to produce.
# shellcheck disable=SC2317,SC2329
on_err() {
    err_rc=$?
    if [ "$VERDICT_REACHED" = "0" ]; then
        echo "mutation-proof: aborted before a verdict (status $err_rc)." >&2
        echo "  No claim is made about the test. This is a setup failure, not UNPROVEN." >&2
        exit 2
    fi
    exit "$err_rc"
}
trap on_err ERR

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
    # A symlinked FINAL component defeats containment: abs_path resolves the
    # directory but appends the basename verbatim, tar preserves the link into
    # scratch, and `cat >` follows it — writing the stub through the link into a
    # real file outside the root. This workspace is full of such links (the
    # Obsidian vault, skills/bookkeeping, ~/.claude). Refuse, and name the real
    # file so the caller can target it directly.
    if [ -L "$t" ]; then
        link_dest=$(readlink "$t" 2>/dev/null || echo "?")
        echo "mutation-proof: target '$t' is a symlink -> $link_dest" >&2
        echo "  Refusing: mutating it would write THROUGH the link into the real" >&2
        echo "  file, which may live outside --root and would not be restored." >&2
        echo "  Point --target at the real file, and --root at a tree containing it." >&2
        exit 2
    fi
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
    # Strip NULs before the command substitution sees them: on a binary target
    # bash otherwise prints "ignored null byte in input" to stderr, and the user
    # gets a warning ahead of the correct, clear rejection.
    first=$(head -c 512 "$f" 2>/dev/null | tr -d '\000' | head -1 || true)
    case "$first" in
        '#!'*bash*|'#!'*/sh*|'#!'*zsh*|'#!'*' sh'*) echo shell; return ;;
        '#!'*python*)                               echo python; return ;;
        '#!'*node*|'#!'*bun*|'#!'*deno*)            echo node; return ;;
    esac
    echo unknown
}

write_stub() {
    # $1 = file in the scratch copy, $2 = kind
    #
    # Every branch unlinks first. Never write through a path that might be a
    # link: `cat >` follows one and lands in the real file, outside the scratch
    # copy and outside --root. The -L guard on the target is the primary
    # defence; this is the one that holds when a link arrives some other way.
    rm -f -- "$1"
    case "$2" in
        shell)
            # A plain `exit 0` is not a no-op when the target is SOURCED: it
            # terminates the SOURCING shell with status 0 before any assertion
            # runs, so a genuinely discriminating test on a sourced library
            # reports UNPROVEN. That is not a failure to neuter — it forges a
            # pass. `return` is valid only in a sourced file, so this is inert
            # when sourced (functions simply never get defined) and still exits
            # 0 when executed. POSIX-safe: works under bash and dash, both ways.
            cat >"$1" <<'STUB'
#!/usr/bin/env bash
# mutation-proof stub — the real implementation was removed for this run.
return 0 2>/dev/null || true
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
        rm -f -- "$dst"   # never redirect through a possible link
        git -C "$ROOT_ABS" show "$REF:$gitrel$rel" >"$dst"
        chmod +x "$dst" 2>/dev/null || true
        echo "revert to $REF"
    else
        # Absent at that ref: the pre-fix state IS absence. Deleting is the
        # faithful mutation, not an error — but it is a DIFFERENT experiment
        # from reverting content, and the verdict says so, because "the suite
        # noticed a missing file" is much weaker than "the suite noticed the fix
        # was undone". A renamed path lands here silently otherwise.
        rm -f -- "$dst"
        echo "revert to $REF (absent at that ref → DELETED, not reverted)"
    fi
}

restore_target() {
    local rel="$1"
    mkdir -p "$(dirname "$SCRATCH/$rel")"
    rm -f -- "$SCRATCH/$rel"
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
        RC=$?
    else
        # Stock macOS has neither timeout nor gtimeout, and this runner is fired
        # from a pre-push hook: an infinite-loop test would wedge the hook
        # forever on the primary dev platform. Watchdog in plain bash rather
        # than silently dropping the bound the caller asked for.
        ( cd "$SCRATCH" && MUTATION_PROOF_ACTIVE=1 bash -c "$TEST_CMD" ) >"$out" 2>&1 &
        local pid=$! waited=0
        while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt "$TIMEOUT_SECS" ]; do
            sleep 1
            waited=$((waited + 1))
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid" 2>/dev/null
            sleep 1
            kill -KILL "$pid" 2>/dev/null
            wait "$pid" 2>/dev/null
            RC=124   # match GNU timeout's convention
            echo "[mutation-proof] test command exceeded ${TIMEOUT_SECS}s and was killed" >>"$out"
        else
            wait "$pid"
            RC=$?
        fi
    fi
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

# Evidence is LEG-SCOPED, never a bare top-level `evidence` key. The consumer's
# `shows_evidence` is per-RECORD: it reads `rec["evidence"]` and stars the whole
# record as evidenced. Writing this block at the top level would therefore make
# it vouch for fires_on_trigger and silent_on_non_trigger — the two legs this
# runner explicitly disclaims — turning a hand-written `yes*` into `yes`.
# Verified against BRO-2035 by execution: that upgrade happens.
evidence = entry.get("evidence_by_leg")
if not isinstance(evidence, dict):
    evidence = {}
evidence[LEG] = {
    "producer": "mutation-proof v0.0.1 (broomva/skills cross-review)",
    "recorded_at": datetime.datetime.now(datetime.timezone.utc)
                   .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "strategy": strategy + (f" (ref {ref})" if ref else ""),
    "mutation": mutation,
    "test_command": test_cmd,
    "exit_code_baseline": int(rc_before),
    "exit_code_mutated": int(rc_after),
    "checks_flipped": None if flipped == "n/a" else int(flipped),
}
entry["evidence_by_leg"] = evidence
doc["probes"][key] = entry

# A record carrying `true` legs that nothing has evidenced is the exact shape
# the probe receipt was introduced to expose, and merging into it silently would
# leave this runner's honest leg as cover for two unevidenced ones.
UNOBSERVED = ("fires_on_trigger", "silent_on_non_trigger")
bare = [leg for leg in UNOBSERVED
        if entry.get(leg) is True and leg not in evidence]
if bare:
    print("mutation-proof: WARNING — receipt entry %r already asserts %s as true "
          "with no evidence recorded for %s." % (key, ", ".join(bare),
                                                 "it" if len(bare) == 1 else "them"),
          file=sys.stderr)
    print("  This run evidenced only %s. Those legs remain unproven claims; "
          "nothing here vouches for them." % LEG, file=sys.stderr)

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
    echo "  Timeout:     ${TIMEOUT_SECS}s (bash watchdog — no timeout/gtimeout on PATH)"
else
    echo "  Timeout:     ${TIMEOUT_SECS}s ($TIMEOUT_BIN)"
fi
echo ""

copy_tree
LOGDIR=$(mktemp -d "${TMPDIR:-/tmp}/mutproof-logs.XXXXXX")
echo "  Scratch:     $SCRATCH"
echo "  Logs:        $LOGDIR  (outside the tree under test)"
echo ""

# ─── Baseline ─────────────────────────────────────────────────────────────
BASE_OUT="$LOGDIR/baseline.log"
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
ANY_INCONCLUSIVE=0
TARGET_N=0
while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    TARGET_N=$((TARGET_N + 1))
    VERDICT_REACHED=0

    LABEL=$(apply_mutation "$rel")

    # Did the mutation actually change anything? Nothing else checks. `--ref
    # HEAD~1` when the file last changed in an earlier commit — the likeliest
    # off-by-one there is — leaves the target byte-identical, and the run then
    # reports UNPROVEN having never once executed the suite without the code.
    # With --emit-receipt that files a durable, false `went_red: false`.
    IDENTICAL=0
    if [ -e "$SCRATCH/$rel" ] && cmp -s "$SCRATCH/$rel" "$ROOT_ABS/$rel"; then
        IDENTICAL=1
    fi

    MUT_OUT="$LOGDIR/mutated-${TARGET_N}.log"
    if [ "$IDENTICAL" = "1" ]; then
        RC_AFTER="$RC_BEFORE"
        MUT_PARSED=0; MUT_OK=0; MUT_FAIL=0
    else
        run_test "$MUT_OUT"
        RC_AFTER=$RC
        count_marks "$MUT_OUT"
        MUT_PARSED=$COUNT_PARSED
        MUT_OK=$COUNT_OK
        MUT_FAIL=$COUNT_FAIL
    fi
    restore_target "$rel"

    BASE_TOTAL=$((BASE_OK + BASE_FAIL))
    MUT_TOTAL=$((MUT_OK + MUT_FAIL))

    # Flip count: only claimed when both runs parsed AND the suite ran the same
    # number of checks. A suite that aborted early has a different shape, and
    # subtracting across shapes would invent a number.
    FLIPPED="n/a"
    FLIP_NOTE=""
    if [ "$BASE_PARSED" = "1" ] && [ "$MUT_PARSED" = "1" ]; then
        if [ "$BASE_TOTAL" = "$MUT_TOTAL" ]; then
            FLIPPED=$((MUT_FAIL - BASE_FAIL))
        else
            FLIP_NOTE="check count changed ${BASE_TOTAL} → ${MUT_TOTAL}: the suite did not run the same shape, so no flip count is claimed"
        fi
    else
        FLIP_NOTE="output is not parseable as per-check results — exit codes only"
    fi

    # A green mutated run that emitted FEWER checks than the baseline did not
    # pass — it did not RUN. The classic producer is a sourced library: any stub
    # that terminates the sourcing shell early exits it 0 with the assertions
    # never reached. Reporting that as UNPROVEN accuses a working test of being
    # decoration, so the collapse outranks the exit code.
    COLLAPSED=0
    if [ "$BASE_PARSED" = "1" ] && [ "$RC_AFTER" = "0" ]; then
        if [ "$MUT_PARSED" = "0" ] || [ "$MUT_TOTAL" -lt "$BASE_TOTAL" ]; then
            COLLAPSED=1
        fi
    fi

    echo "  ─── mutated: $rel ───"
    echo "  Mutation:    $LABEL"
    if [ "$IDENTICAL" = "1" ]; then
        echo "  (no test run — the mutation changed nothing)"
    else
        echo "  exit $RC_AFTER  ·  $(fmt_counts "$MUT_PARSED" "$MUT_OK" "$MUT_FAIL")"
    fi
    echo ""

    VERDICT="UNPROVEN"
    if [ "$IDENTICAL" = "1" ]; then
        VERDICT="INCONCLUSIVE"
        echo "  INCONCLUSIVE — the mutation was a no-op."
        if [ "$STRATEGY" = "revert" ]; then
            echo "    $rel is byte-identical at $REF, so the suite never ran without"
            echo "    the code under proof. Pick a ref where the file actually differs"
            echo "    (git log --oneline -- $rel)."
        else
            echo "    The stub is byte-identical to the target, so nothing was neutered."
        fi
    elif [ "$RC_AFTER" != "0" ]; then
        VERDICT="PROVEN"
        echo "  PROVEN — the test discriminates."
        echo "    exit $RC_BEFORE → $RC_AFTER with $rel neutered."
        if [ "$FLIPPED" != "n/a" ]; then
            echo "    $FLIPPED check(s) flipped ok → FAIL."
        else
            echo "    $FLIP_NOTE"
        fi
        case "$LABEL" in
            *DELETED*)
                echo "    CAVEAT: the mutation DELETED the file rather than reverting its"
                echo "    contents. This proves the suite notices the file missing, which"
                echo "    is weaker than proving it notices the fix undone. A renamed path"
                echo "    lands here — check the ref if you expected a content revert." ;;
        esac
    elif [ "$COLLAPSED" = "1" ]; then
        VERDICT="INCONCLUSIVE"
        echo "  INCONCLUSIVE — the mutated run emitted fewer checks than the baseline."
        echo "    ${BASE_TOTAL} check(s) before, $([ "$MUT_PARSED" = "1" ] && echo "$MUT_TOTAL" || echo 0) after, exit 0."
        echo "    The suite did not pass; it did not RUN."
        echo "    A stub that ends the sourcing shell produces exactly this shape."
        echo "    Nothing is claimed about whether the test discriminates."
    else
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

    case "$VERDICT" in
        UNPROVEN)     ANY_UNPROVEN=1 ;;
        INCONCLUSIVE) ANY_INCONCLUSIVE=1 ;;
    esac

    if [ -n "$RECEIPT" ]; then
        echo ""
        if [ "$VERDICT" = "INCONCLUSIVE" ]; then
            # No observation, so no leg. This is the case the receipt would
            # otherwise poison with a durable false `false`.
            echo "  [receipt] nothing written — the neuter leg was not observed."
        else
            WENT_RED=false
            if [ "$VERDICT" = "PROVEN" ]; then WENT_RED=true; fi
            KEY="$rel"
            if [ -n "$RECEIPT_KEY" ]; then KEY="$RECEIPT_KEY"; fi
            emit_receipt "$KEY" "$WENT_RED" "$LABEL" "$RC_BEFORE" "$RC_AFTER" "$FLIPPED"
        fi
    fi
    echo ""
    echo "mutation-proof: verdict=$VERDICT target=$rel strategy=$STRATEGY rc_before=$RC_BEFORE rc_after=$RC_AFTER flipped=$FLIPPED"
    echo ""
    VERDICT_REACHED=1
done <<EOF
$RELS
EOF

if [ "$ANY_UNPROVEN" = "1" ]; then
    exit 1
fi
if [ "$ANY_INCONCLUSIVE" = "1" ]; then
    exit 3
fi
exit 0
