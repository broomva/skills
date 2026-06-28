#!/usr/bin/env python3
"""agentic-vps verification gate.

Evaluates whether a provisioned box meets the *capability-preserving* security
invariants (the box IS the sandbox: contained, not leashed).

The evaluation is a PURE function — `evaluate(facts)` — so it is unit-tested
without any host I/O. The CLI wrapper collects `facts` over SSH and feeds them in.

Gate semantics:
  required gates  -> any FAIL => overall FAIL (exit 1)
  recommended     -> FAIL => WARN only (does not fail the gate unless --strict)
"""
from __future__ import annotations
import argparse
import json
import subprocess

# (key, required?, human description, predicate over facts)
GATES = [
    ("agent_nonroot", True, "agent runs as a non-root user (uid != 0)",
     lambda f: isinstance(f.get("agent_uid"), int) and f["agent_uid"] != 0),
    ("agent_has_sudo", False, "agent has passwordless sudo (capability preserved)",
     lambda f: bool(f.get("agent_passwordless_sudo"))),
    ("resource_caps", True, "user-slice resource caps set (host-survival)",
     lambda f: bool(f.get("slice_memory_max")) and bool(f.get("slice_tasks_max"))),
    ("tailscale_up", True, "Tailscale is up (VPN reachability path)",
     lambda f: bool(f.get("tailscale_ip"))),
    ("public_ssh_closed", True, "public :22 is NOT reachable (perimeter closed)",
     lambda f: f.get("public_ssh_open") is False),
    ("no_secrets_in_env", True, "no long-lived broad secret in agent env/.bashrc",
     lambda f: f.get("secrets_in_env") == []),
    ("snapshot_exists", False, "a recovery snapshot exists (reversibility)",
     lambda f: bool(f.get("snapshot_exists"))),
    ("claude_config", False, "Claude Code settings present (bypassPermissions)",
     lambda f: f.get("claude_default_mode") == "bypassPermissions"),
]

# secret env var names that must never be present in the agent's environment/shell init
SECRET_ENV_NAMES = ("ANTHROPIC_API_KEY", "GITHUB_TOKEN", "GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "OPENAI_API_KEY")

# Definitive "port is CLOSED/unreachable" stderr signals (OS-portable: macOS + Linux phrasings).
# Anything NOT matching these is treated as OPEN — a security gate must fail CLOSED, so
# unknown/ambiguous probe results count as "open" (i.e. the perimeter gate fails safe).
SSH_CLOSED_SIGNALS = (
    "Operation timed out",        # macOS: filtered/dropped
    "Connection timed out",       # Linux: filtered/dropped
    "timed out",                  # banner/connect timeout variants
    "Connection refused",         # host up, port closed
    "No route to host",
    "Network is unreachable",
    "Could not resolve hostname",
)


def classify_public_ssh(returncode: int, stderr: str) -> bool:
    """Pure: True if public SSH appears OPEN/reachable, False only if DEFINITELY closed.

    Fail-safe for a security gate: rc==0 (connected + ran) is open; any definitive
    closed/unreachable signal is closed; EVERYTHING ELSE (auth reached, host-key
    changed, connection closed by remote, kex error, too many auth failures,
    unknown) is treated as OPEN so the `public_ssh_closed` gate cannot pass a box
    that is actually reachable.
    """
    if returncode == 0:
        return True
    if any(sig in stderr for sig in SSH_CLOSED_SIGNALS):
        return False
    return True  # reachable-but-not-authed, or unknown -> assume OPEN (fail closed)


def evaluate(facts: dict) -> dict:
    """Pure evaluation of the capability-preserving invariants.

    Returns {"gates": [{key, required, ok, desc}], "ok": bool, "failed_required": [...]}.
    """
    results = []
    failed_required = []
    for key, required, desc, pred in GATES:
        try:
            ok = bool(pred(facts))
        except Exception:
            ok = False
        results.append({"key": key, "required": required, "ok": ok, "desc": desc})
        if required and not ok:
            failed_required.append(key)
    return {"gates": results, "ok": len(failed_required) == 0, "failed_required": failed_required}


def find_secrets_in_env(env_dump: str) -> list[str]:
    """Pure: given a newline dump of env + shell-init contents, return offending secret names."""
    found = []
    for name in SECRET_ENV_NAMES:
        for line in env_dump.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # match `NAME=...` or `export NAME=...`
            if stripped.startswith(f"{name}=") or stripped.startswith(f"export {name}="):
                found.append(name)
                break
    return found


# ---------------------------------------------------------------------------
# I/O wrapper (not unit-tested; thin shell around the pure core)
# ---------------------------------------------------------------------------
def _ssh(host: str, cmd: str, timeout: int = 20) -> str:
    out = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={timeout}", host, cmd],
        capture_output=True, text=True, timeout=timeout + 10,
    )
    return out.stdout.strip()


def collect_facts(host: str, public_ip: str | None) -> dict:
    facts: dict = {}
    uid = _ssh(host, "id -u")
    facts["agent_uid"] = int(uid) if uid.isdigit() else None
    facts["agent_passwordless_sudo"] = _ssh(host, "sudo -n true 2>/dev/null && echo yes") == "yes"
    auid = _ssh(host, "id -u")
    facts["slice_memory_max"] = _ssh(host, f"systemctl show user-{auid}.slice -p MemoryMax --value 2>/dev/null")
    facts["slice_tasks_max"] = _ssh(host, f"systemctl show user-{auid}.slice -p TasksMax --value 2>/dev/null")
    facts["tailscale_ip"] = _ssh(host, "tailscale ip -4 2>/dev/null | head -1")
    # capture the LOGIN-shell env (where exported secrets actually live) + all shell-init files
    env_dump = _ssh(host, "bash -lc env 2>/dev/null; cat ~/.bashrc ~/.bash_profile ~/.profile ~/.zshrc 2>/dev/null")
    facts["secrets_in_env"] = find_secrets_in_env(env_dump)
    facts["claude_default_mode"] = _ssh(
        host, "python3 -c \"import json;print(json.load(open(__import__('os').path.expanduser('~/.claude/settings.json'))).get('permissions',{}).get('defaultMode',''))\" 2>/dev/null")
    # public :22 reachability — probed from THIS machine against the public IP.
    # Uses the fail-closed classifier: only a definitive closed/unreachable signal
    # counts as closed; anything else (incl. host-key-changed, kex error, auth
    # reached) is treated as OPEN so the perimeter gate cannot pass an exposed box.
    if public_ip:
        probe = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
             "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
             f"agent@{public_ip}", "true"],
            capture_output=True, text=True,
        )
        facts["public_ssh_open"] = classify_public_ssh(probe.returncode, probe.stderr)
    else:
        facts["public_ssh_open"] = None
    return facts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verify agentic-vps capability-preserving invariants")
    ap.add_argument("--host", help="ssh target over the tailnet, e.g. agent@100.x.y.z")
    ap.add_argument("--public-ip", help="public IP to probe for closed :22")
    ap.add_argument("--facts-json", help="evaluate a facts JSON file instead of SSH (testing/offline)")
    ap.add_argument("--strict", action="store_true", help="treat recommended gate failures as failures")
    args = ap.parse_args(argv)

    if args.facts_json:
        with open(args.facts_json) as fh:
            facts = json.load(fh)
    elif args.host:
        facts = collect_facts(args.host, args.public_ip)
    else:
        ap.error("one of --host or --facts-json is required")

    res = evaluate(facts)
    for g in res["gates"]:
        mark = "PASS" if g["ok"] else ("FAIL" if g["required"] else "WARN")
        tag = "" if g["required"] else " (recommended)"
        print(f"[{mark}] {g['key']}{tag} — {g['desc']}")
    ok = res["ok"] and (not args.strict or all(g["ok"] for g in res["gates"]))
    print("\nOVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
