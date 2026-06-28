"""CLI subcommand modules.

Each module in this package exposes one or more `click.Command`s that
`runners/cli/__main__.py` registers on the top-level `cli` group. Keeping
the heavy commands here avoids loading every stage runner on
`phronesis --help`.
"""

from __future__ import annotations
