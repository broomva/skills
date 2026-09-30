"""The fleet config: ~/.config/ctx/fleet.json, one section per scope (spec §5.7).

JSON because fleet_reconcile.py runs under `python3 -I` with no YAML parser.
The owner edits it. An unknown key, a scope missing from the core's
scopes.yaml, a wrong type or a parse error fails `config-check`, and the tick
does not fire. `config-get` prints one value; tick.sh reads any error as off
(dispatch_enabled) and dry (dry_run).

Keys marked "phase 1" below are this build's additions, pending the spec
(broomva/workspace#842 fixes the rest).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ctx

from . import common

DEFAULT_PATH = "~/.config/ctx/fleet.json"

#: key -> (type check, default). A default of None means "absent is fine".
SCOPE_KEYS: Dict[str, Tuple[str, Any]] = {
    "dispatch_enabled": ("int01", 0),         # the kill switch: the tick fires only on exactly 1
    "dry_run": ("int01", 1),                  # live only on exactly 0
    "mode": ("mode", "report"),               # report: observe, classify and ask; every other verb refuses
    "tracker": ("dict", None),
    "state_dir": ("str", None),               # default ~/.local/state/fleet-reconcile/<scope>
    "paseo_project": ("str_or_null", None),   # reported against the scope rule, never used to decide
    "caps": ("caps", None),
    "mail_interval_h": ("int", 6),
    "paseo_tools": ("paseo_tools", None),
    "driver": ("dict", None),
    "adopted": ("adopted", []),
    # phase 1
    "listing_cap": ("int", 200),              # a session listing this long may be truncated: fail closed
    "pr_list_cap": ("int", 200),              # the same for `gh pr list` per repo
    "gh_token_file": ("str_or_null", None),   # tick.sh exports it as GH_TOKEN when present
    "actions_app_id": ("int", 15368),         # the app a required check must be pinned to (GitHub Actions)
    "launchd_prefix": ("str_or_null", None),  # scheduled-work inventory: which LaunchAgents to list
    "launchd_logs": ("str_map", None),        # label -> the log that shows a real run, when stdout doesn't
    "bookkeeping_run_log": ("str_or_null", None),
    "dream_run_log": ("str_or_null", None),
    "ask_renotify_h": ("int", 6),
    "tick_timeout_min": ("int", 15),
}
CAP_KEYS = ("fleet_sessions", "active_sessions", "active_window_min", "research_spawns_per_day")
CAP_DEFAULTS = {"fleet_sessions": 8, "active_sessions": 12, "active_window_min": 30, "research_spawns_per_day": 4}


class ConfigError(ValueError):
    pass


def path() -> Path:
    raw = os.environ.get("FLEET_CONFIG")
    return Path(raw) if raw else common.expand(DEFAULT_PATH)


def _check(kind: str, key: str, v: Any) -> None:
    ok = {
        "int01": lambda: type(v) is int and v in (0, 1),
        "int": lambda: type(v) is int and v >= 0,
        "str": lambda: isinstance(v, str) and bool(v),
        "str_or_null": lambda: v is None or isinstance(v, str),
        "mode": lambda: v in ("report", "act"),
        "dict": lambda: isinstance(v, dict),
        "str_map": lambda: v is None or (isinstance(v, dict) and all(
            isinstance(k, str) and isinstance(x, str) for k, x in v.items())),
        "caps": lambda: isinstance(v, dict) and not (set(v) - set(CAP_KEYS))
        and all(type(x) is int and x >= 0 for x in v.values()),
        "paseo_tools": lambda: isinstance(v, dict) and not (set(v) - {"paseo_version", "read", "write"})
        and all(isinstance(v.get(k, []), list) and all(isinstance(t, str) for t in v.get(k, []))
                for k in ("read", "write")),
        "adopted": lambda: isinstance(v, list) and all(
            isinstance(e, dict) and isinstance(e.get("session_id"), str) and ctx.SESSION_ID_RE.match(e["session_id"])
            and not (set(e) - {"session_id", "adopted", "note"}) for e in v),
    }[kind]()
    if not ok:
        raise ConfigError("%s: bad value for %s (%s)" % (key, key, kind))


def load(check_scopes: bool = True) -> Dict[str, Any]:
    """The whole config, validated. Raises ConfigError."""
    p = path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError("%s: missing" % p)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise ConfigError("%s: %s" % (p, exc))
    if not isinstance(raw, dict) or raw.get("v") != 1 or not isinstance(raw.get("scopes"), dict):
        raise ConfigError("%s: want {\"v\": 1, \"scopes\": {...}}" % p)
    unknown = set(raw) - {"v", "scopes"}
    if unknown:
        raise ConfigError("%s: unknown top-level key(s) %s" % (p, ", ".join(sorted(unknown))))
    known_scopes = None
    if check_scopes:
        try:
            known_scopes = {s for s in ctx.load_scopes().by_repo.values() if s}
        except ctx.ConfigError as exc:
            raise ConfigError("scopes.yaml: %s" % exc)
    for sid, sec in raw["scopes"].items():
        if not isinstance(sec, dict):
            raise ConfigError("scope %s: not an object" % sid)
        if not ctx.SCOPE_ID_RE.match(sid):
            raise ConfigError("scope %s: invalid id" % sid)
        if known_scopes is not None and sid not in known_scopes:
            raise ConfigError("scope %s: not in scopes.yaml" % sid)
        bad = set(sec) - set(SCOPE_KEYS)
        if bad:
            raise ConfigError("scope %s: unknown key(s) %s" % (sid, ", ".join(sorted(bad))))
        for key, value in sec.items():
            _check(SCOPE_KEYS[key][0], "%s.%s" % (sid, key), value)
    return raw


def scope(sid: str, check_scopes: bool = True) -> Dict[str, Any]:
    """One scope's section with defaults filled in. Raises ConfigError."""
    raw = load(check_scopes)
    if sid not in raw["scopes"]:
        raise ConfigError("scope %s: not in %s" % (sid, path()))
    sec = dict(raw["scopes"][sid])
    for key, (_, default) in SCOPE_KEYS.items():
        sec.setdefault(key, default)
    sec["caps"] = dict(CAP_DEFAULTS, **(sec.get("caps") or {}))
    sec["state_dir"] = str(common.expand(sec.get("state_dir") or "~/.local/state/fleet-reconcile/%s" % sid))
    if sec.get("gh_token_file"):
        sec["gh_token_file"] = str(common.expand(sec["gh_token_file"]))
    sec["scope"] = sid
    return sec


def state_dir(sec: Dict[str, Any]) -> Path:
    return Path(sec["state_dir"])


def adopted_ids(sec: Dict[str, Any]) -> List[str]:
    return [e["session_id"] for e in sec.get("adopted") or []]


def get(sid: str, key: str) -> Optional[str]:
    """What `fleet config-get` prints: a scalar as text, anything else as JSON."""
    sec = scope(sid)
    if key not in sec:
        raise ConfigError("unknown key %s" % key)
    v = sec[key]
    if v is None:
        return ""
    return str(v) if isinstance(v, (str, int)) and not isinstance(v, bool) else json.dumps(v, sort_keys=True)
