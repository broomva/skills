#!/usr/bin/env python3
"""Mutation check for reel_loop's gates: delete each gate in a scratch copy and
require the test suite to fail.

A gate whose deletion leaves every test green is not tested, whatever the prose
says. Each mutation names the exact source text it replaces; if that text is no
longer in the script (a rename or refactor), this check FAILS instead of
silently skipping the mutation, so a renamed gate cannot retire its own check.

Run: python3 tests/mutation_check.py      (from skills/video/reel-loop)
Not collected by pytest (no test_ prefix): it runs pytest itself.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]

MUTATIONS = [
    ("approval sha binding",
     'elif approval["video_sha256"] != digest:', "elif False:"),
    ("approval required",
     "if not approval:\n        reasons.append(\"no approval", "if False:\n        reasons.append(\"no approval"),
    ("consent checked for a declared clone",
     'reasons += _consent_errors(card.get("voice_consent"), card_dir, now)', "pass"),
    ("consent file must exist",
     "elif not (card_dir / ref).is_file():", "elif False:"),
    ("consent date must parse",
     'if when is None:\n        errs.append("voice_consent.date must be an ISO date")',
     'if False:\n        errs.append("voice_consent.date must be an ISO date")'),
    ("declared synthetic forces disclosure",
     'is_ai = card.get("is_ai_generated") is True or any(synthetic.values())',
     'is_ai = card.get("is_ai_generated") is True'),
    ("explicit disclosure kept",
     'is_ai = card.get("is_ai_generated") is True or any(synthetic.values())',
     "is_ai = any(synthetic.values())"),
    ("malformed cards blocked",
     "def _type_errors(card) -> list[str]:", "def _type_errors(card) -> list[str]:\n    return []"),
    ("publish sends the gated bytes, not the file as it is now",
     'str(len(data))}, body=data)', 'str(len(data))}, body=video.read_bytes())'),
    ("blocked card makes no API call",
     "    if container is None:\n        return None, reasons, notes\n\n    bearer = {",
     "    bearer = {"),
    ("empty video blocked",
     'if not data:\n        return None, ["video is empty"]', 'if False:\n        return None, ["video is empty"]'),
    ("oversize blocked",
     "if len(data) > REEL_MAX_BYTES:", "if False:"),
    ("container ERROR status fails the publish",
     'if status in ("ERROR", "EXPIRED"):', "if False:"),
    ("token redacted from every error",
     'return text.replace(token, "<redacted>") if token else text', "return text"),
    ("poll sends the token in a header, not the URL",
     'params={"fields": "status_code"},\n                      headers=bearer,',
     'params={"fields": "status_code", "access_token": token},\n                      headers=bearer,'),
    ("container create sends the token in a header, not the body",
     "params=_form(container), headers=bearer)", 'params={**_form(container), "access_token": token}, headers=bearer)'),
    ("upload success must be boolean true",
     'if sent.get("success") is not True:', 'if not sent.get("success"):'),
    ("polling stops at the deadline",
     "if clock() + poll_every > deadline:", "if False:"),
    ("non-object replies are errors",
     "if not isinstance(out, dict):\n        raise PublishError(f\"{where}",
     "if False:\n        raise PublishError(f\"{where}"),
    ("caption length",
     "if len(caption) > CAPTION_MAX_CHARS:", "if False:"),
    ("ffprobe absent is UNCHECKED, not silent",
     'notes.append("UNCHECKED: ffprobe', 'notes.append("checked: ffprobe'),
    ("leave-one-out baseline",
     'others = [x["views"] for x in items if x is not r]', 'others = [x["views"] for x in items]'),
    ("insights settle before judging",
     "if age_h < min_age_hours:", "if False:"),
    ("trial posts excluded from baseline",
     'if q is not p and not q["is_trial"]', "if q is not p"),
]


def run_suite(root: Path) -> int:
    return subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "-x", "-p", "no:cacheprovider"],
                          cwd=root, capture_output=True, text=True).returncode


def main() -> int:
    src = (SKILL / "scripts" / "reel_loop.py").read_text(encoding="utf-8")
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "reel-loop"
        shutil.copytree(SKILL, root, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        target = root / "scripts" / "reel_loop.py"
        if run_suite(root) != 0:
            print("FAIL: the unmutated suite does not pass; fix that first")
            return 1
        for label, old, new in MUTATIONS:
            if src.count(old) != 1:
                print(f"FAIL  {label}: anchor found {src.count(old)} times (expected 1); update the mutation")
                failures += 1
                continue
            target.write_text(src.replace(old, new, 1), encoding="utf-8")
            killed = run_suite(root) != 0
            print(f"{'ok  ' if killed else 'FAIL'}  {label}: {'a test fails' if killed else 'every test still passes'}")
            failures += not killed
        target.write_text(src, encoding="utf-8")
    print(f"\n{len(MUTATIONS) - failures}/{len(MUTATIONS)} mutations killed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
