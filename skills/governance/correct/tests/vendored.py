#!/usr/bin/env -S python3 -I
"""vendored.py — the runner files this skill took from broomva/workspace, and their hashes.

scripts/VENDORED.json records the source commit and, for each file, the sha256 of the source
and of the copy shipped here. Any edit to a shipped file must be recorded: change the file,
run `python3 -I tests/vendored.py --write`, and say what changed under "changes". The test
suite (tests/test_correct.py) fails while the manifest and the files disagree.

  vendored.py            exit 1 and name each file whose hash is not the recorded one
  vendored.py --write    rewrite the shipped hashes (source hashes and "changes" stay)
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
MANIFEST = SCRIPTS / "VENDORED.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mismatches() -> list[str]:
    data = json.loads(MANIFEST.read_text())
    out = []
    for name, entry in sorted(data["files"].items()):
        path = SCRIPTS / name
        if not path.exists():
            out.append(f"{name}: recorded in VENDORED.json and not shipped")
        elif sha(path) != entry["shipped_sha256"]:
            out.append(f"{name}: differs from the hash in VENDORED.json; record the change "
                       "(tests/vendored.py --write, and a line under \"changes\")")
        if entry["shipped_sha256"] != entry["source_sha256"] and not any(
                c.get("file") == name for c in data.get("changes") or []):
            out.append(f"{name}: differs from its source and VENDORED.json \"changes\" does not say how")
    return out


def main(argv: list[str]) -> int:
    if argv == ["--write"]:
        data = json.loads(MANIFEST.read_text())
        for name, entry in data["files"].items():
            entry["shipped_sha256"] = sha(SCRIPTS / name)
        MANIFEST.write_text(json.dumps(data, indent=2) + "\n")
        return 0
    if argv:
        print(__doc__, file=sys.stderr)
        return 2
    bad = mismatches()
    for line in bad:
        print(line, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
