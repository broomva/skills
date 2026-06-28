"""Pytest configuration for skills/p9 tests.

Ensures `scripts/` is importable as `p9` regardless of how pytest is invoked.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
