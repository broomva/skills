"""The send gate (spec §5.7): the coordinator's SendMessage hooks.

SendMessage is a model tool fleet act can't call, so the coordinator's settings
register `fleet send-gate pre` on PreToolUse and `fleet send-gate post` on
PostToolUse and PostToolUseFailure (matcher SendMessage, 10 s).

pre checks every one of these, in order, and records the first that fails
(failed, gate_refused, naming the check) and exits 2:
  1. the ledger has an unclosed mail intent from this tick (FLEET_TICK) whose
     target.name equals tool_input.to exactly (no [ref]) and whose target.text
     equals tool_input.message;
  2. its recipient is still a fleet spawn in the ledger or an adopted session,
     and the 6 h rule holds without counting this intent;
  3. a fresh claude agents --json --all shows exactly one live row with that
     name, carrying the intent's session id.
All pass under dry run: done (would: true), exit 2. All pass live: exit 0.

post closes the intent: done with the msg_id, or failed (harness_refused). A
send with no intent at all, which a crashed or slow pre hook lets through
(spike P5, P6), is failed (unledgered_send, of: null). A hook is the floor of
the named route, not a boundary: exit 2 blocks in bypass mode, a crashed or
slow one lets the tool run.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from . import common, config, ledger
from .act import Act, Refused
from .sources import Sources

_ID_RE = re.compile(r'"(?:msg_?id|message_?id)"\s*:\s*"([^"]{1,80})"', re.IGNORECASE)
#: Inside the hook's 10 s: a ledger lock or a listing that takes longer fails
#: the gate closed here, rather than the harness killing the hook (which lets
#: the tool run, spike P6).
LOCK_WAIT_S = 3.0
LISTING_TIMEOUT_S = 5.0


def _matches(records: List[Dict[str, Any]], tick: int, to: str, text: str, open_only: bool) -> List[Dict[str, Any]]:
    shut = ledger.closing(records)
    return [r for r in records if r.get("kind") == "intent" and r.get("verb") == "mail" and r.get("tick") == tick
            and (r.get("target") or {}).get("name") == to and (r.get("target") or {}).get("text") == text
            and (not open_only or r.get("id") not in shut)]


def pre(sec: Dict[str, Any], src: Sources, hook: Dict[str, Any], tick: Optional[int], dry: bool,
        now: float) -> Tuple[int, str]:
    sd = config.state_dir(sec)
    records, corrupt = ledger.read(sd)
    ti = hook.get("tool_input") if isinstance(hook.get("tool_input"), dict) else {}
    to, text = ti.get("to"), ti.get("message")
    base = {"scope": sec["scope"], "tick": tick, "dry_run": dry, "by": "hook", "verb": "mail"}

    def refuse(check: str, it: Optional[Dict[str, Any]] = None) -> Tuple[int, str]:
        try:
            ledger.append(sd, dict(base, kind="failed", of=it["id"] if it else None,
                                   key=it["key"] if it else "to:%s" % common.safe_text(to, 80),
                                   reason="gate_refused", detail="send gate: %s" % check), wait=LOCK_WAIT_S)
        except (ledger.LedgerError, OSError) as exc:  # still refused: the record is what's lost
            check += " (and the refusal couldn't be recorded: %s)" % exc
        return 2, "fleet send gate refused this SendMessage: %s" % check

    if tick is None:
        return refuse("no tick (FLEET_TICK is not set)")
    if corrupt:  # a corrupt line can hide a prior mail or an outcome (§5.7)
        return refuse("the ledger has %d corrupt line(s)" % corrupt)
    if not isinstance(to, str) or not isinstance(text, str):
        return refuse("no matching intent (the call has no to or message)")
    found = _matches(records, tick, to, text, open_only=True)
    if not found:
        return refuse("no matching intent: no unclosed mail intent from tick %d to %s with this exact text (run "
                      "fleet act mail, then send its to and message unchanged, with no [ref])"
                      % (tick, common.safe_text(to, 60)))
    it = found[-1]
    t = it["target"]
    act = Act(sec, src, tick, dry, now)
    if it["key"] not in {v["key"] for v in act.ours().values()}:
        return refuse("the recipient is no longer a fleet spawn in the ledger or an adopted session", it)
    prior = ledger.mail_recent(records, t.get("recipient") or t["session_id"], now, sec["mail_interval_h"], dry,
                               exclude=it["id"])
    if prior:
        return refuse("a second mail to this recipient within %d h (intent %s)" % (sec["mail_interval_h"],
                                                                                    prior["id"]), it)
    try:
        rows = act.listing(LISTING_TIMEOUT_S)
    except Refused as exc:
        return refuse(exc.detail, it)
    live = [r for r in rows if r["pid"] is not None and r["name"] == to]
    if len(live) != 1 or live[0]["session_id"] != t["session_id"]:
        return refuse("the name no longer maps to one live session (%d live row(s) carry it%s)" % (
            len(live), "" if not live or live[0]["session_id"] == t["session_id"] else ", not session %s"
            % t["session_id"][:8]), it)
    if dry:
        try:
            ledger.append(sd, dict(base, kind="done", of=it["id"], key=it["key"], result={"would": True}),
                          wait=LOCK_WAIT_S)
        except (ledger.LedgerError, OSError) as exc:
            return 2, "dry run: not sent (DRY_RUN=1); closing intent %s failed: %s" % (it["id"], exc)
        return 2, ("dry run: not sent (DRY_RUN=1). The send gate passed every check and closed intent %s as would."
                   % it["id"])
    return 0, ""


def post(sec: Dict[str, Any], hook: Dict[str, Any], tick: Optional[int], dry: bool) -> Optional[Dict[str, Any]]:
    sd = config.state_dir(sec)
    records, _ = ledger.read(sd)
    ti = hook.get("tool_input") if isinstance(hook.get("tool_input"), dict) else {}
    to, text = ti.get("to"), ti.get("message")
    base = {"scope": sec["scope"], "tick": tick, "dry_run": dry, "by": "hook", "verb": "mail"}
    if not isinstance(to, str) or not isinstance(text, str):
        return None
    found = _matches(records, tick, to, text, open_only=True) if tick is not None else []
    if not found:
        if tick is not None and _matches(records, tick, to, text, open_only=False):
            return None  # closed already (the pre hook's dry close, or a refusal)
        return ledger.append(sd, dict(base, kind="failed", of=None, key="to:%s" % common.safe_text(to, 80),
                                      reason="unledgered_send",
                                      detail="a SendMessage to %s with no mail intent behind it"
                                      % common.safe_text(to, 60)))
    it = found[-1]
    resp = hook.get("tool_response", hook.get("error"))
    blob = resp if isinstance(resp, str) else json.dumps(resp, default=str)
    failed = hook.get("hook_event_name") == "PostToolUseFailure" or (
        isinstance(resp, dict) and bool(resp.get("is_error") or resp.get("error") or resp.get("success") is False))
    if failed:
        return ledger.append(sd, dict(base, kind="failed", of=it["id"], key=it["key"], reason="harness_refused",
                                      detail=common.safe_text(blob, 200)))
    m = _ID_RE.search(blob or "")
    return ledger.append(sd, dict(base, kind="done", of=it["id"], key=it["key"],
                                  result={"msg_id": m.group(1) if m else None}))
