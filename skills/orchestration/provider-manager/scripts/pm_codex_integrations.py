"""Prepare supported launcher configuration without editing live application state."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path

import pm_codex_homes
import pm_store


def executable(value):
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise pm_store.StoreError("Launcher must be an absolute executable file")
    return str(path)


def t3_requests(binary):
    """One immutable instance per generation; never update the built-in codex instance."""
    binary = executable(binary)
    requests = []
    for email, account in sorted(pm_codex_homes.registry()["accounts"].items()):
        home = Path(account["home"])
        if not home.is_absolute() or not home.is_dir():
            raise pm_store.StoreError("Codex account home is unavailable: %s" % email)
        generation = hashlib.sha256(str(home).encode()).hexdigest()[:24]
        requests.append({
            "method": "server.updateSettings",
            "payload": {
                "patch": {},
                "providerInstanceMutation": {
                    "operation": "create",
                    "instanceId": "codex-pm-" + generation,
                    "instance": {
                        "driver": "codex", "displayName": "Codex " + email,
                        "config": {"setupMode": "existing", "binaryPath": binary, "homePath": str(home),
                                   "shadowHomePath": ""},
                    },
                },
            },
        })
    return requests


def paseo_config(config, launcher):
    """Return a candidate document; the operator applies it and runs paseo daemon reload."""
    launcher = executable(launcher)
    if not isinstance(config, dict):
        raise pm_store.StoreError("Paseo config must be an object")
    candidate = copy.deepcopy(config)
    node = candidate
    for key in ("agents", "providers", "codex"):
        node = node.setdefault(key, {})
        if not isinstance(node, dict):
            raise pm_store.StoreError("Paseo agents.providers.codex must contain objects")
    # A replacement command can carry required options. Never silently discard it.
    previous = node.get("command")
    if previous is not None and previous != [launcher]:
        raise pm_store.StoreError("Paseo Codex already has a custom command; reconcile it explicitly")
    if node.get("extends") not in (None, "codex"):
        raise pm_store.StoreError("Paseo codex entry extends a different provider")
    env = node.get("env", {})
    if not isinstance(env, dict):
        raise pm_store.StoreError("Paseo Codex env must be an object")
    if env.get("CODEX_HOME"):
        raise pm_store.StoreError("Paseo Codex has an explicit CODEX_HOME; reconcile it explicitly")
    node["command"] = [launcher]
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="application", required=True)
    t3 = sub.add_parser("t3", help="Emit native settings RPC requests; submit through T3's settings client")
    t3.add_argument("--binary", required=True, help="Absolute real Codex binary, not the selection wrapper")
    paseo = sub.add_parser("paseo", help="Emit a candidate config; never modifies the input file")
    paseo.add_argument("--config", required=True)
    paseo.add_argument("--launcher", required=True)
    args = parser.parse_args()
    try:
        result = (t3_requests(args.binary) if args.application == "t3" else
                  paseo_config(json.loads(Path(args.config).read_text()), args.launcher))
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, TypeError, pm_store.StoreError) as exc:
        parser.exit(1, "codex integration: %s\n" % exc)


if __name__ == "__main__":
    main()
