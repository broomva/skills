#!/usr/bin/env python3
"""Regression test — every entrypoint script must carry the Python 3.10 guard.

This catches the bug class discovered 2026-05-22 by dogfood: a contributor adds
a new script that uses PEP-604 union types (`str | None`) or other 3.10+
syntax in module-level annotations but forgets the runtime guard at the top.
On a Python 3.9 interpreter that script then fails with a cryptic
`TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`
instead of the clean version-requirement message.

Run: `python3 scripts/test_runtime_guard.py` (or via pytest if it ever exists).
Exit 0 = all entrypoints guarded; exit 1 = list of unguarded scripts printed.
"""

# Self-guard: this very file also runs on the same interpreter, so guard first.
import sys

if sys.version_info < (3, 10):
    raise SystemExit(
        f"finance-substrate requires Python >= 3.10. "
        f"Got {sys.version_info.major}.{sys.version_info.minor}. "
        f"Install via `brew install python@3.11` or `pyenv install 3.11 && pyenv local 3.11`."
    )

from pathlib import Path

GUARD_SENTINEL = "version_info < (3, 10)"

EXEMPT_SCRIPTS = {
    # _runtime_check.py (if it ever appears) is the shared module that hosts
    # the check — not an entrypoint itself.
    "_runtime_check.py",
}


def main() -> int:
    scripts_dir = Path(__file__).parent
    unguarded: list[str] = []

    for script in sorted(scripts_dir.glob("*.py")):
        if script.name in EXEMPT_SCRIPTS:
            continue
        if script.name == Path(__file__).name:
            # this file is the test — it carries its own guard, verified above
            continue
        content = script.read_text(encoding="utf-8")
        # Only check files that look like CLI entrypoints (have if __name__ == ...
        # or are scripts in scripts/).
        if GUARD_SENTINEL not in content:
            unguarded.append(script.name)

    if unguarded:
        print("UNGUARDED entrypoint scripts (add the Python 3.10 runtime guard):")
        for name in unguarded:
            print(f"  scripts/{name}")
        print()
        print("Required guard pattern (insert after the module docstring):")
        print("""
# --- Python version guard (PEP 604 union syntax requires >= 3.10) ---
import sys

if sys.version_info < (3, 10):
    raise SystemExit(
        f"finance-substrate requires Python >= 3.10. "
        f"Got {sys.version_info.major}.{sys.version_info.minor}. "
        f"Install via `brew install python@3.11` or `pyenv install 3.11 && pyenv local 3.11`."
    )
# --- end guard ---
""")
        return 1

    print(f"OK — all {len(list(scripts_dir.glob('*.py'))) - 1} entrypoint scripts carry the Python 3.10 guard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
