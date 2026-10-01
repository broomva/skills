"""Follow-through of System 1 claims inside one ablation trial.

A claim is followed when a tool call AFTER its injection opened the object the
claim came from: a Read or shell read of its file, `kg load` naming its entity,
`gh pr view|diff|checks` of its PR, by a call that ran (a failed or refused
call opened nothing). The detector is ctx-core's (ctx_s1_replay.fetch_objs),
which E1 uses for its ground truth, so E1 and E2 agree on what opens an object;
they differ on where the window starts: E1 counts from the assistant message
after the injection, E2 from the next call. A claim read in context leaves no tool call, so
follow-through is a proxy for use, not use (spec workspace#840 §6.5): a claim
that answered the question outright is NOT followed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from skill_evals.ctx_ablation import arms as arms_mod

if str(arms_mod.CTX_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(arms_mod.CTX_SCRIPTS))
import ctx_s1_replay as R  # noqa: E402


def followed(injected: Sequence[tuple[str, int]], objs: Mapping[str, Iterable[str]],
             tool_uses: Sequence[Any], workspace: Path, ran: Sequence[bool] | None = None) -> int:
    """How many injected (item id, first tool index after it) pairs a later tool
    call opened. `ran[i]` says whether call i executed (default: all did); a call
    that did not run opens nothing, and the indices stay the transcript's. Each
    item counts once."""
    if not injected:
        return 0
    where = R.Where(str(workspace), str(workspace), None, None)
    opened_at: list[set[str]] = []
    for i, tu in enumerate(tool_uses):
        inp = tu.input if isinstance(getattr(tu, "input", None), dict) else {}
        did_run = ran is None or (i < len(ran) and ran[i])
        opened_at.append(R.fetch_objs(str(tu.name), inp, where, None) if did_run else set())
    n, seen = 0, set()
    for iid, after in injected:
        if iid in seen:
            continue
        seen.add(iid)
        want = set(objs.get(iid) or [])
        if want and any(want & opened_at[i] for i in range(max(0, after), len(opened_at))):
            n += 1
    return n
