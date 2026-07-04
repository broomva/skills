#!/usr/bin/env python3
"""eve-forge validate gate — parse `eve info --json` and assert readiness.

Asserts: 0 diagnostics (or `errors`), every expected tool registered, compile-ready.
Hardened (P20): treats falsy/stringy readiness ("false", 0) as not-ready, and
accepts `errors` as an alias for `diagnostics` (schema drift no longer fails-open).
Usage:  npx eve info --json | validate.py --expect-tools fill_document,send_document
Exit 0 = ready; 2 = not ready (iterate).
"""
import argparse
import json
import sys


def _falsy(v):
    if isinstance(v, str):
        return v.strip().lower() in ("false", "0", "no", "")
    return not v


def assess_info(info, expect_tools=None):
    """(ok, reason) from a parsed `eve info --json` object."""
    reasons = []
    diags = info.get("diagnostics") or info.get("errors") or []
    if diags:
        reasons.append("%d diagnostic(s): %s" % (len(diags), diags[:3]))
    tools = info.get("tools") or []
    tool_names = set()
    for t in tools:
        tool_names.add(t if isinstance(t, str) else t.get("name"))
    if expect_tools:
        missing = [t for t in expect_tools if t not in tool_names]
        if missing:
            reasons.append("missing tool(s): %s" % missing)
    for key in ("ready", "compile"):
        if key in info and _falsy(info[key]):
            reasons.append("not compile-ready (%s falsy)" % key)
    if reasons:
        return False, "; ".join(reasons)
    return True, "ready: tools=%s" % ",".join(sorted(n for n in tool_names if n))


def main(argv=None):
    ap = argparse.ArgumentParser(description="eve-forge validate gate")
    ap.add_argument("--file", help="eve info json (default: stdin)")
    ap.add_argument("--expect-tools", default="")
    a = ap.parse_args(argv)
    raw = open(a.file).read() if a.file else sys.stdin.read()
    info = json.loads(raw)
    expect = [t.strip() for t in a.expect_tools.split(",") if t.strip()]
    ok, reason = assess_info(info, expect)
    print(("PASS " if ok else "FAIL ") + reason)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
