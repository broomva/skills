"""Broomva Health skill — personal health knowledge graph.

Hexagonal architecture:
- `domain`      pure Pydantic v2 models, zero I/O
- `ports`       Protocol interfaces (TraceSource, TraceRepository, ...)
- `application` use cases orchestrating ports
- `adapters`    concrete implementations behind ports
- `cli`         Typer surface
- `synthesis`   derived views (HRV-CV, CTL/ATL/TSB, VO2max arc)
- `config`      settings + filesystem paths
- `migrations`  schema versions

Adding a new source (Apple Health, Whoop, Oura) = one new adapter under
`adapters/sources/` + registration in `adapters/sources/_registry.py`.
"""

from __future__ import annotations

__version__ = "0.3.0"
__all__ = ["__version__"]
