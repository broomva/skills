"""Read Antigravity ACP quotas without writing its native credential file.

Contract follows Google's T3 Antigravity client (antigravityUsageLimits.ts). Google documents
refreshing access tokens at https://developers.google.com/identity/protocols/oauth2/native-app#offline ; this is not Codex's rotating-refresh-token protocol. Unexpected refresh-token rotation
fails closed and leaves a durable, credential-free marker to prevent spending that grant again.
The native ACP process remains the writer of profile/antigravity-acp/acp_token.json.
"""
import hashlib
import json
import math
import os
import platform
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINTS = ("https://daily-cloudcode-pa.googleapis.com", "https://cloudcode-pa.googleapis.com")
MAX_RESPONSE = 2 * 1024 * 1024
TIMEOUT = 6


class ProbeError(Exception):
    """Only fixed, credential-free reason codes cross the probe boundary."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(url, *, form=None, body=None, access_token=None):
    headers = {"Accept": "application/json"}
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if access_token:
        headers["Authorization"] = "Bearer " + access_token
        architecture = {"x86_64": "x64", "aarch64": "arm64"}.get(platform.machine(), platform.machine())
        headers["User-Agent"] = (
            "antigravity/hub/1.0.0 (aidev_client; os_type=%s; arch=%s; cl=963137146)"
            % (sys.platform, architecture)
        )
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        # A redirect must never forward OAuth tokens to a different origin.
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=TIMEOUT) as response:
            if not 200 <= response.status < 300:
                raise ProbeError("http_unavailable")
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise ProbeError("invalid_response")
            result = json.loads(raw, parse_constant=lambda value: None)
            if not isinstance(result, dict):
                raise ProbeError("invalid_response")
            return result
    except urllib.error.HTTPError as exc:
        # Do not read/log the response body, URL, request or exception text.
        raise ProbeError({401: "auth_unavailable", 403: "forbidden", 429: "throttled"}.get(
            exc.code, "redirect_refused" if 300 <= exc.code < 400 else "http_unavailable")) from None
    except (OSError, ValueError, TypeError):
        raise ProbeError("transport_unavailable") from None


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _text(value):
    return re.sub(r"[\x00-\x1f\x7f]", "", value).strip()[:160] if isinstance(value, str) else ""


def _reset(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError):
        return None


def _window(identifier, label, family, quota, window=None):
    fraction = quota.get("remainingFraction")
    disabled = quota.get("disabled", False)
    usable = (_number(fraction) and 0 <= fraction <= 1 and "remainingAmount" not in quota
              and disabled is False)
    result = {"id": identifier, "label": label, "family": family,
              "kind": "weekly" if window == "weekly" else "session" if window == "5h" else "other",
              "usedPercent": (1 - fraction) * 100 if usable else None,
              "disabled": disabled is not False}
    if window:
        result["window"] = window
    if window in ("weekly", "5h"):
        result["windowDurationMins"] = 10080 if window == "weekly" else 300
    reset = _reset(quota.get("resetTime"))
    if reset:
        result["resetsAt"] = reset
    return result


def merge_windows(*collections):
    """Keep the most-used reading; conflicting/unknown observations cannot invent headroom."""
    result = {}
    for collection in collections:
        for window in collection:
            key = window["id"]
            previous = result.get(key)
            if previous is None:
                result[key] = dict(window)
                continue
            conflict = (previous.get("family") != window.get("family")
                        or previous.get("window") != window.get("window"))
            if (conflict or previous.get("usedPercent") is None or window.get("usedPercent") is None
                    or previous.get("disabled") or window.get("disabled")):
                result[key] = dict(previous, usedPercent=None,
                                   disabled=bool(previous.get("disabled") or window.get("disabled")))
            elif window["usedPercent"] > previous["usedPercent"]:
                result[key] = dict(window)
            # If endpoints disagree on the reset, choose the later valid timestamp.
            resets = [w["resetsAt"] for w in (previous, window) if w.get("resetsAt")]
            if resets:
                result[key]["resetsAt"] = max(resets, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))
    return list(result.values())


def parse_summary(data):
    if not isinstance(data, dict):
        return []
    groups = data.get("groups")
    if not isinstance(groups, list) or not any(isinstance(g, dict) and isinstance(g.get("buckets"), list)
                                             and g["buckets"] for g in groups):
        groups = [{"buckets": data.get("buckets", [])}]
    windows = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("buckets"), list):
            continue
        for bucket in group["buckets"]:
            if not isinstance(bucket, dict) or not _text(bucket.get("bucketId")):
                continue
            identifier = _text(bucket["bucketId"])
            family = "gemini" if identifier.startswith("gemini-") else "third_party" if identifier.startswith("3p-") else None
            label = _text(group.get("displayName")) or _text(bucket.get("displayName")) or identifier
            windows.append(_window(identifier, label, family, bucket, _text(bucket.get("window")) or None))
    return merge_windows(windows)


def parse_models(data):
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, dict):
        return []
    windows = []
    for model_id, model in models.items():
        if not isinstance(model, dict):
            continue
        provider = model.get("modelProvider")
        family = ("gemini" if model_id.startswith("gemini-") or provider == "MODEL_PROVIDER_GOOGLE" else
                  "claude" if model_id.startswith("claude-") or provider == "MODEL_PROVIDER_ANTHROPIC" else
                  "gpt" if model_id.startswith("gpt-") or provider == "MODEL_PROVIDER_OPENAI" else None)
        if family is None:
            continue
        for field, suffix in (("quotaInfo", "quota"), ("weeklyQuotaInfo", "weekly")):
            quota = model.get(field)
            if isinstance(quota, dict):
                windows.append(_window(family + "-" + suffix, family.title(), family, quota,
                                       "weekly" if suffix == "weekly" else None))
    return merge_windows(windows)


def _redact(value, secrets):
    if isinstance(value, str):
        for secret in secrets:
            if isinstance(secret, str) and len(secret) >= 4:
                value = value.replace(secret, "[redacted]")
        return value
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: _redact(item, secrets) for key, item in value.items()}
    return value


def probe(profile, expected_email):
    """Return sanitized email/status/windows/numbersAt. No native credential writes or redirects.

    status='ok' means at least one usable window; callers must still require the requested family
    and every applicable window to have a numeric usedPercent. Unknown telemetry never means zero.
    numbersAt is epoch seconds only when usable measurements exist. No access token is persisted.
    """
    email = expected_email.strip().lower()
    result = {"email": email, "status": "unavailable", "windows": [], "numbersAt": None}
    secrets = []
    try:
        if not email or "@" not in email:
            raise ProbeError("invalid_expected_identity")
        token_path = Path(profile) / "antigravity-acp" / "acp_token.json"
        if token_path.stat().st_size > MAX_RESPONSE:
            raise ProbeError("invalid_credentials")
        token = json.loads(token_path.read_text())
        if not isinstance(token, dict) or not all(isinstance(token.get(k), str) and token[k]
                                                for k in ("client_id", "client_secret", "refresh_token")):
            raise ProbeError("invalid_credentials")
        secrets.extend(token[k] for k in ("client_secret", "refresh_token"))
        fingerprint = hashlib.sha256((token["client_id"] + "\0" + token["refresh_token"]).encode()).hexdigest()
        marker_dir = Path.home() / ".cache" / "broomva-provider-antigravity"
        marker_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker = marker_dir / (fingerprint + ".rotation-unsupported")
        if marker.exists():
            raise ProbeError("auth_rotation_unsupported")
        refreshed = _request("https://oauth2.googleapis.com/token", form={
            "client_id": token["client_id"], "client_secret": token["client_secret"],
            "refresh_token": token["refresh_token"], "grant_type": "refresh_token"})
        returned_refresh = refreshed.get("refresh_token")
        if returned_refresh is not None and returned_refresh != token["refresh_token"]:
            # The marker carries no grant. A new native login changes the fingerprint and clears it.
            try:
                fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, "w") as out:
                    out.write("auth_rotation_unsupported\n")
                    out.flush()
                    os.fsync(out.fileno())
                folder_fd = os.open(marker_dir, os.O_RDONLY)
                try:
                    os.fsync(folder_fd)
                finally:
                    os.close(folder_fd)
            raise ProbeError("auth_rotation_unsupported")
        access = refreshed.get("access_token")
        if not isinstance(access, str) or not access or not _number(refreshed.get("expires_in")) or refreshed["expires_in"] <= 0:
            raise ProbeError("invalid_token_response")
        secrets.append(access)
        identity = _request("https://www.googleapis.com/oauth2/v2/userinfo", access_token=access)
        if not isinstance(identity.get("email"), str) or identity["email"].strip().lower() != email or identity.get("verified_email") is False:
            raise ProbeError("identity_mismatch")
        project = token.get("project_id")
        if project is not None and not isinstance(project, str):
            raise ProbeError("invalid_credentials")
        body = {"project": project} if project else {}
        windows = []
        for operation, parser in (("retrieveUserQuotaSummary", parse_summary), ("fetchAvailableModels", parse_models)):
            readings = []
            for endpoint in ENDPOINTS:
                try:
                    readings.append(parser(_request(endpoint + "/v1internal:" + operation,
                                                    body=body, access_token=access)))
                except ProbeError:
                    readings.append([])
            windows = merge_windows(windows, *readings)
            if any(w["usedPercent"] is not None for w in windows):
                break
        result["windows"] = windows
        if any(w["usedPercent"] is not None for w in windows):
            result.update(status="ok", numbersAt=time.time())
        else:
            result["reason"] = "quota_unavailable"
    except ProbeError as exc:
        result["reason"] = str(exc)
    except (OSError, ValueError, TypeError, KeyError):
        result["reason"] = "profile_unavailable"
    return _redact(result, secrets)
