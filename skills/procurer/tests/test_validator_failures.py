"""Validator must reject structural violations and explain what failed."""

from __future__ import annotations

from pathlib import Path

import pytest

import validate_report

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"


def _validate_string(content: str, tmp_path: Path) -> list[str]:
    """Helper: write content to tmp_path and run the validator on it."""
    report = tmp_path / "report.md"
    report.write_text(content, encoding="utf-8")
    return validate_report.validate(report)


def test_missing_top_level_headers_fails(tmp_path: Path) -> None:
    content = "# A need\n\nNo sections at all.\n"
    errors = _validate_string(content, tmp_path)
    # Should flag all four missing top-level headers
    assert any("Problem framing" in e for e in errors)
    assert any("Alternatives" in e for e in errors)
    assert any("Recommendation" in e for e in errors)
    assert any("Sources" in e for e in errors)


def test_fewer_than_three_alternatives_fails(tmp_path: Path) -> None:
    content = (
        "# A need\n\n"
        "## Problem framing\nSomething.\n\n"
        "## Alternatives\n\n"
        "### Alternative A — first\n"
        "**Thesis.** x.\n**Cost band.**\n- Low: $ 100\n- Typical: $ 200\n- High: $ 300\n"
        "**Confidence:** 0.8\n**Providers cited:** —\n\n"
        "### Alternative B — second\n"
        "**Thesis.** y.\n**Cost band.**\n- Low: $ 100\n- Typical: $ 200\n- High: $ 300\n"
        "**Confidence:** 0.8\n**Providers cited:** —\n\n"
        "## Recommendation\n**Start with:** A\n**Total budget envelope:** $100 – $200\n**Rationale:** because.\n\n"
        "## Sources\n[1] https://x.com — \"Title\" — fetched 2026-05-13T00:00Z\n"
    )
    errors = _validate_string(content, tmp_path)
    assert any("alternative" in e.lower() and ">=" in e for e in errors), (
        f"Expected '< MIN_ALTERNATIVES' failure; got: {errors}"
    )


def test_confidence_out_of_range_fails(tmp_path: Path) -> None:
    content = _three_alternatives_template().replace(
        "**Confidence:** 0.85", "**Confidence:** 1.5", 1
    )
    errors = _validate_string(content, tmp_path)
    assert any("outside [0, 1]" in e for e in errors), (
        f"Expected out-of-range confidence failure; got: {errors}"
    )


def test_missing_confidence_fails(tmp_path: Path) -> None:
    content = _three_alternatives_template().replace(
        "**Confidence:** 0.85", "Confidence-not-here", 1
    )
    errors = _validate_string(content, tmp_path)
    # The "missing field: Confidence" check should fire
    assert any("Confidence" in e for e in errors)


def test_missing_cost_band_low_fails(tmp_path: Path) -> None:
    content = _three_alternatives_template().replace(
        "- Low: $ 100", "- LOW-MISSING: $ 100", 1
    )
    errors = _validate_string(content, tmp_path)
    assert any("'Low'" in e or "Low" in e for e in errors)


def test_unresolved_footnote_fails(tmp_path: Path) -> None:
    """A footnote referenced in the body but not in ## Sources is flagged."""
    # Template uses [1]; replace one occurrence with [99] (unresolved) so we get
    # a body reference that has no matching ## Sources entry.
    content = _three_alternatives_template().replace(
        "**Providers cited:** see [1]", "**Providers cited:** see [99]", 1
    )
    errors = _validate_string(content, tmp_path)
    assert any("[99]" in e or "99" in e for e in errors), (
        f"Expected unresolved-footnote failure; got: {errors}"
    )


def test_source_missing_url_fails(tmp_path: Path) -> None:
    content = _three_alternatives_template().replace(
        "https://x.com — \"Title\" — fetched 2026-05-13T00:00Z",
        "no-url-here — \"Title\" — fetched 2026-05-13T00:00Z",
        1,
    )
    errors = _validate_string(content, tmp_path)
    assert any("URL" in e for e in errors), (
        f"Expected source-missing-URL failure; got: {errors}"
    )


def test_source_missing_fetched_at_fails(tmp_path: Path) -> None:
    content = _three_alternatives_template().replace(
        "fetched 2026-05-13T00:00Z", "no-timestamp", 1
    )
    errors = _validate_string(content, tmp_path)
    assert any("fetched" in e.lower() for e in errors)


def test_inconsistent_currency_fails(tmp_path: Path) -> None:
    """Mixing $ and EUR across alternatives should flag a currency-consistency error."""
    base = _three_alternatives_template()
    # Replace one alternative's currency to EUR
    content = base.replace("Low: $ 100", "Low: EUR 100", 1)
    content = content.replace("Typical: $ 200", "Typical: EUR 200", 1)
    content = content.replace("High: $ 300", "High: EUR 300", 1)
    errors = _validate_string(content, tmp_path)
    assert any("currency" in e.lower() for e in errors), (
        f"Expected currency-consistency failure; got: {errors}"
    )


def test_missing_recommendation_fields_fails(tmp_path: Path) -> None:
    content = _three_alternatives_template().replace(
        "**Total budget envelope:** $100 – $200\n", "", 1
    )
    errors = _validate_string(content, tmp_path)
    assert any("Total budget envelope" in e for e in errors)


# ----------------------------------------------------------------------
# Template helper
# ----------------------------------------------------------------------

def _three_alternatives_template() -> str:
    """A minimal but valid 3-alternative report. Tests mutate this to exercise failures."""
    return (
        "# A need\n\n"
        "## Problem framing\nSomething.\n\n"
        "## Alternatives\n\n"
        "### Alternative A — first\n"
        "**Thesis.** x.\n"
        "**Cost band.**\n- Low: $ 100\n- Typical: $ 200\n- High: $ 300\n"
        "**Confidence:** 0.85\n"
        "**Providers cited:** see [1]\n\n"
        "### Alternative B — second\n"
        "**Thesis.** y.\n"
        "**Cost band.**\n- Low: $ 100\n- Typical: $ 200\n- High: $ 300\n"
        "**Confidence:** 0.85\n"
        "**Providers cited:** see [1]\n\n"
        "### Alternative C — third\n"
        "**Thesis.** z.\n"
        "**Cost band.**\n- Low: $ 100\n- Typical: $ 200\n- High: $ 300\n"
        "**Confidence:** 0.85\n"
        "**Providers cited:** see [1]\n\n"
        "## Recommendation\n"
        "**Start with:** A\n"
        "**Total budget envelope:** $100 – $200\n"
        "**Rationale:** because.\n\n"
        "## Sources\n"
        "[1] https://x.com — \"Title\" — fetched 2026-05-13T00:00Z\n"
    )


def test_template_helper_itself_validates_clean(tmp_path: Path) -> None:
    """Sanity check — the template helper must produce a passing report."""
    errors = _validate_string(_three_alternatives_template(), tmp_path)
    assert errors == [], f"Template helper unexpectedly failed validation: {errors}"
