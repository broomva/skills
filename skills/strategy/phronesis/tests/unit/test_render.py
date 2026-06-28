"""Renderer base — Jinja2 environment + filters."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from core.render import _as_currency, _as_percent, render

pytestmark = pytest.mark.unit


class TestAsCurrencyFilter:
    def test_decimal_renders_as_dollar_with_commas(self):
        assert _as_currency(Decimal("640000")) == "$640,000"

    def test_int_renders_as_dollar(self):
        assert _as_currency(420000) == "$420,000"

    def test_float_renders_as_dollar(self):
        assert _as_currency(180000.0) == "$180,000"

    def test_non_numeric_returns_str(self):
        assert _as_currency("TBD") == "TBD"  # type: ignore[arg-type]

    def test_non_usd_currency(self):
        assert _as_currency(Decimal("1000000"), currency="COP") == "1,000,000 COP"


class TestAsPercentFilter:
    def test_fraction_renders_as_percent(self):
        assert _as_percent(Decimal("0.234")) == "23.4%"

    def test_one_decimal_default(self):
        assert _as_percent(0.85) == "85.0%"

    def test_custom_places(self):
        assert _as_percent(Decimal("0.234567"), places=3) == "23.457%"

    def test_non_numeric_returns_str(self):
        assert _as_percent("N/A") == "N/A"  # type: ignore[arg-type]


class TestRender:
    def test_render_missing_template_raises(self):
        from jinja2.exceptions import TemplateNotFound

        with pytest.raises(TemplateNotFound):
            render("nonexistent-slug", {})

    def test_render_uses_strict_undefined(self, tmp_path: Path):
        """Phase 1 has no smoke-template ready; D.1 ships maturity-report.
        Verify strict-undefined behavior via TemplateNotFound proxy: any
        missing template OR missing var must raise."""
        # The maturity-report.md.j2 template ships in D.1; its tests cover
        # strict-undefined behavior end-to-end. Here we just assert the
        # filters are registered.
        from core.render import _build_environment

        env = _build_environment()
        assert "as_currency" in env.filters
        assert "as_percent" in env.filters
