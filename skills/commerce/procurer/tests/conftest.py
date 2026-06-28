"""Pytest configuration for procurer validator tests."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Make scripts/ importable so tests can import validate_report directly
sys.path.insert(0, str(SCRIPTS_DIR))
