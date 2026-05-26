"""CLI layer — Typer surface.

The CLI is the outermost ring of the hex architecture. ``app`` is the
top-level Typer command tree; ``main`` is the process entry point with
exit-code mapping. Most callers want one or the other:

    from broomva_health.cli import app   # for embedding / Typer.testing
    from broomva_health.cli import main  # for the ``health`` script

The ``Container`` is exported for tests that want to wire a custom set
of adapters without going through ``Container.build``.
"""

from __future__ import annotations

from broomva_health.cli.app import app, main
from broomva_health.cli.container import Container
from broomva_health.cli.formatters import FORMATS, Format, format_value

__all__ = ["FORMATS", "Container", "Format", "app", "format_value", "main"]
