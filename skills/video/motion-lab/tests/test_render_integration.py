"""Integration tests: drive scripts/render.mjs end to end through Playwright.

Skipped when Playwright cannot be resolved; set MOTION_LAB_NODE_DIR to a
directory whose node_modules has playwright. CI also sets
MOTION_LAB_REQUIRE_RENDER=1, which turns a missing Playwright into a failure
instead of a silent skip.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
FIX = HERE / "fixtures"


NODE_DIR = Path(os.environ.get("MOTION_LAB_NODE_DIR", SKILL))


def _playwright_available() -> bool:
    if not shutil.which("node"):
        return False
    probe = subprocess.run(["node", "-e", "require.resolve('playwright')"], cwd=NODE_DIR, capture_output=True)
    return probe.returncode == 0


_RENDER_OK = _playwright_available()
if os.environ.get("MOTION_LAB_REQUIRE_RENDER") and not _RENDER_OK:
    # CI sets this: a render suite that silently skips is a false green.
    raise RuntimeError(f"MOTION_LAB_REQUIRE_RENDER is set but playwright is not resolvable from {NODE_DIR}")

needs_playwright = pytest.mark.skipif(not _RENDER_OK,
                                      reason="node + playwright not resolvable (set MOTION_LAB_NODE_DIR)")


def render(fixture: str, out: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX / fixture), "--seconds", "1",
                           "--fps", "12", "--width", "160", "--height", "90", "--out", str(out), *extra],
                          cwd=NODE_DIR, capture_output=True, text=True, timeout=180)


def digests(d: Path) -> list[str]:
    return [hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((d / "frames").glob("*.png"))]


@needs_playwright
class TestRender:
    def test_renders_frames_0_to_n_minus_1_with_a_sheet(self, tmp_path):
        r = render("good.html", tmp_path, "--verify")
        assert r.returncode == 0, r.stderr
        m = json.loads(r.stdout)
        assert m["frames"] == 12 and m["render_range"] == [0, 11]
        assert len(list((tmp_path / "frames").glob("*.png"))) == 12
        assert (tmp_path / "contact.png").stat().st_size > 0
        assert m["verify"]["pure"] is True and m["driven_by"] == {"renderAt": True, "animations": 1}

    def test_frames_actually_change_over_time(self, tmp_path):
        render("good.html", tmp_path, "--no-sheet")
        assert len(set(digests(tmp_path))) > 1

    def test_two_independent_renders_are_byte_identical(self, tmp_path):
        a, b = tmp_path / "a", tmp_path / "b"
        render("good.html", a, "--no-sheet")
        render("good.html", b, "--no-sheet")
        assert digests(a) == digests(b)

    def test_verify_catches_an_impure_renderat(self, tmp_path):
        r = render("impure.html", tmp_path, "--verify", "--no-sheet")
        assert r.returncode == 3
        assert json.loads(r.stdout)["verify"]["mismatches"]

    def test_usage_error(self, tmp_path):
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), "--fps", "0", str(FIX / "good.html")],
                           cwd=NODE_DIR, capture_output=True, text=True)
        assert r.returncode == 2 and "positive" in r.stderr


