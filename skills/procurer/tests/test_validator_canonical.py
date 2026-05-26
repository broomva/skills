"""Validator must accept canonical worked examples and reject obvious violations."""

from __future__ import annotations

from pathlib import Path

import validate_report

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "assets" / "examples"


def test_window_noise_example_passes() -> None:
    """The canonical window-noise worked example must validate clean."""
    errors = validate_report.validate(EXAMPLES / "window-noise-attenuation.md")
    assert errors == [], f"Canonical example failed validation:\n  - " + "\n  - ".join(errors)


def test_validator_exits_zero_on_canonical_example(tmp_path, capsys) -> None:
    """CLI entry point exits 0 when the canonical example is passed."""
    rc = validate_report.main(["validate_report.py", str(EXAMPLES / "window-noise-attenuation.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_validator_exits_two_on_missing_file(capsys) -> None:
    """Missing file returns exit code 2 (usage error)."""
    rc = validate_report.main(["validate_report.py", "/nonexistent/path.md"])
    assert rc == 2
