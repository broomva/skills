"""Shared pytest fixtures for bookkeeping tests."""
import sys
from pathlib import Path

# Make scripts/ importable as a package
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
