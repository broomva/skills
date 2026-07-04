#!/usr/bin/env python3
"""eve-forge validate gate — parse `eve info --json` and assert readiness.

HARDENED against REAL eve v0.19.0 output (dogfood BRO-1685):
  - eve prints a banner ("☰eve  v0.19.0") to stdout BEFORE the JSON → parse from
    the first `{` (`parse_info`), don't `json.loads` the raw stream.
  - real `diagnostics` is a DICT `{"errors":N,"warnings":N}` (not a list); readiness
    is `"status":"ready"` (string), not a boolean `ready`/`compile`. Tolerate all.
Asserts: 0 diagnostic errors, every expected tool registered, status ready.
Usage:  npx eve info --json | validate.py --expect-tools fill_document,send_document
Exit 0 = ready; 2 = not ready (iterate).
"""
import argparse
import json
import sys


def parse_info(raw):
    """Extract the JSON object from `eve info --json` stdout (skips the banner)."""
    i = raw.find("{")
    if i < 0:
        raise ValueError("no JSON object found in eve info output")
    return json.loads(raw[i:])


def _falsy(v):
    if isinstance(v, str):
        return v.strip().lower() in ("false", "0", "no", "")
    return not v


def assess_info(info, expect_tools=None):
    """(ok, reason) from a parsed `eve info --json` object (real eve schema)."""
    reasons = []
    # diagnostics: real eve = {"errors":N,"warnings":N}; tolerate a list; `errors` alias
    diags = info.get("diagnostics")
    err_count = 0
    if isinstance(diags, dict):
        err_count = diags.get("errors", 0) or 0
    elif isinstance(diags, list):
        err_count = len(diags)
    if isinstance(info.get("errors"), list):
        err_count += len(info["errors"])
    if err_count:
        reasons.append("%d diagnostic error(s)" % err_count)
    # tools (list of strings, or list of {name})
    tools = info.get("tools") or []
    tool_names = set(t if isinstance(t, str) else t.get("name") for t in tools)
    if expect_tools:
        missing = [t for t in expect_tools if t not in tool_names]
        if missing:
            reasons.append("missing tool(s): %s" % missing)
    # readiness: real eve = "status":"ready"; tolerate boolean ready/compile
    status = info.get("status")
    if status is not None and str(status).strip().lower() != "ready":
        reasons.append("status=%r (not ready)" % status)
    for key in ("ready", "compile"):
        if key in info and _falsy(info[key]):
            reasons.append("not compile-ready (%s falsy)" % key)
    if reasons:
        return False, "; ".join(reasons)
    return True, "ready: tools=%s" % ",".join(sorted(n for n in tool_names if n))


def main(argv=None):
    ap = argparse.ArgumentParser(description="eve-forge validate gate")
    ap.add_argument("--file", help="eve info output (default: stdin)")
    ap.add_argument("--expect-tools", default="")
    a = ap.parse_args(argv)
    raw = open(a.file).read() if a.file else sys.stdin.read()
    info = parse_info(raw)
    expect = [t.strip() for t in a.expect_tools.split(",") if t.strip()]
    ok, reason = assess_info(info, expect)
    print(("PASS " if ok else "FAIL ") + reason)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
