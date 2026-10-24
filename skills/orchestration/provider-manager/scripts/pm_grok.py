"""Read-only Grok usage telemetry (BRO-3466). One xAI account: no balancing, switching or login.

Source, found empirically in grok 1.0.70 (its billing pane and paywall check): with the grok.com
OIDC access token the CLI keeps in ~/.grok/auth.json,
  GET https://cli-chat-proxy.grok.com/v1/billing?format=credits  -> the plan's usage window
      (currentPeriod type/start/end, creditUsagePercent, per-product usagePercent)
  GET https://cli-chat-proxy.grok.com/v1/user?include=subscription -> email, subscriptionTier
The grok CLI stays the only reader of the refresh token and the only writer of auth.json: an expired
access token is reported, never refreshed here (any grok run refreshes it). Numbers come only from
those responses; anything unreadable is `telemetry unavailable: <reason>`, never a zero.
"""
import http.client
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://cli-chat-proxy.grok.com/v1"
CLIENT_VERSION = "1.0.70"
MAX_RESPONSE = 1024 * 1024
TIMEOUT = 8
CACHE_SECONDS = 60
PERIODS = {"USAGE_PERIOD_TYPE_WEEKLY": "weekly", "USAGE_PERIOD_TYPE_DAILY": "daily",
           "USAGE_PERIOD_TYPE_MONTHLY": "monthly"}


class ProbeError(Exception):
    """Only fixed, credential-free reason codes cross the probe boundary."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _paths():
    home = Path.home()
    return home / ".grok" / "auth.json", home / ".cache" / "broomva-provider-grok" / "usage.json"


def _request(path, token):
    request = urllib.request.Request(BASE + path, headers={
        "Accept": "application/json", "Authorization": "Bearer " + token,
        "x-grok-client-version": CLIENT_VERSION, "x-grok-client-mode": "headless"})
    try:
        # A redirect must never forward the bearer token to another origin.
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=TIMEOUT) as response:
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise ProbeError("invalid_response")
            result = json.loads(raw, parse_constant=lambda value: None)
            if not isinstance(result, dict):
                raise ProbeError("invalid_response")
            return result
    except urllib.error.HTTPError as exc:
        # Do not read/log the response body, URL, request or exception text.
        raise ProbeError({401: "auth_rejected", 403: "auth_rejected", 429: "endpoint_throttled"}.get(
            exc.code, "redirect_refused" if 300 <= exc.code < 400 else "http_%d" % exc.code)) from None
    except (OSError, ValueError, TypeError, RecursionError, http.client.HTTPException):
        raise ProbeError("transport_unavailable") from None


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _text(value):
    return re.sub(r"[\x00-\x1f\x7f]", "", value).strip()[:120] if isinstance(value, str) else ""


def _instant(value):
    if not isinstance(value, str):
        return None
    # Python 3.9's fromisoformat takes only 3- or 6-digit fractions: normalise to 6.
    value = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], value.replace("Z", "+00:00"), count=1)
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, OverflowError):
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _iso(moment):
    return moment.isoformat().replace("+00:00", "Z") if moment else None


def _percent(value):
    return float(value) if _number(value) and 0 <= value <= 1000 else None


def parse_credits(data):
    """The plan window from /billing?format=credits; None when it is not the measured shape."""
    config = data.get("config") if isinstance(data, dict) else None
    if not isinstance(config, dict):
        return None
    period = config.get("currentPeriod") if isinstance(config.get("currentPeriod"), dict) else {}
    used = _percent(config.get("creditUsagePercent"))
    if used is None:
        return None
    start = _instant(period.get("start") or config.get("billingPeriodStart"))
    end = _instant(period.get("end") or config.get("billingPeriodEnd"))
    kind = PERIODS.get(period.get("type"), "other") if isinstance(period.get("type"), str) else "other"
    window = {"id": kind, "kind": kind, "usedPercent": used, "startsAt": _iso(start), "resetsAt": _iso(end)}
    if start and end and end > start:
        window["windowDurationMins"] = int((end - start).total_seconds() // 60)
    products = []
    items = config.get("productUsage")
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and _text(item.get("product")) and _percent(item.get("usagePercent")) is not None:
            products.append({"product": _text(item["product"]), "usedPercent": _percent(item["usagePercent"])})
    if products:
        window["products"] = products
    return window


def _read_auth(auth_path):
    """(email, token, expiresAt) from the grok CLI's auth.json. Never writes it."""
    try:
        if auth_path.stat().st_size > MAX_RESPONSE:
            raise ProbeError("auth_unreadable")
        data = json.loads(auth_path.read_text())
    except FileNotFoundError:
        raise ProbeError("not_logged_in") from None
    except (OSError, ValueError):
        raise ProbeError("auth_unreadable") from None
    entries = [v for k, v in data.items() if isinstance(v, dict) and k.startswith("https://auth.x.ai")] \
        if isinstance(data, dict) else []
    if len(entries) != 1:
        raise ProbeError("not_logged_in" if not entries else "multiple_logins")
    entry = entries[0]
    token, email = entry.get("key"), _text(entry.get("email")).lower()
    if not isinstance(token, str) or not token or "@" not in email:
        raise ProbeError("not_logged_in")
    return email, token, _instant(entry.get("expires_at"))


def _load_cache(cache_path):
    """The last good reading, or None unless every window still carries a measured percent."""
    try:
        cached = json.loads(cache_path.read_text())
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(cached, dict) or not _number(cached.get("numbersAt")) or not isinstance(cached.get("email"), str):
        return None
    windows = cached.get("windows")
    if not isinstance(windows, list) or not windows or not all(
            isinstance(w, dict) and _percent(w.get("usedPercent")) is not None for w in windows):
        return None
    return cached


def _save_cache(cache_path, result):
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = cache_path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as out:
            out.write(json.dumps(result))
        os.replace(tmp, cache_path)
    except OSError:
        pass  # a cache that cannot be written only costs a re-read


def _status(windows, blocked):
    spent = [w["usedPercent"] for w in windows] + [p["usedPercent"] for w in windows for p in w.get("products", [])]
    if blocked or any(used >= 100 for used in spent):
        return "LIMITED"
    return "OK"


def probe(now=None):
    """One sanitized account dict. status: OK, LIMITED, NEEDS_LOGIN or UNAVAILABLE."""
    now = time.time() if now is None else now
    auth_path, _ = _paths()
    result = {"provider": "grok", "email": None, "tier": None, "isActive": True, "status": "UNAVAILABLE",
              "telemetry": "unavailable", "windows": [], "numbersAt": None,
              "source": BASE + "/billing?format=credits"}
    token = None
    try:
        email, token, expires = _read_auth(auth_path)
        result["email"] = email
        if expires is None:
            raise ProbeError("token_expiry_unreadable")
        if expires.timestamp() <= now:
            raise ProbeError("access_token_expired")
        user = _request("/user?include=subscription", token)
        if _text(user.get("email")).lower() != email:
            raise ProbeError("identity_mismatch")
        result["tier"] = _text(user.get("subscriptionTier")) or None
        blocked = bool(user.get("userBlockedReason")) or bool(user.get("teamBlockedReasons"))
        window = parse_credits(_request("/billing?format=credits", token))
        if window is None:
            raise ProbeError("usage_not_reported")
        result.update(windows=[window], telemetry="ok", numbersAt=now, status=_status([window], blocked))
        if blocked:
            result["reason"] = "account_blocked"
    except ProbeError as exc:
        reason = str(exc)
        result["reason"] = reason
        if reason in ("not_logged_in", "auth_rejected"):
            result["status"] = "NEEDS_LOGIN"
    except (TypeError, ValueError, KeyError, AttributeError, RecursionError):
        # A response this parser does not understand is unavailable, never a crash of `--provider all`.
        result.update(windows=[], telemetry="unavailable", numbersAt=None, status="UNAVAILABLE",
                      reason="invalid_response")
    if token and token in json.dumps(result):  # defence in depth: no field may carry the bearer token
        result = {"provider": "grok", "email": None, "tier": None, "isActive": True, "status": "UNAVAILABLE",
                  "telemetry": "unavailable", "windows": [], "numbersAt": None, "reason": "credential_in_result"}
    return result


def usage(force=False, now=None):
    """[account] with the plan window. Cached CACHE_SECONDS; a failed read keeps the last good
    numbers only as `lastKnown`, labelled with their age, never as current telemetry."""
    now = time.time() if now is None else now
    auth_path, cache_path = _paths()
    cached = _load_cache(cache_path)
    try:
        current = _read_auth(auth_path)[0]
    except ProbeError:
        current = None
    if cached and cached["email"] != current:
        cached = None  # another login's numbers are never this account's
    if cached and not force and 0 <= now - cached["numbersAt"] < CACHE_SECONDS:
        return [dict(cached, numbersAgeSeconds=int(now - cached["numbersAt"]))]
    result = probe(now)
    if result["telemetry"] == "ok":
        _save_cache(cache_path, result)
        result["numbersAgeSeconds"] = 0
    elif cached and cached["email"] == result.get("email"):
        result["lastKnown"] = {"windows": cached["windows"], "numbersAt": cached["numbersAt"],
                               "numbersAgeSeconds": max(0, int(now - cached["numbersAt"]))}
    return [result]


def accounts():
    """Identity only, from auth.json; no network."""
    auth_path, _ = _paths()
    try:
        email, _, expires = _read_auth(auth_path)
        return [{"provider": "grok", "email": email, "isActive": True,
                 "tokenExpiresAt": _iso(expires), "status": "LOGGED_IN"}]
    except ProbeError as exc:
        return [{"provider": "grok", "email": None, "isActive": True,
                 "status": "NEEDS_LOGIN" if str(exc) == "not_logged_in" else "UNAVAILABLE", "reason": str(exc)}]


HINTS = {"access_token_expired": "any grok run refreshes it, e.g. `~/.grok/bin/grok models`",
         "not_logged_in": "the owner signs in with `grok login`",
         "auth_rejected": "the owner signs in again with `grok login`"}


def format_rows(rows):
    lines = ["%-8s %-30s %-10s %-8s %-8s %-22s %s" % ("ACTIVE", "EMAIL", "TIER", "WINDOW", "USED", "RESETS (UTC)", "STATUS"),
             "-" * 110]
    for a in rows:
        status = a["status"]
        if a.get("telemetry") != "ok":
            status += " (telemetry unavailable: %s%s)" % (a.get("reason") or "unknown",
                                                           "; " + HINTS[a["reason"]] if a.get("reason") in HINTS else "")
        elif a.get("reason"):
            status += " (%s)" % a["reason"]
        elif a.get("numbersAgeSeconds"):
            status += " (numbers %ds old)" % a["numbersAgeSeconds"]
        windows = a.get("windows") or [{}]
        for w in windows:
            used = "%g%%" % w["usedPercent"] if w.get("usedPercent") is not None else "-"
            resets = (w.get("resetsAt") or "-").replace("T", " ")[:16]
            lines.append("%-8s %-30s %-10s %-8s %-8s %-22s %s" % (" * " if a.get("isActive") else "", a.get("email") or "-",
                                                                  a.get("tier") or "-", w.get("kind") or "-", used, resets, status))
        last = a.get("lastKnown")
        if last:
            for w in last.get("windows", []):
                lines.append("         last known %dm ago: %s %g%%, resets %s" % (
                    last["numbersAgeSeconds"] // 60, w.get("kind"), w.get("usedPercent"), w.get("resetsAt")))
    return "\n".join(lines)
