#!/usr/bin/env python3
"""eve-forge pipeline runner + Node-24 preflight.

Sequences the deterministic gates around the latent (agent-authored) stages.
Subcommands:
  preflight             check Node >= 24 (the `npx eve init` trap)
  gate <agent_dir>      run deploy-safety (+ validate if --info given); prod by default
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deploy_safety  # noqa: E402
import validate  # noqa: E402


def node_major():
    try:
        out = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip()
        return int(out.lstrip("v").split(".")[0])
    except Exception:
        return None


def cmd_preflight(_a):
    maj = node_major()
    if maj is None:
        print("FAIL preflight: node not found (eve needs Node >= 24)")
        return 2
    if maj < 24:
        print("FAIL preflight: node v%d < 24 — `npx eve init` will hard-fail; run `nvm use 24`" % maj)
        return 2
    print("PASS preflight: node v%d >= 24" % maj)
    return 0


def cmd_gate(a):
    ok, rows = deploy_safety.scan_dir(a.agent_dir, a.env)
    for ch, row_ok, reason in rows:
        print("[deploy-safety %s] %s: %s" % ("PASS" if row_ok else "FAIL", ch, reason))
    rc = 0 if ok else 2
    if a.info:
        expect = [t.strip() for t in a.expect_tools.split(",") if t.strip()]
        info_ok, reason = validate.assess_info(json.load(open(a.info)), expect)
        print("[validate %s] %s" % ("PASS" if info_ok else "FAIL", reason))
        if not info_ok:
            rc = 2
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(description="eve-forge runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")
    g = sub.add_parser("gate")
    g.add_argument("agent_dir")
    g.add_argument("--env", default="prod", choices=["prod", "dev"])
    g.add_argument("--info")
    g.add_argument("--expect-tools", default="")
    a = ap.parse_args(argv)
    return {"preflight": cmd_preflight, "gate": cmd_gate}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
