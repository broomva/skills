"""``health auth`` subcommand — login / logout / per-source status."""

from __future__ import annotations

import getpass
from typing import TYPE_CHECKING

import typer

from broomva_health.application.status import HealthStatusUseCase
from broomva_health.cli.formatters import format_value
from broomva_health.domain.errors import AuthRequired, HealthError
from broomva_health.domain.source import Source

if TYPE_CHECKING:
    from broomva_health.cli.container import Container

__all__ = ["app"]


app = typer.Typer(
    no_args_is_help=True,
    help="One-time login + token management for each trace source.",
)


def _container_from_ctx(ctx: typer.Context) -> Container:
    container = ctx.obj["container"] if ctx.obj else None
    if container is None:
        raise typer.BadParameter("CLI was not initialized — container missing")
    return container  # type: ignore[no-any-return]


@app.command("login")
def login(
    ctx: typer.Context,
    email: str | None = typer.Option(None, "--email", help="Garmin Connect account email."),
    profile: str = typer.Option("default", "--profile", "-p", help="Profile identifier."),
    source: Source = typer.Option(
        Source.GARMIN, "--source", "-s", help="Which source to authenticate."
    ),
) -> None:
    """Interactive login: prompts for password securely; persists token bundle.

    The password is read via ``getpass`` so it never appears in shell history
    or terminal scrollback. MFA, if requested by the source, prompts on stdin.
    """

    container = _container_from_ctx(ctx)
    src = container.sources.get(source)
    if src is None:
        typer.secho(f"Source '{source.value}' is not registered.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Delegated-auth backends (e.g. the Garmin `cli` backend, which rides
    # eddmann's garmin-connect token store) never collect a password here —
    # credentials go straight to the upstream tool, never through this skill.
    if getattr(src, "delegated_auth", False):
        src.authenticate(
            token_store=container.token_store,
            mfa=container.mfa,
            email=None,
            password=None,
            profile=profile,
        )
        typer.secho(
            f"{source.value}: authenticated via the delegated backend (profile={profile}).",
            fg=typer.colors.GREEN,
        )
        return

    if email is None:
        email = typer.prompt(f"{source.value} email")
    password = getpass.getpass(f"{source.value} password: ")
    try:
        src.authenticate(
            token_store=container.token_store,
            mfa=container.mfa,
            email=email,
            password=password,
            profile=profile,
        )
    except HealthError:
        raise
    typer.secho(
        f"Authenticated {source.value} as {email} (profile={profile}).",
        fg=typer.colors.GREEN,
    )


@app.command("import")
def import_token(
    ctx: typer.Context,
    from_dir: str | None = typer.Option(
        None,
        "--from",
        help="Directory holding oauth1_token.json + oauth2_token.json "
        "(default: ~/.config/garmin-connect-cli/tokens).",
    ),
    profile: str = typer.Option("default", "--profile", "-p"),
    source: Source = typer.Option(Source.GARMIN, "--source", "-s"),
) -> None:
    """Import an existing token into the in-house (native) backend.

    The native Garmin backend rides an existing garth token instead of doing a
    Cloudflare-walled fresh login. This copies that token (e.g. the one
    ``garmin-connect auth login`` already minted) into our store. No password,
    no fresh login — your credentials never pass through this skill.
    """

    container = _container_from_ctx(ctx)
    src = container.sources.get(source)
    importer = getattr(src, "import_tokens", None)
    if not callable(importer):
        typer.secho(
            f"The '{source.value}' backend does not support token import "
            "(only the native backend does). Set `[garmin] backend = \"native\"`.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    n = importer(from_dir=from_dir, profile=profile)
    typer.secho(
        f"Imported {n} token file(s) for {source.value} (profile={profile}). "
        "Run `health sync` to pull your data.",
        fg=typer.colors.GREEN,
    )


@app.command("logout")
def logout(
    ctx: typer.Context,
    profile: str = typer.Option("default", "--profile", "-p"),
    source: Source = typer.Option(Source.GARMIN, "--source", "-s"),
) -> None:
    """Remove the cached token bundle for ``(source, profile)``."""

    container = _container_from_ctx(ctx)
    container.token_store.delete(source, profile)
    typer.secho(
        f"Removed token bundle for {source.value} (profile={profile}).",
        fg=typer.colors.YELLOW,
    )


@app.command("status")
def status(
    ctx: typer.Context,
    profile: str = typer.Option("default", "--profile", "-p"),
) -> None:
    """Per-source token validity snapshot.

    Exits 0 if every registered source has a valid token, 2 (``auth_required``)
    if any are missing or expired.
    """

    container = _container_from_ctx(ctx)
    use_case = HealthStatusUseCase(
        sources=list(container.sources.values()), token_store=container.token_store
    )
    statuses = use_case.execute(profile=profile)
    fmt = ctx.obj["format"]
    fields = ctx.obj["fields"]
    typer.echo(format_value(statuses, fmt, fields=fields))
    if not all(s.token_valid for s in statuses):
        # Surface as both the typed error (for callers using ``main()``)
        # AND as a typer.Exit so the CliRunner test harness sees the
        # correct exit code without going through ``main()``.
        err = AuthRequired("one or more sources lack a valid token")
        typer.secho(f"error[{err.code}]: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=err.exit_code)
