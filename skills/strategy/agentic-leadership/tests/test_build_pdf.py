"""Smoke-test the rendered companion playbook when its local toolchain exists."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "build-pdf.sh"
PDF = SKILL_DIR / "assets" / "the-new-baseline.pdf"
DEFAULT_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _chrome() -> str | None:
    configured = os.environ.get("CHROME")
    if configured and Path(configured).is_file():
        return configured
    if DEFAULT_CHROME.is_file():
        return str(DEFAULT_CHROME)
    return next((shutil.which(name) for name in ("google-chrome", "chromium", "chromium-browser") if shutil.which(name)), None)


def test_build_pdf_creates_a_substantive_playbook() -> None:
    """The committed builder renders a readable, multi-page PDF rather than a stub."""
    chrome = _chrome()
    if not shutil.which("pandoc") or not chrome or not shutil.which("pdfinfo"):
        pytest.skip("requires pandoc, Chrome/Chromium, and pdfinfo")

    completed = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=SKILL_DIR,
        env={**os.environ, "CHROME": chrome},
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert PDF.is_file() and PDF.stat().st_size > 100_000

    info = subprocess.run(["pdfinfo", str(PDF)], text=True, capture_output=True, check=True)
    match = re.search(r"^Pages:\s+(\d+)$", info.stdout, re.MULTILINE)
    assert match, info.stdout
    assert int(match.group(1)) >= 8
