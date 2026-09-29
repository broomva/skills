#!/bin/sh
# The registered hook command: /bin/sh .../ctx-hook.sh <session-start|stop|stop-failure>
#
# Runs ctx_hook.py only if it is there, with an interpreter that is there;
# otherwise exits 0. A Python asked to run a missing file exits 2, and a Stop
# hook that exits 2 keeps its session turning, so a moved or checked-out-away
# skill must not reach Python at all. (If this wrapper itself is missing,
# /bin/sh exits 127, which Claude Code treats as a non-blocking error.)
#
# CTX_PYTHON picks the interpreter (the owner's snippet pins it); python3 on
# PATH otherwise. -I keeps a module planted in the session's cwd from being
# imported; -S skips `site` (ctx is stdlib only).
here=$(dirname "$0")
hook="$here/ctx_hook.py"
py=${CTX_PYTHON:-python3}
[ -f "$hook" ] || exit 0
command -v "$py" >/dev/null 2>&1 || exit 0
exec "$py" -I -S "$hook" "$@"
