"""Top-level Typer app + ``main`` entry point.

The CLI is the outermost ring of the hexagon: it constructs concrete
adapters via ``Container.build``, drops them into a Typer context, and
dispatches to subcommands. The container is constructed *once* per
process inside the root callback so ``health --help`` skips the build
(and therefore the adapter imports) entirely.

Exit-code policy (see ``domain/errors.py``):
- 0 — success
- 1 — generic error (RateLimited, SyncFailed, RepositoryError, etc.)
- 2 — auth required (AuthRequired, MFANeeded)

Unhandled exceptions are caught at the top level: a friendly message is
printed and exit code 1 is returned. ``--verbose`` re-raises so the full
traceback surfaces in development.
"""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from broomva_health import __version__
from broomva_health.cli import (
    activities as activities_cli,
)
from broomva_health.cli import (
    auth as auth_cli,
)
from broomva_health.cli import (
    backfill as backfill_cli,
)
from broomva_health.cli import (
    context as context_cli,
)
from broomva_health.cli import (
    doctor as doctor_cli,
)
from broomva_health.cli import (
    health as health_metric_cli,
)
from broomva_health.cli import (
    raw as raw_cli,
)
from broomva_health.cli import (
    status as status_cli,
)
from broomva_health.cli import (
    sync as sync_cli,
)
from broomva_health.cli import (
    synthesis as synthesis_cli,
)
from broomva_health.cli import (
    training as training_cli,
)
from broomva_health.cli import (
    weight as weight_cli,
)
from broomva_health.cli.container import Container
from broomva_health.cli.formatters import FORMATS, Format
from broomva_health.config.paths import HealthPaths
from broomva_health.config.settings import load_settings
from broomva_health.domain.errors import HealthError

if TYPE_CHECKING:
    pass

__all__ = ["app", "main"]


app = typer.Typer(
    name="health",
    help=(
        "Broomva Health — personal health knowledge graph. "
        "Trace-ingest + synthesis + Obsidian projection behind a clean "
        "hex-architecture core."
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)


_FORMAT_CHOICE = typer.Option(
    "json",
    "--format",
    "-f",
    help=f"Output format: one of {', '.join(FORMATS)}.",
    case_sensitive=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit(code=0)


@app.callback()
def root(
    ctx: typer.Context,
    profile: str = typer.Option(
        "default",
        "--profile",
        "-p",
        help="Profile identifier (multi-account support).",
        show_default=True,
    ),
    fmt: str = _FORMAT_CHOICE,
    fields: str | None = typer.Option(
        None,
        "--fields",
        help="Comma-separated list of fields to keep in tabular/JSON output.",
    ),
    config_file: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to a TOML config (overrides $BROOMVA_HEALTH_CONFIG_DIR/config.toml).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable DEBUG logging."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error logging."),
    version: bool | None = typer.Option(  # noqa: ARG001 — eager-callback consumes this
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    """Global options. Lazily builds the adapter container."""

    # Logging level — bind early so subcommands inherit it.
    if verbose:
        log_level = logging.DEBUG
    elif quiet:
        log_level = logging.WARNING
    else:
        log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )

    fmt_lower = fmt.lower()
    if fmt_lower not in FORMATS:
        raise typer.BadParameter(
            f"--format must be one of {FORMATS}; got {fmt!r}", param_hint="--format"
        )

    # Defer the heavy lifting to first subcommand call.
    paths = HealthPaths.discover()
    resolved_config = (
        config_file.expanduser() if config_file is not None else paths.config_file
    )
    settings = load_settings(resolved_config)

    container = Container.build(settings, paths)
    ctx.obj = {
        "container": container,
        "format": fmt_lower,  # narrowed; tests assert string
        "fields": [f.strip() for f in fields.split(",")] if fields else None,
        "profile": profile,
        "verbose": verbose,
        "quiet": quiet,
    }
    ctx.call_on_close(container.close)


# --- Subcommand groups -------------------------------------------------------

app.add_typer(auth_cli.app, name="auth")
app.add_typer(sync_cli.app, name="sync")
app.add_typer(status_cli.app, name="status")
app.add_typer(backfill_cli.app, name="backfill")
app.add_typer(activities_cli.app, name="activities")
app.add_typer(health_metric_cli.app, name="health")
app.add_typer(training_cli.app, name="training")
app.add_typer(weight_cli.app, name="weight")
app.add_typer(context_cli.app, name="context")
app.add_typer(synthesis_cli.app, name="synthesis")
app.add_typer(raw_cli.app, name="raw")
app.add_typer(doctor_cli.app, name="doctor")


def _silence_format_for_helpers(fmt: Format) -> Format:
    # Reserved seam for tests that want to swap the default mid-run.
    return fmt


def main() -> None:
    """Process entry point — wraps Typer with exit-code mapping."""

    try:
        app()
    except HealthError as exc:
        # The Typer app may already have printed user-visible output; the
        # exception is the structured-exit signal.
        typer.secho(
            f"error[{exc.code}]: {exc}", fg=typer.colors.RED, err=True
        )
        sys.exit(exc.exit_code)
    except typer.Exit:
        raise
    except SystemExit:
        raise
    except KeyboardInterrupt:
        typer.secho("interrupted", fg=typer.colors.YELLOW, err=True)
        sys.exit(130)
    except Exception as exc:
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        if verbose:
            traceback.print_exc()
        typer.secho(f"unexpected error: {exc}", fg=typer.colors.RED, err=True)
        sys.exit(1)
