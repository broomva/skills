#!/usr/bin/env python3
"""
provider_manager_hook.py — Claude Code Autonomous Balancing & Rate-Limit Hook

Wired to Claude Code hooks (SessionStart, PostToolUse, UserPromptSubmit) to:
1. Proactively balance accounts before sessions start or when usage exceeds thresholds.
2. Intercept rate-limit failures in tool executions and immediately failover/rotate
   to standby accounts without interrupting the agent workflow.

Design principles:
- SILENT BY DEFAULT: Emits output only when an action occurs or when reporting status at SessionStart.
- FAST & NON-BLOCKING: Relies on cached usage data (<60s TTL); bounded 3s timeouts.
- ALWAYS EXIT 0: Never crashes or blocks Claude Code execution turns.
"""

import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import provider_manager as pm

RATE_LIMIT_PATTERNS = [
    r"rate_limit_error",
    r"rate limit (?:exceeded|reached)",
    r"you have reached your (?:current )?usage limit",
    r"hit a rate limit",
    r"status(?: code)?:?\s*429",
    r"http (?:status )?429",
    r"too many requests",
    r"billing limit",
    r"quota exceeded",
    r"credit balance is too low",
]

RATE_LIMIT_RE = re.compile("|".join(RATE_LIMIT_PATTERNS), re.IGNORECASE)


def handle_session_start(payload: dict) -> None:
    """Run proactive balancing and display multi-account status banner."""
    try:
        # Run balancing with default 85% threshold
        balance_res = pm.balance_accounts(threshold=85.0, dry_run=False)
        action = balance_res.get("action")
        if action == "switched":
            sys.stderr.write(
                f"[provider-manager] Proactively rotated active account to {balance_res.get('toAccount')} "
                f"(previous account {balance_res.get('fromAccount')} was at {balance_res.get('activeUtilization')}% utilization).\n"
            )
            return

        # Single line glanceable status (to stderr so it does not pollute prompt prefix context)
        accounts = pm.fetch_all_usage()
        active = next((a for a in accounts if a.get("isActive")), None)
        standbys = [a for a in accounts if not a.get("isActive")]
        if active:
            active_fh = f"{active.get('fiveHourUtil')}%" if active.get('fiveHourUtil') is not None else "?"
            active_sd = f"{active.get('sevenDayUtil')}%" if active.get('sevenDayUtil') is not None else "?"
            standby_parts = []
            for s in standbys:
                s_fh = f"{s.get('fiveHourUtil')}%" if s.get('fiveHourUtil') is not None else "?"
                s_sd = f"{s.get('sevenDayUtil')}%" if s.get('sevenDayUtil') is not None else "?"
                standby_parts.append(f"{s.get('email')} ({s_fh} 5h, {s_sd} 7d)")
            standby_str = f" | Standby: {', '.join(standby_parts)}" if standby_parts else ""
            sys.stderr.write(f"[provider-manager] Active: {active.get('email')} ({active_fh} 5h, {active_sd} 7d){standby_str}\n")
    except Exception:
        pass


def handle_post_tool_use(payload: dict) -> None:
    """Detect rate limits in tool execution output or errors, and trigger auto-rotation."""
    try:
        text_to_check = []
        for k in ("error", "tool_output", "stderr", "output", "result"):
            v = payload.get(k)
            if isinstance(v, str):
                text_to_check.append(v)
            elif isinstance(v, dict):
                text_to_check.append(json.dumps(v))

        combined = " ".join(text_to_check)
        if combined and RATE_LIMIT_RE.search(combined):
            rotate_res = pm.rotate_account(reason="tool_rate_limit", dry_run=False)
            if rotate_res.get("success"):
                sys.stderr.write(
                    f"\n[provider-manager] Rate limit detected in tool execution! "
                    f"Automatically failed over active account: {rotate_res.get('rotatedFrom')} -> {rotate_res.get('rotatedTo')}.\n"
                )
    except Exception:
        pass


def handle_prompt_submit(payload: dict) -> None:
    """Before prompt executes, check if active account is near exhaustion (>=90%)."""
    try:
        balance_res = pm.balance_accounts(threshold=90.0, dry_run=False)
        if balance_res.get("action") == "switched":
            sys.stderr.write(
                f"[provider-manager] Active account reached {balance_res.get('activeUtilization')}% utilization. "
                f"Proactively rotated to {balance_res.get('toAccount')} before executing prompt.\n"
            )
    except Exception:
        pass


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else "session-start"
    payload = {}
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw.strip():
                payload = json.loads(raw)
    except Exception:
        payload = {}

    if event in ("session-start", "SessionStart"):
        handle_session_start(payload)
    elif event in ("post-tool-use", "PostToolUse", "PostToolUseFailure"):
        handle_post_tool_use(payload)
    elif event in ("prompt-submit", "UserPromptSubmit"):
        handle_prompt_submit(payload)


if __name__ == "__main__":
    main()
