"""Jinja2 renderer for engagement deliverables.

Each deliverable has a template at templates/<slug>.md.j2; the renderer feeds
it engagement state + stage outputs and produces markdown. The L1-L5 + P3 +
P7 + P8 linters run on the rendered output before persisting (M3 release gate).

Strict undefined: missing context variables raise UndefinedError immediately
rather than silently producing empty output.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATES_ROOT = Path(__file__).resolve().parent.parent / "templates"


def _as_currency(value: Decimal | int | float, currency: str = "USD") -> str:
    """Format a Decimal/numeric value as `$640,000` style currency.

    USD is the default for Phase 1; future revisions may key on
    Recommendation.value_currency for non-USD engagements.
    """
    if not isinstance(value, (Decimal, int, float)):
        return str(value)
    n = float(value)
    if currency == "USD":
        return f"${n:,.0f}"
    return f"{n:,.0f} {currency}"


def _as_percent(value: Decimal | int | float, places: int = 1) -> str:
    """Format a fraction (0.234) as `23.4%`."""
    if not isinstance(value, (Decimal, int, float)):
        return str(value)
    n = float(value)
    return f"{n * 100:.{places}f}%"


def _build_environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_ROOT)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,  # markdown, not HTML
    )
    env.filters["as_currency"] = _as_currency
    env.filters["as_percent"] = _as_percent
    return env


def render(slug: str, context: dict[str, Any]) -> str:
    """Render a deliverable template against context.

    Raises:
        TemplateNotFound: if templates/<slug>.md.j2 doesn't exist.
        UndefinedError: if context omits a required variable.
    """
    env = _build_environment()
    template = env.get_template(f"{slug}.md.j2")
    return template.render(**context)
