"""The driver profile (spec §5.5, §5.7): the settings file a driver runs under.

A 0600 file, `claude --bg --settings <file>`. Its shape is probe 6's
(2.1.280), the one the spec measured: crossSessionInbound accept; the sandbox
on with no unsandboxed escape and a strict domain allowlist; denyRead on
Paseo's directory; permission denies for reading it and for editing
~/.claude/** and any .claude/settings*.json (not .claude/**, since a driver's
own worktree sits under .claude/worktrees/). Drivers run in bypassPermissions
(--dangerously-skip-permissions in the argv), the mode in which probe 2's deny
rules held.

No token. Owner decision 2026-10-01: the fleet uses the owner's gh login, and
spec §5.2's non-admin fleet credential is waived. A driver reads that login
inside the sandbox with `gh auth token` (no network), git pushes through the
configured gh credential helper, and pull-request calls go to the REST API
with curl: gh's own network calls fail TLS inside the sandbox (OSStatus
-26276), and taking gh out of it needs allowUnsandboxedCommands, the escape
this profile refuses. Measured 2026-10-01 (credential drill, profile D).
Open residual (BRO-2755, measured 2026-10-02): with the keychain readable, a
driver can read ANY login-keychain item via /usr/bin/security without a prompt,
not only gh's (securityd is reachable from inside the sandbox; the file-based
denyRead does not reach it). The keychain can't be partially denied — a file
deny is whole-keychain and would break gh's own read — so the exposure is a W1
decision for the owner (accept arm D, or arm A's env token + keychain-file deny,
which a file deny does reach). What a driver does not need, this profile now
denies: the credential files below. W5's full per-spawn pattern inventory
(incl. **/.env*) is F1 follow-up.

It changes what a driver reaches by default and is not a boundary (§5.1). The
file stays at its path until the driver's worktree goes: a resume reads the
saved options, the settings path among them (§5.3).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

#: Credential stores a GitHub-PR driver's gh route and build never need to read,
#: measured present and driver-readable on 2026-10-01/02 (BRO-2755). Denied at
#: the sandbox (Bash) and the Read tool. The login keychain is NOT here (the gh
#: route needs it, and a file deny is whole-keychain: a W1 decision), and
#: ~/.config/gh and git config stay readable (the gh route needs them). Package
#: registries/toolchain caches (~/.npmrc, ~/.cargo/credentials.toml) are left
#: readable: a scope's build may need them (DRIVER_DEFAULTS).
CRED_DENY_READ = ["~/.aws", "~/.ssh", "~/.config/gcloud", "~/.kube", "~/.config/op",
                  "~/.gnupg", "~/.netrc", "~/.docker/config.json"]

DENY_READ = ["~/.paseo"] + CRED_DENY_READ
DENY = (["Read(~/.paseo/**)", "Edit(~/.claude/**)", "Edit(**/.claude/settings*.json)"]
        + ["Read(%s)" % p for p in CRED_DENY_READ] + ["Read(%s/**)" % p for p in CRED_DENY_READ])


def driver_profile(sec: Dict[str, Any], key: str) -> Dict[str, Any]:
    drv = sec["driver"]
    fs: Dict[str, Any] = {"denyRead": list(DENY_READ)}
    if drv["allow_write"]:
        fs["allowWrite"] = list(drv["allow_write"])
    return {
        "crossSessionInbound": "accept",
        "sandbox": {"enabled": True, "allowUnsandboxedCommands": False,
                    "network": {"strictAllowlist": True, "allowedDomains": list(drv["allowed_domains"])},
                    "filesystem": fs},
        "permissions": {"deny": list(DENY)},
    }


def driver_argv(sec: Dict[str, Any], key: str, profile_path: Path, brief: str) -> List[str]:
    """§5.3's spawn: claude --bg -w <key> --name <key> --strict-mcp-config
    --dangerously-skip-permissions --settings <profile file> "<brief>" (the
    flags probe 6 ran with), plus --model when the scope's driver names one."""
    argv = ["claude", "--bg", "-w", key, "--name", key, "--strict-mcp-config", "--dangerously-skip-permissions",
            "--settings", str(profile_path)]
    if sec["driver"].get("model"):
        argv += ["--model", sec["driver"]["model"]]
    return argv + [brief]


def path_for(state_dir: Path, key: str) -> Path:
    return Path(state_dir) / "profiles" / ("%s.json" % key)


def write(path: Path, profile: Dict[str, Any]) -> Path:
    """Write the profile 0600 (created so; never world- or group-readable on
    the way), fsynced. It holds no secret since 0.4.0; 0600 stays, since
    nothing else needs to read it."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, (json.dumps(profile, indent=1, sort_keys=True) + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))
    return path
