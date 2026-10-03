"""Stub Anthropic auth/usage/profile/messages endpoints with a JSON-file state.

The token endpoint rotates refresh tokens the way the real one does: a refresh consumes the token it
was sent and mints a new pair, and a consumed refresh token answers 400 invalid_grant. That rotation
is what turns a stale credential copy into a dead one, so every kill path depends on it.

State lives in a file (FAKE_ANTHROPIC_STATE) so the test process, provider-manager subprocesses, the
fake `claude` and the Claude Code simulator all see one server.
"""

import fcntl
import json
import os
import secrets
import time
from contextlib import contextmanager


def _path():
    p = os.environ.get("FAKE_ANTHROPIC_STATE")
    if not p:
        raise RuntimeError("FAKE_ANTHROPIC_STATE is unset (test guard)")
    return p


@contextmanager
def state():
    path = _path()
    with open(path + ".lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                data = {}
            for k in ("accounts", "access", "refresh"):
                data.setdefault(k, {})
            data.setdefault("calls", [])
            yield data
            tmp = path + ".tmp.%d" % os.getpid()
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, path)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def now_ms():
    return int(time.time() * 1000)


def _record(data, kind, email, status):
    data["calls"].append({"kind": kind, "email": email, "status": status, "ts": time.time(), "pid": os.getpid()})
    data["calls"] = data["calls"][-5000:]


def add_account(email, account_uuid, org_uuid, five_hour=10.0, seven_day=20.0):
    with state() as d:
        d["accounts"][email] = {
            "account_uuid": account_uuid,
            "org_uuid": org_uuid,
            "five_hour": five_hour,
            "seven_day": seven_day,
            "usage_mode": "ok",
            "exhausted": False,
            "locked_reason": None,
            # a fixed time 3 h ahead, as the real endpoint reports for one window; a test that wants a
            # new window sets a new value
            "five_hour_resets_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3 * 3600)),
        }


def set_account(email, **kw):
    with state() as d:
        d["accounts"][email].update(kw)


def mint(email, at_ttl_s=3600.0):
    """Mint a fresh valid pair for email; returns a claudeAiOauth dict."""
    with state() as d:
        return _mint(d, email, at_ttl_s)


def _mint(d, email, at_ttl_s=3600.0):
    at = "at-" + email.split("@")[0] + "-" + secrets.token_hex(6)
    rt = "rt-" + email.split("@")[0] + "-" + secrets.token_hex(6)
    exp = now_ms() + int(at_ttl_s * 1000)
    d["access"][at] = {"email": email, "expires_at_ms": exp}
    d["refresh"][rt] = {"email": email, "state": "valid"}
    return {
        "accessToken": at,
        "refreshToken": rt,
        "expiresAt": exp,
        "scopes": ["user:inference", "user:profile", "user:sessions:claude_code"],
        "subscriptionType": "max",
    }


def consume(rt):
    with state() as d:
        if rt in d["refresh"]:
            d["refresh"][rt]["state"] = "consumed"


def expire_access(at):
    with state() as d:
        if at in d["access"]:
            d["access"][at]["expires_at_ms"] = now_ms() - 1000


def refresh_state(rt):
    with state() as d:
        r = d["refresh"].get(rt)
        return r["state"] if r else None


def email_for_access(at):
    with state() as d:
        a = d["access"].get(at)
        return a["email"] if a else None


def token_refresh(rt, at_ttl_s=3600.0):
    with state() as d:
        r = d["refresh"].get(rt)
        if not r or r["state"] != "valid":
            _record(d, "refresh", r["email"] if r else None, 400)
            return 400, {"error": "invalid_grant", "error_description": "Refresh token not found or invalid"}
        r["state"] = "consumed"
        fresh = _mint(d, r["email"], at_ttl_s)
        acct = d["accounts"][r["email"]]
        _record(d, "refresh", r["email"], 200)
        return 200, {
            "access_token": fresh["accessToken"],
            "refresh_token": fresh["refreshToken"],
            "expires_in": int(at_ttl_s),
            "scope": " ".join(fresh["scopes"]),
            "token_type": "Bearer",
            "account": {"uuid": acct["account_uuid"], "email_address": r["email"]},
            "organization": {"uuid": acct["org_uuid"]},
        }


def _bearer_account(d, at):
    a = d["access"].get(at or "")
    if not a or a["expires_at_ms"] <= now_ms():
        return None
    return a["email"]


def usage(at):
    with state() as d:
        email = _bearer_account(d, at)
        if not email:
            _record(d, "usage", None, 401)
            return 401, {"error": {"type": "authentication_error", "message": "OAuth token has expired"}}
        acct = d["accounts"][email]
        if acct["usage_mode"] == "429":
            _record(d, "usage", email, 429)
            return 429, {"error": {"type": "rate_limit_error", "message": "Too many requests"}}
        if acct["usage_mode"] == "500":
            _record(d, "usage", email, 500)
            return 500, {"error": {"type": "api_error", "message": "Internal server error"}}
        _record(d, "usage", email, 200)
        body = {
            "five_hour": {"utilization": acct["five_hour"], "resets_at": acct["five_hour_resets_at"]},
            "seven_day": {"utilization": acct["seven_day"], "resets_at": "2099-01-08T00:00:00Z"},
        }
        if acct.get("locked_reason"):
            body["five_hour"]["locked_reason"] = acct["locked_reason"]
        return 200, body


def profile(at):
    with state() as d:
        email = _bearer_account(d, at)
        if not email:
            _record(d, "profile", None, 401)
            return 401, {"error": {"type": "authentication_error"}}
        acct = d["accounts"][email]
        _record(d, "profile", email, 200)
        return 200, {
            "account": {"uuid": acct["account_uuid"], "email": email, "display_name": email.split("@")[0]},
            "organization": {"uuid": acct["org_uuid"], "organization_type": "claude_max"},
        }


def messages(at, kind="messages"):
    with state() as d:
        email = _bearer_account(d, at)
        if not email:
            _record(d, kind, None, 401)
            return 401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
        if d["accounts"][email]["exhausted"]:
            _record(d, kind, email, 429)
            return 429, {"type": "error", "error": {"type": "rate_limit_error", "message": "You've hit your limit"}}
        _record(d, kind, email, 200)
        return 200, {"type": "message", "content": [{"type": "text", "text": "OK"}], "served_by": email}


def calls(kind=None):
    with state() as d:
        return [c for c in d["calls"] if kind is None or c["kind"] == kind]
