#!/usr/bin/env python3
"""eve-forge deploy-safety gate — the incident-derived, fail-closed machine-check.

A benchmark run (BRO-1677) shipped a public, auth:none(), gateway-billed eve
endpoint. This gate makes that structurally impossible: it FAILS any production
deploy whose channel auth is not locked. Wire it as a PreToolUse hook before
`vercel deploy`.

Hardened (P20 round 1) against fail-OPEN inputs:
  - comments + string literals are stripped before matching (no decoy configs);
  - a hard deny scans the whole (stripped) source for any unsafe authenticator
    call `none(` / `placeholderAuth(` — regardless of array nesting/position;
  - ALL `auth:[...]` arrays are extracted with balanced-bracket matching
    (nested option arrays like `jwt({audience:["a"]})` no longer truncate);
  - a real authenticator is required via DENY-LIST (any call not unsafe/dev-only),
    so custom authenticators (clerkAuth/auth0/session/...) are accepted.

Rule (prod): no unsafe authenticator anywhere; at least one real (non dev-only)
authenticator in an `auth:` array. Unparseable / variable-defined / missing auth
-> FAIL CLOSED. `localDev()` is dev-only. `--env dev` is ungated.

Usage:
  deploy_safety.py <agent_dir> [--env prod|dev]
  echo "<channel src>" | deploy_safety.py --stdin
Exit 0 = safe to deploy; 2 = unsafe (blocked).
"""
import argparse
import glob
import os
import re
import sys

UNSAFE = {"none", "placeholderAuth"}
DEV_ONLY = {"localDev"}
CHANNEL_GLOBS = ("*.ts", "*.tsx", "*.mts", "*.cts", "*.js", "*.jsx", "*.mjs")


def strip_comments_strings(src):
    """Remove /* */, // comments and '/"/` string literals so decoys can't match."""
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"//[^\n]*", " ", src)
    src = re.sub(r"'(?:\\.|[^'\\])*'", "''", src)
    src = re.sub(r'"(?:\\.|[^"\\])*"', '""', src)
    src = re.sub(r"`(?:\\.|[^`\\])*`", "``", src)
    return src


def _balanced_end(src, lb):
    """Index just past the ']' matching the '[' at src[lb], or None."""
    depth = 0
    for i in range(lb, len(src)):
        if src[i] == "[":
            depth += 1
        elif src[i] == "]":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def auth_arrays(src):
    """Inner text of every balanced `auth: [...]` array (comments/strings pre-stripped)."""
    out = []
    for m in re.finditer(r"auth\s*:\s*\[", src):
        lb = src.index("[", m.start())
        end = _balanced_end(src, lb)
        out.append(src[lb + 1:] if end is None else src[lb + 1:end - 1])
    return out


def _calls(text):
    return re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", text)


def assess_auth(src, env="prod"):
    """(ok, reason) verdict for a single channel source string."""
    if env == "dev":
        return True, "dev env: auth not gated in dev"
    clean = strip_comments_strings(src)
    # belt: hard-deny any unsafe authenticator call anywhere in the stripped source
    for u in UNSAFE:
        if re.search(r"\b" + re.escape(u) + r"\s*\(", clean):
            return False, "prod blocked: unsafe authenticator %s() present" % u
    arrays = auth_arrays(clean)
    if not arrays:
        return False, "no explicit `auth:` array found in channel (fail-closed)"
    real = set()
    for arr in arrays:
        for name in _calls(arr):
            if name not in UNSAFE and name not in DEV_ONLY:
                real.add(name)
    if not real:
        return False, ("prod blocked: no verifiable real authenticator "
                       "(only dev-only, or variable-defined auth — inline a recognized authenticator)")
    return True, "prod-safe: real authenticator(s) %s present, no unsafe auth" % sorted(real)


def scan_dir(agent_dir, env="prod"):
    """(all_ok, [(path, ok, reason)]) over every channel file (all JS/TS extensions)."""
    files = []
    for g in CHANNEL_GLOBS:
        files += glob.glob(os.path.join(agent_dir, "**", "channels", g), recursive=True)
        files += glob.glob(os.path.join(agent_dir, "channels", g))
    files = sorted(set(files))
    if not files:
        return False, [("<none>", False, "no channel files under channels/ (fail-closed)")]
    rows = []
    all_ok = True
    for ch in files:
        with open(ch) as f:
            ok, reason = assess_auth(f.read(), env)
        rows.append((ch, ok, reason))
        all_ok = all_ok and ok
    return all_ok, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="eve-forge deploy-safety gate")
    ap.add_argument("agent_dir", nargs="?")
    ap.add_argument("--env", default="prod", choices=["prod", "dev"])
    ap.add_argument("--stdin", action="store_true")
    a = ap.parse_args(argv)
    if a.stdin:
        ok, reason = assess_auth(sys.stdin.read(), a.env)
        print(("PASS " if ok else "FAIL ") + reason)
        return 0 if ok else 2
    if not a.agent_dir:
        ap.error("agent_dir or --stdin required")
    ok, rows = scan_dir(a.agent_dir, a.env)
    for ch, row_ok, reason in rows:
        print("[%s] %s: %s" % ("PASS" if row_ok else "FAIL", ch, reason))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
