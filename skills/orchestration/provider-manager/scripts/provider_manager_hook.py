#!/usr/bin/env python3
"""
provider_manager_hook.py — Claude Code hook for provider-manager.

Every session on the machine runs this hook, so it decides nothing and switches nothing itself:

- session-start: one status line from the usage cache (stderr; no network), then a kick.
- prompt-submit: a kick.
- stop-failure:  the turn ended on an API error. Record the session for resume. On `rate_limit` or
                 `authentication_failed`, queue the report and kick at once (the evaluation probes
                 before acting: a limit must be confirmed, a dead grant proven dead by Claude Code).
- post-tool-use: nothing. Tool output is never a Claude rate limit (a GitHub API limit or a site's
                 429 used to rotate the machine's account).

A kick starts `provider_manager.py balance --auto` detached, at most once per evaluation interval.
That process takes the machine-wide balancer lock, so exactly one evaluation runs however many
sessions kick. Always exits 0, writes nothing to stdout, and returns in milliseconds.
"""

import json
import os
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import pm_state  # noqa: E402
import provider_manager as pm  # noqa: E402

KICK_MIN_GAP_SECONDS = 30.0
MAX_PAYLOAD_BYTES = 1_000_000


def kick(reason: str, signal: str = None, force: bool = False) -> None:
    now = time.time()
    if not force:
        cfg = pm.load_config()
        st = pm.load_state()
        if now - st.get("lastEvalAt", 0) < cfg["evalIntervalSeconds"] or now - st.get("lastKickAt", 0) < KICK_MIN_GAP_SECONDS:
            return
    pm.update_state(lambda s: s.__setitem__("lastKickAt", now))
    if os.environ.get("PROVIDER_MANAGER_INLINE") == "1":
        pm.run_auto(reason=reason, signal=signal)
        return
    argv = [sys.executable] + (["-I"] if sys.flags.isolated else []) + [
        str(SCRIPT_DIR / "provider_manager.py"), "balance", "--auto", "--reason", reason]
    if signal:
        argv += ["--signal", signal]
    pm_state.spawn_detached(argv)


def handle_session_start(payload: dict) -> None:
    try:
        cache = pm.read_usage_cache().get("accounts", {})
        orca = pm.get_orca_data().get("settings", {})
        active_id = orca.get("activeClaudeManagedAccountId")
        parts = []
        for acc in orca.get("claudeManagedAccounts", []):
            u = cache.get(acc.get("id")) or {}
            fh = (u.get("five_hour") or {}).get("utilization")
            sd = (u.get("seven_day") or {}).get("utilization")
            label = "%s (%s 5h, %s 7d%s)" % (acc.get("email"), "%s%%" % fh if fh is not None else "?",
                                            "%s%%" % sd if sd is not None else "?",
                                            "" if u.get("telemetry", "ok") == "ok" else ", " + u.get("telemetry"))
            parts.append(("Active: " if acc.get("id") == active_id else "Standby: ") + label)
        if parts:
            sys.stderr.write("[provider-manager] %s\n" % " | ".join(sorted(parts)))
    except Exception:  # noqa: BLE001 - a status line must never break a session
        pass
    kick("session-start")


def handle_prompt_submit(payload: dict) -> None:
    kick("prompt-submit")


def handle_post_tool_use(payload: dict) -> None:
    """Deliberately nothing: see the module docstring."""
    return None


def handle_stop_failure(payload: dict) -> None:
    error = payload.get("error") or "unknown"
    entry = pm_state.record_stalled(pm.STALLED_PATH, payload, dict(os.environ))
    pm.log_provider_event("session.stalled", {"error": error, "stalledSession": entry.get("sessionId"),
                                              "paseoAgentId": entry.get("paseoAgentId")})
    signal = {"rate_limit": "rate_limit", "authentication_failed": "auth_failed"}.get(error)
    if signal:
        now = time.time()

        def queue(s):
            s.setdefault("pendingSignals", []).append({"type": signal, "at": now, "sessionId": entry.get("sessionId")})
            s["pendingSignals"] = s["pendingSignals"][-20:]
        pm.update_state(queue)
        kick("stop-failure", signal=signal, force=True)


HANDLERS = {
    "session-start": handle_session_start, "SessionStart": handle_session_start,
    "prompt-submit": handle_prompt_submit, "UserPromptSubmit": handle_prompt_submit,
    "post-tool-use": handle_post_tool_use, "PostToolUse": handle_post_tool_use,
    "PostToolUseFailure": handle_post_tool_use,
    "stop-failure": handle_stop_failure, "StopFailure": handle_stop_failure,
}


def main() -> None:
    if os.environ.get("PROVIDER_MANAGER_PROBE"):
        return  # never act inside our own probe
    event = sys.argv[1] if len(sys.argv) > 1 else "session-start"
    handler = HANDLERS.get(event)
    if handler is None or handler is handle_post_tool_use:
        return
    payload = {}
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read(MAX_PAYLOAD_BYTES)
            if raw.strip():
                payload = json.loads(raw)
    except Exception:  # noqa: BLE001
        payload = {}
    try:
        handler(payload if isinstance(payload, dict) else {})
    except Exception:  # noqa: BLE001 - always exit 0
        pass


if __name__ == "__main__":
    main()
