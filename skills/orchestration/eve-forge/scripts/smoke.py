#!/usr/bin/env python3
"""eve-forge smoke gate — assert a deployed agent's output vs ground truth.

Evidence-gated acceptance: given the filled-document text and a ground-truth
spec (required substrings + forbidden placeholders), assert every required value
appears and no forbidden/unfilled marker remains.
Hardened (P20): `required` terms match on WORD BOUNDARIES so "Bella" is not
satisfied by "Isabella" nor "one week" by "phone weekly". `forbidden` markers
(placeholders like <UNFILLED>) still match as substrings.
Usage:  smoke.py --output filled.txt --truth truth.json
  truth.json: {"required": ["Bella","Meloxicam","one week"], "forbidden": ["<UNFILLED>"]}
Exit 0 = pass; 2 = fail.
"""
import argparse
import json
import re
import sys


def _strip_html_comments(text):
    """Remove <!-- ... --> so an echoed template/house-style comment can't false-match
    a required OR forbidden term (BRO-1685: the agent echoed the template comment,
    which contains 'bloodwork', into the deliverable)."""
    return re.sub(r"<!--.*?-->", " ", text, flags=re.S)


def _present(term, out):
    return re.search(r"\b" + re.escape(term.lower()) + r"\b", out) is not None


def assess_output(output, truth):
    """(ok, coverage_ratio, reason). HTML comments stripped first (v1.0.2). `forbidden`
    encodes case-scoped negative constraints (e.g. no 'bloodwork' for a non-senior patient)."""
    out = _strip_html_comments(output or "").lower()
    reasons = []
    required = truth.get("required", [])
    missing = [r for r in required if not _present(r, out)]
    if missing:
        reasons.append("missing required: %s" % missing)
    forbidden = truth.get("forbidden", [])
    present = [f for f in forbidden if f.lower() in out]
    if present:
        reasons.append("forbidden present (unfilled/placeholder): %s" % present)
    covered = len(required) - len(missing)
    ratio = covered / len(required) if required else 1.0
    if reasons:
        return False, ratio, "; ".join(reasons)
    return True, ratio, "smoke PASS: %d/%d required fields, no forbidden" % (covered, len(required))


def main(argv=None):
    ap = argparse.ArgumentParser(description="eve-forge smoke gate")
    ap.add_argument("--output", required=True)
    ap.add_argument("--truth", required=True)
    a = ap.parse_args(argv)
    output = open(a.output).read()
    truth = json.load(open(a.truth))
    ok, ratio, reason = assess_output(output, truth)
    print(("PASS " if ok else "FAIL ") + reason + " (coverage=%d%%)" % round(ratio * 100))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
