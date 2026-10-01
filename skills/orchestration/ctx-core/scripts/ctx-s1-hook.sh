#!/bin/sh
# The registered command for one System 1 stage:
#   CTX_S1=1 CTX_S1_STAGES=<csv> /bin/sh .../ctx-s1-hook.sh <stage>
#
# Every stage is off unless CTX_S1=1 and the stage (or "all") is listed in
# CTX_S1_STAGES; a file at ~/.config/ctx/s1-off turns every stage off without
# touching settings.json. The checks are shell builtins, so a stage that is off
# costs one /bin/sh and no Python.
#
# Otherwise it execs the interpreter (so SIGTERM reaches the hook's own handler,
# which exits 0) on a tiny loader rather than on the script itself: if the
# script is gone or unreadable by the time Python opens it (a branch switch in
# the checkout), the loader exits 0. Python asked to run a missing script exits
# 2, and exit 2 from a PreToolUse hook blocks the tool call. -I keeps a module in
# the session's cwd from being imported; -S skips `site`.
[ "${CTX_S1:-0}" = 1 ] || exit 0
case ",${CTX_S1_STAGES:-}," in
  *",$1,"* | *",all,"*) ;;
  *) exit 0 ;;
esac
[ -e "${HOME:-/nonexistent}/.config/ctx/s1-off" ] && exit 0
here=${0%/*}
hook="$here/ctx_s1_hook.py"
py=${CTX_PYTHON:-python3}
[ -f "$hook" ] || exit 0
command -v "$py" >/dev/null 2>&1 || exit 0
exec "$py" -I -S -c '
import sys
p = sys.argv[1]
try:
    with open(p, "rb") as fh:
        code = compile(fh.read(), p, "exec")
except BaseException:
    raise SystemExit(0)
sys.argv = sys.argv[1:]
exec(code, {"__name__": "__main__", "__file__": p})
' "$hook" "$@"
