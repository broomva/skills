#!/usr/bin/env python3
"""agentic-vps lockout-safety staging checker.

The single hardest-won lesson from the srv1692698 session: you can lock yourself
(and the agent) out of a box by closing public SSH before the VPN path is proven.
This encodes the safe ordering as a PURE function over a planned step sequence,
so a plan that would cause lockout fails deterministically — before it runs.

Recognized step kinds (order-significant):
  snapshot                  - take a provider snapshot / rollback point
  vpn_up                    - bring up the mesh VPN (tailscale up / wg)
  vpn_ssh_verified          - confirmed ssh over the VPN IP in a fresh session
  allow_vpn_ssh             - firewall: allow SSH over the VPN interface
  close_public_ssh          - firewall/UFW: remove public :22 (UFW + edge)
  oob_console_confirmed     - out-of-band console (Browser Terminal) confirmed

A step kind may appear with extra free-text after a colon (ignored).
"""
from __future__ import annotations
import argparse

KINDS = {
    "snapshot", "vpn_up", "vpn_ssh_verified", "allow_vpn_ssh",
    "close_public_ssh", "oob_console_confirmed",
}

# Each rule: (description, predicate(steps, index_of) -> ok)
# index_of(kind) returns the first index of that kind, or None.
RULES = [
    ("snapshot must precede closing public SSH",
     lambda idx: idx("close_public_ssh") is None or (
         idx("snapshot") is not None and idx("snapshot") < idx("close_public_ssh"))),
    ("VPN must be up before closing public SSH",
     lambda idx: idx("close_public_ssh") is None or (
         idx("vpn_up") is not None and idx("vpn_up") < idx("close_public_ssh"))),
    ("VPN SSH must be VERIFIED before closing public SSH",
     lambda idx: idx("close_public_ssh") is None or (
         idx("vpn_ssh_verified") is not None and idx("vpn_ssh_verified") < idx("close_public_ssh"))),
    ("must allow VPN SSH path before closing public SSH",
     lambda idx: idx("close_public_ssh") is None or (
         idx("allow_vpn_ssh") is not None and idx("allow_vpn_ssh") < idx("close_public_ssh"))),
    ("out-of-band console must be confirmed before closing public SSH",
     lambda idx: idx("close_public_ssh") is None or (
         idx("oob_console_confirmed") is not None and idx("oob_console_confirmed") < idx("close_public_ssh"))),
    ("VPN must be verified AFTER it is brought up (not assumed)",
     lambda idx: idx("vpn_ssh_verified") is None or idx("vpn_up") is None or (
         idx("vpn_up") < idx("vpn_ssh_verified"))),
]


def normalize(steps: list[str]) -> list[str]:
    """Strip free-text after ':' and whitespace; keep only the kind token."""
    return [s.split(":", 1)[0].strip() for s in steps]


def check_sequence(steps: list[str]) -> dict:
    """Pure: validate a planned step sequence against the lockout-safety rules.

    Returns {"ok": bool, "violations": [desc...], "unknown_steps": [...]}.
    """
    kinds = normalize(steps)
    unknown = [k for k in kinds if k and k not in KINDS]

    def index_of(kind: str):
        return kinds.index(kind) if kind in kinds else None

    violations = [desc for desc, pred in RULES if not pred(index_of)]
    return {"ok": len(violations) == 0 and not unknown,
            "violations": violations, "unknown_steps": unknown}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check a provisioning plan for lockout safety")
    ap.add_argument("steps", nargs="*", help="ordered step kinds (see module docstring)")
    ap.add_argument("--plan-file", help="newline-separated steps file")
    args = ap.parse_args(argv)

    steps = list(args.steps)
    if args.plan_file:
        with open(args.plan_file) as fh:
            steps += [ln.strip() for ln in fh if ln.strip()]
    if not steps:
        ap.error("provide steps or --plan-file")

    res = check_sequence(steps)
    if res["unknown_steps"]:
        print("UNKNOWN steps:", ", ".join(res["unknown_steps"]))
    for v in res["violations"]:
        print("[VIOLATION]", v)
    print("\nLOCKOUT-SAFE:", "YES" if res["ok"] else "NO")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
